# -*- coding: utf-8 -*-
"""
MAESTRO 보안 감시자

역할:
  1. 루팅/탈옥 감지 → 경고 (사용 차단은 아님, 사용자 선택)
  2. 개발자 모드 감지
  3. 에뮬레이터 감지 (API 키 노출 위험)
  4. 네트워크 보안 설정

감지 즉시 앱 종료는 하지 않음 — 사용자에게 경고 후 선택권 부여.
"""

import os, sys, logging
from typing import NamedTuple

_log = logging.getLogger("maestro.security")

try:
    from kivy.utils import platform as _plat
    _IS_ANDROID = _plat == "android"
except ImportError:
    _IS_ANDROID = False


class SecurityReport(NamedTuple):
    is_rooted:    bool
    is_emulator:  bool
    is_dev_mode:  bool
    risk_level:   str   # "low" / "medium" / "high"
    warnings:     list  # 경고 메시지 목록


# ══════════════════════════════════════════════════════════════════
#  루팅 감지
# ══════════════════════════════════════════════════════════════════

_ROOT_BINARIES = [
    "/sbin/su", "/system/bin/su", "/system/xbin/su",
    "/data/local/xbin/su", "/data/local/bin/su",
    "/system/sd/xbin/su", "/system/bin/failsafe/su",
    "/data/local/su", "/su/bin/su",
]

_ROOT_PACKAGES = [
    "/system/app/Superuser.apk",
    "/system/app/SuperSU.apk",
    "/system/app/Magisk.apk",
    "/data/app/eu.chainfire.supersu",
    "/data/app/com.topjohnwu.magisk",
    "/data/app/com.kingroot.kinguser",
]

_ROOT_PROPS = [
    ("ro.build.tags", "test-keys"),
    ("ro.debuggable", "1"),
    ("ro.secure", "0"),
]


def _check_root_android() -> tuple[bool, list]:
    warnings = []

    # 1. su 바이너리 존재 확인
    for path in _ROOT_BINARIES:
        if os.path.exists(path):
            warnings.append(f"루팅 흔적: {path}")
            return True, warnings

    # 2. 루트 앱 패키지 확인
    for pkg in _ROOT_PACKAGES:
        if os.path.exists(pkg):
            warnings.append(f"루팅 앱 감지: {os.path.basename(pkg)}")
            return True, warnings

    # 3. Build 프로퍼티 확인
    try:
        from jnius import autoclass
        Build = autoclass("android.os.Build")
        tags = Build.TAGS or ""
        if "test-keys" in tags:
            warnings.append("빌드 태그: test-keys (루팅 ROM 의심)")
            return True, warnings
    except Exception:
        pass

    # 4. /proc/mounts 확인 (system rw 마운트)
    try:
        mounts = open("/proc/mounts").read()
        if " /system " in mounts and "rw," in mounts:
            warnings.append("/system 파티션이 쓰기 가능으로 마운트됨")
            return True, warnings
    except Exception:
        pass

    return False, warnings


# ══════════════════════════════════════════════════════════════════
#  에뮬레이터 감지
# ══════════════════════════════════════════════════════════════════

def _check_emulator() -> tuple[bool, list]:
    warnings = []
    if not _IS_ANDROID:
        return False, warnings

    try:
        from jnius import autoclass
        Build = autoclass("android.os.Build")

        fingerprint = (Build.FINGERPRINT or "").lower()
        model       = (Build.MODEL or "").lower()
        manufacturer= (Build.MANUFACTURER or "").lower()
        brand       = (Build.BRAND or "").lower()
        product     = (Build.PRODUCT or "").lower()
        hardware    = (Build.HARDWARE or "").lower()

        emulator_markers = {
            "fingerprint": ["generic", "unknown", "emulator", "sdk_gphone"],
            "model":       ["emulator", "android sdk", "sdk_phone", "google_sdk"],
            "manufacturer":["unknown", "genymotion"],
            "brand":       ["generic", "android"],
            "product":     ["sdk_gphone", "sdk", "generic"],
            "hardware":    ["goldfish", "ranchu", "vbox86"],
        }

        fields = dict(fingerprint=fingerprint, model=model,
                      manufacturer=manufacturer, brand=brand,
                      product=product, hardware=hardware)

        for field, markers in emulator_markers.items():
            val = fields[field]
            if any(m in val for m in markers):
                warnings.append(f"에뮬레이터 감지 ({field}: {val})")
                return True, warnings

    except Exception:
        pass

    return False, warnings


