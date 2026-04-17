# MAESTRO - AI 오케스트레이터

GPT-4o x Claude x DeepSeek x Grok x 뇌 에이전트  
웹 리서치, 코딩, 문서 분석, 이미지 생성, Vercel 배포까지 터미널 하나로.

---

## 노트북 / 새 PC 세팅

### 1. 클론
```bash
git clone https://github.com/caifyhelp-cmyk/web-researcher.git
cd web-researcher
```

### 2. 패키지 설치
```bash
pip install -r requirements_local.txt
```

### 3. API 키 설정
```
Windows: copy _local_keys_template.py _local_keys.py
Mac/Linux: cp _local_keys_template.py _local_keys.py
```
`_local_keys.py` 를 열어서 키 입력

| 키 | 발급 경로 |
|---|---|
| OPENAI_API_KEY | https://platform.openai.com/api-keys |
| ANTHROPIC_API_KEY | https://console.anthropic.com/ |
| DEEPSEEK_API_KEY | https://platform.deepseek.com/ |
| GROK_API_KEY | https://console.x.ai/ |
| GITHUB_DATA_TOKEN | https://github.com/settings/tokens (repo 권한 필요) |
| NAVER_CLIENT_ID/SECRET | https://developers.naver.com/ (검색 API) |
| VERCEL_TOKEN | https://vercel.com/account/tokens |

### 4. 실행
```bash
python maestro.py
```

---

## 주요 기능

| 기능 | 설명 |
|---|---|
| 웹 리서치 | 경쟁사 분석, 시장 조사, 트렌드 파악 → Excel/PDF/PPT 저장 |
| 파일/문서 분석 | PDF, Word, Excel, 이미지, CSV 모두 지원 |
| 코드 작성 | Claude Code 연동, 실제 파일 생성/수정/실행 |
| Vercel 배포 | 로컬 폴더 → 라이브 URL 즉시 발급 (무료) |
| 회의록 자동화 | 음성 파일 → STT → AI 분석 → Notion 자동 기록 |
| 이미지 생성 | DALL-E 3 |
| 집단지성 | 대화 패턴 자동 수집 → GitHub 동기화 |

## 자동 업데이트
앱 실행 시 GitHub에서 최신 버전을 자동 다운로드합니다.  
`version.txt` 기준으로 업데이트 여부를 판단합니다.
