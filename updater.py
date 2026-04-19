# -*- coding: utf-8 -*-
"""
MAESTRO 자동 업데이터

역할:
  1. GitHub에서 최신 버전 확인 (커밋 해시 비교)
  2. 변경된 메인 파일만 다운로드·적용
  3. ~/.maestro/custom.json 은 절대 건드리지 않음
  4. 업데이트 내역 출력

사용:
  python updater.py          # 대화형 업데이트 확인
  python updater.py --auto   # 조용히 자동 업데이트 (앱 시작 시 호출)
"""

import os, sys, json, hashlib, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime

_HERE      = Path(__file__).parent
_META_PATH = Path(os.path.expanduser("~")) / ".maestro" / "update_meta.json"
_META_PATH.parent.mkdir(parents=True, exist_ok=True)

REPO_OWNER = "caifyhelp-cmyk"
REPO_NAME  = "web-researcher"
BRANCH     = "master"

# 업데이트 대상 파일 (custom.json, _local_keys.py 등은 절대 포함하지 않음)
UPDATE_FILES = [
    "maestro.py",
    "app_local.py",
    "orchestrator.py",
    "web_researcher.py",
    "pattern_collector.py",
    "feedback_collector.py",
    "requirements.txt",
]

GITHUB_RAW = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}"
GITHUB_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"


# ══════════════════════════════════════════════
#  버전 메타 관리
# ══════════════════════════════════════════════

def _load_meta() -> dict:
    try:
        return json.loads(_META_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"installed_commit": "", "last_check": "", "files": {}}


def _save_meta(meta: dict):
    _META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _file_hash(path: Path) -> str:
    """로컬 파일 SHA256"""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return ""


# ══════════════════════════════════════════════
#  GitHub 통신
# ══════════════════════════════════════════════

def _gh_get(url: str, token: str = "") -> dict | str | None:
    headers = {"User-Agent": "MAESTRO-Updater/1.0"}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            ct = r.headers.get("Content-Type", "")
            data = r.read()
            if "json" in ct:
                return json.loads(data)
            return data.decode("utf-8", errors="replace")
    except Exception:
        return None


def get_latest_commit() -> str:
    """GitHub 최신 커밋 해시 반환"""
    token = os.getenv("GITHUB_DATA_TOKEN", os.getenv("GH_TOKEN", ""))
    result = _gh_get(f"{GITHUB_API}/commits/{BRANCH}", token)
    if isinstance(result, dict):
        return result.get("sha", "")[:12]
    return ""


def download_file(fname: str) -> str | None:
    """GitHub에서 파일 내용 다운로드"""
    token = os.getenv("GITHUB_DATA_TOKEN", os.getenv("GH_TOKEN", ""))
    content = _gh_get(f"{GITHUB_RAW}/{fname}", token)
    if isinstance(content, str) and len(content) > 10:
        return content
    return None


# ══════════════════════════════════════════════
#  업데이트 실행
# ══════════════════════════════════════════════

def check_and_update(auto: bool = False, silent: bool = False) -> dict:
    """
    업데이트 확인 및 적용.

    Args:
        auto:   True = 변경 있으면 자동 적용 (질문 없음)
        silent: True = 최신 상태면 아무것도 출력 안 함

    Returns:
        {"updated": bool, "files": [str], "commit": str, "error": str}
    """
    meta = _load_meta()

    if not silent:
        print("MAESTRO 업데이트 확인 중...")

    latest_commit = get_latest_commit()
    if not latest_commit:
        return {"updated": False, "files": [], "error": "GitHub 연결 실패"}

    meta["last_check"] = datetime.now().isoformat()

    if latest_commit == meta.get("installed_commit"):
        if not silent:
            print(f"최신 버전입니다 (커밋: {latest_commit})")
        _save_meta(meta)
        return {"updated": False, "files": [], "commit": latest_commit}

    # 변경 감지
    changed = []
    new_contents = {}

    for fname in UPDATE_FILES:
        remote = download_file(fname)
        if remote is None:
            continue
        local_path = _HERE / fname
        local_hash = _file_hash(local_path)
        remote_hash = hashlib.sha256(remote.encode("utf-8")).hexdigest()
        if local_hash != remote_hash:
            changed.append(fname)
            new_contents[fname] = remote

    if not changed:
        meta["installed_commit"] = latest_commit
        _save_meta(meta)
        if not silent:
            print(f"최신 버전입니다 (커밋: {latest_commit})")
        return {"updated": False, "files": [], "commit": latest_commit}

    print(f"\n새 업데이트 발견 (커밋: {latest_commit})")
    print(f"변경 파일: {', '.join(changed)}")

    # 자동 모드 아니면 확인
    if not auto:
        ans = input("업데이트 적용할까요? [Y/n] ").strip().lower()
        if ans == "n":
            return {"updated": False, "files": [], "commit": latest_commit}

    # 적용
    applied = []
    for fname, content in new_contents.items():
        target = _HERE / fname
        # 백업
        backup = target.with_suffix(target.suffix + ".bak")
        try:
            if target.exists():
                backup.write_bytes(target.read_bytes())
            target.write_text(content, encoding="utf-8")
            applied.append(fname)
            if not silent:
                print(f"  ✓ {fname} 업데이트됨")
        except Exception as e:
            print(f"  ✗ {fname} 실패: {e}")

    meta["installed_commit"] = latest_commit
    meta["files"] = {f: hashlib.sha256((_HERE/f).read_bytes()).hexdigest()
                     for f in applied if (_HERE/f).exists()}
    _save_meta(meta)

    print(f"\n업데이트 완료 ({len(applied)}개 파일)")
    return {"updated": True, "files": applied, "commit": latest_commit}


def check_update_background():
    """앱 시작 시 백그라운드에서 조용히 확인 (변경 있어도 알림만)"""
    import threading

    def _run():
        try:
            meta = _load_meta()
            latest = get_latest_commit()
            if not latest:
                return
            if latest != meta.get("installed_commit", ""):
                # 변경 있음 → 메인 스레드에 알림용 플래그만 설정
                _PENDING_UPDATE["commit"] = latest
                _PENDING_UPDATE["available"] = True
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()


# 앱이 읽어가는 전역 플래그
_PENDING_UPDATE: dict = {"available": False, "commit": ""}


if __name__ == "__main__":
    auto_flag = "--auto" in sys.argv
    check_and_update(auto=auto_flag, silent=False)
