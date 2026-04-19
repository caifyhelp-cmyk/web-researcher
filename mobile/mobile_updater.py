# -*- coding: utf-8 -*-
"""
MAESTRO 모바일 업데이터

Android APK 특성:
  - APK 내부 파일은 읽기 전용 (덮어쓰기 불가)
  - 해결책: 앱 전용 쓰기 가능 디렉터리에 새 파일 다운로드
            → sys.path 앞에 추가해 번들 파일보다 우선 로드

업데이트 대상:
  maestro.py, orchestrator.py, personalizer.py,
  web_researcher.py, pattern_collector.py, feedback_collector.py
  (mobile/ 폴더 파일은 APK 재빌드 필요, 여기서는 제외)

절대 건드리지 않는 파일:
  keys.enc, history.json, custom.json (사용자 데이터)

안전 메커니즘:
  1. 원자적 쓰기 (.tmp → rename) — 다운로드 중 크래시 시 기존 파일 보존
  2. AST 파싱으로 다운로드 파일 최소 문법 검증
  3. 롤백: 검증 실패 시 기존 버전 유지
  4. 버전 메타 파일로 중복 다운로드 방지
"""

import os, sys, json, hashlib, ast, threading, logging, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime

_log = logging.getLogger("maestro.updater")

# ── 경로 설정 ──────────────────────────────────────────────────────
try:
    from kivy.utils import platform as _plat
    _IS_ANDROID = _plat == "android"
except ImportError:
    _IS_ANDROID = False

if _IS_ANDROID:
    _APP_DATA   = Path("/data/data/com.maestro.app/files")
else:
    _APP_DATA   = Path(os.path.expanduser("~")) / ".maestro"

_UPDATE_DIR  = _APP_DATA / "updates"     # 다운로드된 최신 파일
_META_FILE   = _APP_DATA / "update_meta.json"
_UPDATE_DIR.mkdir(parents=True, exist_ok=True)

# ── GitHub 설정 ────────────────────────────────────────────────────
REPO_OWNER = "caifyhelp-cmyk"
REPO_NAME  = "web-researcher"
BRANCH     = "master"
_RAW_BASE  = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}"
_API_BASE  = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"

# 업데이트 가능한 Python 로직 파일 (mobile/ 파일 제외)
_UPDATABLE = [
    "maestro.py",
    "orchestrator.py",
    "personalizer.py",
    "web_researcher.py",
    "pattern_collector.py",
    "feedback_collector.py",
]

# 업데이트 이벤트 (UI 스레드에서 읽는 공유 상태)
_state: dict = {
    "available":    False,   # 업데이트 있음
    "commit":       "",      # 최신 커밋 해시
    "downloading":  False,   # 다운로드 진행 중
    "done":         False,   # 다운로드 완료 (재시작 필요)
    "files":        [],      # 업데이트된 파일 목록
    "error":        "",      # 오류 메시지
}


def get_state() -> dict:
    return _state.copy()


# ══════════════════════════════════════════════════════════════════
#  sys.path 설정 (앱 시작 시 반드시 호출)
# ══════════════════════════════════════════════════════════════════

def setup_update_path():
    """
    업데이트 디렉터리를 sys.path 최우선 위치에 추가.
    이후 import 시 업데이트된 파일이 번들 파일보다 먼저 로드됨.
    """
    update_str = str(_UPDATE_DIR)
    if update_str not in sys.path:
        sys.path.insert(0, update_str)
    _log.info("Update path: %s", update_str)


# ══════════════════════════════════════════════════════════════════
#  버전 메타 관리
# ══════════════════════════════════════════════════════════════════

def _load_meta() -> dict:
    try:
        if _META_FILE.exists():
            return json.loads(_META_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"installed_commit": "", "last_check": "", "files": {}}


def _save_meta(meta: dict):
    try:
        meta["last_check"] = datetime.now().isoformat()[:19]
        _META_FILE.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
#  GitHub 통신 (HTTPS 전용)
# ══════════════════════════════════════════════════════════════════

