# MAESTRO 변경 이력

---

## v2.8.6 (2026-04-21)

### 버그 수정
- `_call_brain_full()` 함수 미존재 → NameError 수정  
  트리거 블록이 해당 함수를 호출하고 있었으나 정의가 없었음
- `patterns` 필드 타입 오류 수정  
  brain API가 반환하는 `patterns`는 `[{category, rules:[...]}]` 형태의 리스트인데  
  문자열 연결 시도로 TypeError 발생 → `_fmt_patterns()` 헬퍼 추가해 변환 처리
- `passass` 오타 → `pass` 수정
- 트리거 블록 내 문자열 리터럴에 CRLF가 삽입된 SyntaxError 수정

### 추가
- `_fmt_patterns(patterns_data)` 함수  
  `[{category, rules}]` 리스트를 `[카테고리]\n  - 원칙` 텍스트로 변환

---

## v2.8.5 (2026-04-21)

### 버그 수정 (세션 재개 후 발견)
- `_call_brain_full` 참조만 있고 정의 없음 → NameError
- 트리거 블록 내 unterminated string literal (CRLF 내장) → SyntaxError

### 변경
- `_call_brain()`: `patterns` 필드 파싱 추가 (brain API v2 대응)
- `_call_brain_full()`: 신규 생성 — 트리거 자동주입 전용, 시스템 프롬프트 포맷으로 반환
- `_brain_keepalive()`: 4분마다 brain agent API ping → Render 콜드 스타트 방지

---

## v2.8.4 (2026-04-21)

### 변경
- 시스템 프롬프트 전면 재작성  
  - 조경일 사고 3축 (외부 우선 / 자산 전환 / 구조 설계) 기반
  - CoT 지시 + Before/After 예시 포함
  - 응답 구조 강제: ①확인 → ②이유 → ③다음 행동
- `ask_brain` 트리거 키워드 대폭 확장 (마케팅 한정 → 판단/방향/전략 전반)
- GPT-4.1 메인 오케스트레이터 유지, Gemini `gemini-2.5-flash` → `gemini-2.5-pro`
- 응답 언어 평이화 (전문 용어 → 일상어)

---

## v2.8.3 (2026-04-20)

### 변경 (롤백됨)
- `_brain_local()` 로컬 DB 직접 조회 추가 → 전사 공용 앱이므로 API 호출 필수 원칙에 반해 제거

---

## v2.8.2 (2026-04-20)

### 변경
- 응답 최소 길이 가이드 추가 (v2.8.1 지나치게 짧아진 문제 보완)
- 3단계 응답 구조 의무화

---

## v2.8.1 (2026-04-20)

### 변경
- 시스템 프롬프트 평이어 규칙 추가
- 응답이 지나치게 짧아지는 부작용 발생 → v2.8.2에서 수정

---

## v2.8.0 (2026-04-20)

### 변경
- 시스템 프롬프트 1차 개선 (조경일 사고 패턴 반영 시작)
- ask_brain 트리거 확장 첫 번째 버전
- Gemini 모델 업그레이드

---

## brain-agent (병행 변경, 2026-04-21)

### 변경 (caifyhelp-cmyk/brain-agent)
- `agent.py`: `_get_relevant_patterns()` 반환 타입 `str` → `(str, list)` 튜플
  - 케이스스터디 패턴 필터링 추가 (`미흡/부재/실패로/과소평가` 제외)
  - `matched_patterns` 리스트를 `analyze()` 결과 딕셔너리에 포함
- `app.py`: `/api/research` 응답에 `patterns` 필드 추가
  - 형식: `[{category, rules:[...]}]` 카테고리별 최대 8개 원칙
  - 케이스스터디형 2차 필터링 적용
  - 블로그 생성 경로의 `_get_relevant_patterns` 호출도 튜플 언팩으로 수정
