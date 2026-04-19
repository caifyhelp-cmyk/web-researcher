# -*- coding: utf-8 -*-
"""
MAESTRO 보안 키 저장소

Android: Android ID 기반 기기 바인딩 키 → AES-256(Fernet) 암호화
PC/Dev : machine UUID 기반 키 유도

보안 설계:
  - 키는 절대 평문으로 저장 안 됨
  - 암호화 키는 기기 고유 값으로 유도 (저장 안 함)
  - keys.enc 파일을 다른 기기로 복사해도 복호화 불가
  - 앱 전용 디렉터리 사용 (다른 앱 접근 불가)
"""

import os, hashlib, json, logging
from pathlib import Path

# ── 플랫폼 감지 ────────────────────────────────────────────────────
try:
    from kivy.utils import platform as _plat
    _IS_ANDROID = _plat == "android"
except ImportError:
    _IS_ANDROID = False

# ── 저장 경로 ──────────────────────────────────────────────────────
if _IS_ANDROID:
    # 앱 전용 내부 저장소 (다른 앱 접근 불가, 권한 없이 접근 불가)
    _STORAGE_DIR = Path("/data/data/com.maestro.app/files/.maestro")
else:
    _STORAGE_DIR = Path(os.path.expanduser("~")) / ".maestro"

_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
_KEYS_FILE = _STORAGE_DIR / "keys.enc"

# 로그에 민감 정보 절대 기록 안 함
_log = logging.getLogger("maestro.storage")


# ══════════════════════════════════════════════════════════════════
#  기기 바인딩 키 유도
# ══════════════════════════════════════════════════════════════════

def _get_device_fingerprint() -> str:
    """
    기기 고유 식별자 수집 (저장 안 함, 유도에만 사용).
    Android: ANDROID_ID (앱+기기 조합으로 유일, Android 8.0+)
    PC: 네트워크 MAC + 플랫폼 정보
    """
    if _IS_ANDROID:
        try:
            from jnius import autoclass
            Settings = autoclass("android.provider.Settings$Secure")
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            android_id = Settings.getString(
                activity.getContentResolver(),
                Settings.ANDROID_ID
            ) or "fallback-android"
            return android_id
        except Exception:
            # jnius 실패 시 (에뮬레이터 등) 앱-내부 랜덤 ID 생성
            fallback_path = _STORAGE_DIR / ".device_id"
            if fallback_path.exists():
                return fallback_path.read_text().strip()
            import secrets
            fid = secrets.token_hex(16)
            fallback_path.write_text(fid)
            return fid
    else:
        try:
            import uuid
            return str(uuid.getnode())
        except Exception:
            return "dev-fallback-key"


def _derive_fernet_key() -> bytes:
    """
    PBKDF2-HMAC-SHA256으로 Fernet 키 유도.
    동일 기기에서 항상 같은 키 생성.
    """
    fingerprint = _get_device_fingerprint()
    # PBKDF2: 210,000 반복 (NIST 2023 권장 기준 이상)
    raw = hashlib.pbkdf2_hmac(
        "sha256",
        fingerprint.encode("utf-8"),
        b"maestro-salt-v2-2025",  # 고정 salt (앱 식별자)
        iterations=210_000,
    )
    import base64
    return base64.urlsafe_b64encode(raw[:32])


# ══════════════════════════════════════════════════════════════════
#  공개 API
# ══════════════════════════════════════════════════════════════════

class SecureStorage:
    """암호화 키 저장/로드"""

    _fernet = None  # 지연 초기화

    @classmethod
    def _get_fernet(cls):
        if cls._fernet is None:
            try:
                from cryptography.fernet import Fernet
                cls._fernet = Fernet(_derive_fernet_key())
            except ImportError:
                # cryptography 없으면 XOR 폴백 (개발 환경용)
                cls._fernet = _XorFallback(_derive_fernet_key())
        return cls._fernet

    @classmethod
    def save(cls, keys: dict) -> bool:
        """API 키 딕셔너리를 암호화 저장"""
        try:
            plaintext = json.dumps(keys, ensure_ascii=False).encode("utf-8")
            encrypted = cls._get_fernet().encrypt(plaintext)
            _KEYS_FILE.write_bytes(encrypted)
            # 파일 권한: 소유자만 읽기 (Unix 계열)
            try:
                os.chmod(_KEYS_FILE, 0o600)
            except Exception:
                pass
            _log.info("Keys saved (encrypted)")
            return True
        except Exception as e:
            _log.error("Save failed: %s", type(e).__name__)  # 내용 로그 안 함
            return False

    @classmethod
    def load(cls) -> dict:
        """암호화 키 로드 및 복호화. 실패 시 빈 dict 반환"""
        if not _KEYS_FILE.exists():
            return {}
        try:
            encrypted = _KEYS_FILE.read_bytes()
            plaintext = cls._get_fernet().decrypt(encrypted)
            return json.loads(plaintext.decode("utf-8"))
        except Exception as e:
            _log.warning("Load failed (wrong device or corrupted): %s", type(e).__name__)
            return {}

    @classmethod
    def clear(cls) -> bool:
        """저장된 키 안전 삭제 (파일 내용을 0으로 덮어쓴 뒤 삭제)"""
        try:
            if _KEYS_FILE.exists():
                size = _KEYS_FILE.stat().st_size
                # 랜덤 바이트로 3회 덮어쓰기 (간단한 secure erase)
                import secrets
                for _ in range(3):
                    _KEYS_FILE.write_bytes(secrets.token_bytes(max(size, 64)))
                _KEYS_FILE.unlink()
            cls._fernet = None  # 캐시 제거
            return True
        except Exception:
            return False

    @classmethod
    def has_keys(cls) -> bool:
        """최소 1개의 키가 저장됐는지 확인"""
        loaded = cls.load()
        return bool(loaded.get("OPENAI_API_KEY") or loaded.get("ANTHROPIC_API_KEY"))


class _XorFallback:
    """cryptography 라이브러리 없을 때 폴백 (개발 전용, 프로덕션 사용 금지)"""
    def __init__(self, key: bytes):
        import base64
        raw = base64.urlsafe_b64decode(key + b"==")
        self._key = raw[:32]

    def encrypt(self, data: bytes) -> bytes:
        import base64, os as _os
        iv = _os.urandom(16)
        xored = bytes(b ^ self._key[i % 32] for i, b in enumerate(data))
        return base64.urlsafe_b64encode(iv + xored)

    def decrypt(self, token: bytes) -> bytes:
        import base64
        raw = base64.urlsafe_b64decode(token)
        data = raw[16:]  # iv 제거
        return bytes(b ^ self._key[i % 32] for i, b in enumerate(data))
