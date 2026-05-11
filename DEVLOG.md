# web-researcher (MAESTRO) 개발 로그

## 프로젝트 정보
- **목적**: MAESTRO AI 오케스트레이터 — 웹 리서치 + 뇌 에이전트 연동 개인화 AI
- **GitHub**: https://github.com/caifyhelp-cmyk/web-researcher
- **로컬 경로**: `C:\Users\조경일\web-researcher\`
- **Render 서비스 ID**: `srv-d7fka8navr4c73co6l8g`
- **배포 URL**: https://web-researcher-jpyx.onrender.com
- **Render 배포 트리거**: `curl -X POST -H "Authorization: Bearer rnd_z1EWKch9dQaCkbLfCdZpxFvqhvLZ" https://api.render.com/v1/services/srv-d7fka8navr4c73co6l8g/deploys`

## 연동
- 뇌 에이전트: https://brain-agent-v9wl.onrender.com/api/research
- GitHub Actions: master push → Render 자동 배포

## 주요 파일
| 파일 | 역할 |
|------|------|
| `app.py` | Streamlit 메인 |
| `maestro.py` | 오케스트레이터 코어 |
| `orchestrator.py` | 모델 선택 로직 |
| `knowledge_base.json` | 사용자 지식 베이스 |

---

## 개발 로그 (최신순)

<!-- 새 로그는 여기 위에 추가 -->

### [2026-05-11] v2.7.0 — 뇌 에이전트 연동 복구
- /api/ask → /api/research 전환
- Render 자동배포 활성화

### [2026-04-21] v2.8.x — 세션메모리 + 캐시 + brain-agent 연동
- 세션 종료 시 자동 진화 파이프라인 연결
- 바이브코딩 모드 추가 (방향키 선택 UI)
- Android APK 빌드 (Kivy + Buildozer + GitHub Actions)