def _fetch(url: str, timeout: int = 12) -> bytes | None:
    """GitHub에서 HTTPS로 파일 다운로드"""
    if not url.startswith("https://"):
        _log.error("Non-HTTPS URL blocked: %s", url[:60])
        return None
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "MAESTRO-Mobile-Updater/2.1"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.URLError as e:
        _log.warning("Fetch failed: %s", type(e).__name__)
        return None
    except Exception:
        return None


def _get_latest_commit() -> str:
    """GitHub 최신 커밋 해시 (앞 12자리)"""
    data = _fetch(f"{_API_BASE}/commits/{BRANCH}")
    if data:
        try:
            return json.loads(data).get("sha", "")[:12]
        except Exception:
            pass
    return ""


# ══════════════════════════════════════════════════════════════════
#  파일 검증
# ══════════════════════════════════════════════════════════════════

def _validate_python(content: bytes) -> bool:
    """다운로드된 Python 파일 최소 문법 검증 (AST 파싱)"""
    try:
        ast.parse(content.decode("utf-8", errors="replace"))
        return True
    except SyntaxError as e:
        _log.error("Syntax error in downloaded file: %s", e.msg)
        return False
    except Exception:
        return False


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ══════════════════════════════════════════════════════════════════
#  업데이트 확인 (백그라운드)
# ══════════════════════════════════════════════════════════════════

def check_background():
    """앱 시작 시 백그라운드에서 업데이트 확인 (UI 차단 없음)"""
    t = threading.Thread(target=_check_worker, daemon=True)
    t.start()


def _check_worker():
    global _state
    try:
        meta   = _load_meta()
        latest = _get_latest_commit()
        if not latest:
            return   # 오프라인 또는 GitHub 오류 → 무시

        if latest == meta.get("installed_commit"):
            return   # 이미 최신

        _state["available"] = True
        _state["commit"]    = latest
        _log.info("Update available: %s", latest)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
#  업데이트 실행 (사용자가 "업데이트" 버튼 누를 때)
# ══════════════════════════════════════════════════════════════════

def download_and_apply(on_progress=None, on_done=None, on_error=None):
    """
    업데이트 파일 다운로드 + 적용. 백그라운드 실행.

    on_progress(fname, pct): 파일별 진행률 콜백
    on_done(files):          완료 콜백 (업데이트된 파일 목록)
    on_error(msg):           오류 콜백
    """
    t = threading.Thread(
        target=_download_worker,
        args=(on_progress, on_done, on_error),
        daemon=True
    )
    t.start()


def _download_worker(on_progress, on_done, on_error):
    global _state
    _state["downloading"] = True
    _state["error"]       = ""

    meta    = _load_meta()
    applied = []
    total   = len(_UPDATABLE)

    for i, fname in enumerate(_UPDATABLE):
        if on_progress:
            on_progress(fname, int(i / total * 100))

        # 다운로드
        content = _fetch(f"{_RAW_BASE}/{fname}")
        if content is None:
            _log.warning("Skip %s (download failed)", fname)
            continue

        # 변경 여부 확인 (해시 비교)
        remote_hash = _sha256(content)
        existing_path = _UPDATE_DIR / fname
        if existing_path.exists():
            if _sha256(existing_path.read_bytes()) == remote_hash:
                applied.append(fname)  # 이미 최신 버전
                continue

        # Python 파일 문법 검증
        if fname.endswith(".py") and not _validate_python(content):
            _log.error("Validation failed for %s — skipped", fname)
            if on_error:
                on_error(f"{fname} 검증 실패 (다운로드 건너뜀)")
            continue

        # 원자적 쓰기 (.tmp → rename)
        tmp_path = existing_path.with_suffix(".tmp")
        try:
            tmp_path.write_bytes(content)
            tmp_path.replace(existing_path)   # 원자적 교체
            applied.append(fname)
            _log.info("Updated: %s", fname)
        except Exception as e:
            _log.error("Write failed for %s: %s", fname, type(e).__name__)
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            continue

    # 메타 저장
    commit = _state.get("commit", "")
    if applied and commit:
        meta["installed_commit"] = commit
        meta["files"] = {f: _sha256((_UPDATE_DIR / f).read_bytes())
                         for f in applied if (_UPDATE_DIR / f).exists()}
        _save_meta(meta)

    _state["downloading"] = False
    _state["done"]        = True
    _state["files"]       = applied

    if on_done:
        on_done(applied)
