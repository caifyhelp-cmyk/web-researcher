[app]

# ── 앱 정보 ─────────────────────────────────────────────────────
title        = MAESTRO
package.name = maestro
package.domain = com.maestro.app
version      = 2.1.0

# ── 소스 ────────────────────────────────────────────────────────
source.dir   = .
source.include_exts = py,png,jpg,kv,atlas,json,db

# 상위 디렉터리의 마에스트로 핵심 파일 포함
source.include_patterns =
    ../maestro.py,
    ../orchestrator.py,
    ../personalizer.py,
    ../updater.py,
    ../web_researcher.py,
    ../pattern_collector.py,
    ../feedback_collector.py,
    mobile_updater.py,
    secure_storage.py,
    security_guard.py,
    maestro_mobile.py

# ── 의존성 ──────────────────────────────────────────────────────
# 주의: fastapi, uvicorn 제거 (서버 없는 아키텍처)
# cryptography: 키 암호화 필수
requirements =
    python3==3.11.9,
    kivy==2.3.0,
    cryptography==43.0.3,
    openai==1.50.0,
    anthropic==0.34.0,
    requests==2.32.3,
    urllib3==2.2.3,
    certifi,
    duckduckgo_search==6.2.0,
    rich==13.7.0,
    pillow==10.4.0,
    charset-normalizer

# ── Android 설정 ────────────────────────────────────────────────

# 최소 권한 (INTERNET 만 — 저장소 권한 없음, 앱 전용 내부 저장소 사용)
android.permissions = INTERNET

# API 레벨
android.api    = 34
# Android 8.0 Oreo 이상 (ANDROID_ID 신뢰성 보장)
android.minapi = 26
android.ndk    = 25b
android.sdk    = 34
android.accept_sdk_license = True

# 아키텍처 (ARM64 + ARMv7 = 사실상 모든 기기 커버)
android.archs  = arm64-v8a, armeabi-v7a

# 앱 메타
android.app_name_label = MAESTRO AI

# 네트워크 보안 설정 (HTTPS 전용 강제, cleartext 금지)
android.add_aars =
android.manifest.attributes = android:usesCleartextTraffic="false"

# 백업 비활성화 (키 파일이 클라우드 백업되면 보안 위험)
android.add_activities_to_manifest =
android.extra_manifest_application_arguments = android:allowBackup="false" android:fullBackupContent="false"

# GradleKV 설정
android.gradle_dependencies =

# Release 빌드 서명 (GitHub Actions 에서 keystore 환경변수로 설정됨)
# android.keystore = %(KEYSTORE_FILE)s
# android.keystore_alias = maestro
# android.keystore_passwd = %(KEYSTORE_PASS)s
# android.keystore_alias_passwd = %(KEYSTORE_PASS)s

# ── 앱 아이콘 / 스플래시 ──────────────────────────────────────────
# icon.filename    = %(source.dir)s/assets/icon.png
# presplash.filename = %(source.dir)s/assets/splash.png
presplash.color  = #0D1117

# ── 앱 오리엔테이션 ────────────────────────────────────────────────
orientation = portrait

# 풀스크린
fullscreen = 0

# ── Entrypoint ───────────────────────────────────────────────────
android.entrypoint = org.kivy.android.PythonActivity

[buildozer]
log_level = 2
warn_on_root = 1
build_dir    = .buildozer
bin_dir      = bin