# ══════════════════════════════════════════════════════════════════
#  개발자 모드 감지
# ══════════════════════════════════════════════════════════════════

def _check_dev_mode() -> bool:
    if not _IS_ANDROID:
        return False
    try:
        from jnius import autoclass
        Settings = autoclass("android.provider.Settings$Global")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        adb_enabled = Settings.getInt(
            activity.getContentResolver(), Settings.ADB_ENABLED, 0)
        return adb_enabled == 1
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════
#  네트워크 보안: HTTPS 강제
# ══════════════════════════════════════════════════════════════════

def enforce_https():
    """
    HTTP(평문) 요청 차단.
    requests / httpx 의 기본 세션에 커스텀 어댑터를 붙여
    http:// URL을 사용하면 예외 발생.
    """
    try:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        class _HttpsOnlyAdapter(HTTPAdapter):
            def send(self, request, *args, **kwargs):
                if request.url and request.url.startswith("http://"):
                    raise ValueError(f"HTTPS 전용: http:// 차단됨 → {request.url[:60]}")
                return super().send(request, *args, **kwargs)

        _retry = Retry(total=3, backoff_factor=0.5,
                       status_forcelist=[429, 500, 502, 503, 504])
        _adapter = _HttpsOnlyAdapter(max_retries=_retry)

        import requests
        _session = requests.Session()
        _session.mount("https://", _adapter)
        # http:// 는 아예 연결 거부
        _session.mount("http://", _HttpsOnlyAdapter())

        # 모듈 수준 세션 패치 (duckduckgo_search 등도 적용)
        requests.Session = lambda: _session  # type: ignore
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
#  메모리 보안: 민감 문자열 제거
# ══════════════════════════════════════════════════════════════════

def wipe_string(s: str) -> None:
    """
    CPython 에서 문자열 내부 버퍼를 0으로 덮어씀.
    완전한 보장은 없지만 메모리 덤프에서의 노출 위험 감소.
    """
    try:
        import ctypes
        if isinstance(s, str):
            # PyUnicodeObject의 내부 데이터 영역 덮어쓰기
            ctypes.memset(id(s) + 48, 0, len(s) * 2)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
#  스크린 보안: 설정 화면 캡처 차단
# ══════════════════════════════════════════════════════════════════

def set_screen_secure(enabled: bool = True):
    """설정 화면에서 스크린샷/화면 캡처 차단 (Android)"""
    if not _IS_ANDROID:
        return
    try:
        from jnius import autoclass
        LayoutParams = autoclass("android.view.WindowManager$LayoutParams")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        window = activity.getWindow()
        if enabled:
            window.addFlags(LayoutParams.FLAG_SECURE)
        else:
            window.clearFlags(LayoutParams.FLAG_SECURE)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
#  종합 보안 점검
# ══════════════════════════════════════════════════════════════════

def run_security_check() -> SecurityReport:
    """앱 시작 시 한 번 실행되는 종합 보안 점검"""
    warnings = []
    rooted   = False
    emulator = False
    dev_mode = False

    if _IS_ANDROID:
        rooted,   root_warns = _check_root_android()
        emulator, emu_warns  = _check_emulator()
        dev_mode             = _check_dev_mode()
        warnings.extend(root_warns + emu_warns)
        if dev_mode:
            warnings.append("개발자 모드 활성화 (USB 디버깅 가능)")

    # 위험도 산정
    if rooted and emulator:
        risk = "high"
    elif rooted:
        risk = "high"
    elif emulator or dev_mode:
        risk = "medium"
    else:
        risk = "low"

    report = SecurityReport(
        is_rooted=rooted,
        is_emulator=emulator,
        is_dev_mode=dev_mode,
        risk_level=risk,
        warnings=warnings,
    )
    _log.info("Security check: risk=%s, warnings=%d", risk, len(warnings))
    return report
