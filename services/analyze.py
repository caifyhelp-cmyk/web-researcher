# -*- coding: utf-8 -*-
"""
회의 내용 분석 — GPT-4.1 로 구조화된 회의록 생성

출력 구조:
  - 회의 제목 (자동 추출)
  - 참석자 목록
  - 주요 안건 (번호 목록)
  - 결정 사항 (번호 목록)
  - 액션 아이템 (담당자 + 기한 포함)
  - 다음 회의 예정일 (텍스트에서 감지 시)
  - 전체 요약 (3~5문장)
"""
import os
import json
from datetime import date


def analyze_meeting(labeled_transcript: str, meeting_date: str = "") -> dict:
    """
    화자 분리된 전사 텍스트를 분석해 구조화된 회의록 딕셔너리 반환.

    Args:
        labeled_transcript: "화자: 발화내용\\n..." 형식
        meeting_date: "2026-04-19" 형식 (없으면 오늘 날짜)

    Returns:
        {
            "title": str,
            "date": str,
            "attendees": [str, ...],
            "agenda": [str, ...],
            "decisions": [str, ...],
            "action_items": [{"task": str, "owner": str, "due": str}, ...],
            "next_meeting": str,
            "summary": str,
        }
    """
    import openai

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return _fallback_structure(labeled_transcript, meeting_date)

    if not meeting_date:
        meeting_date = date.today().isoformat()

    prompt = f"""다음 회의 전사록을 분석해 JSON으로 반환하세요.

[회의 날짜]: {meeting_date}
[전사록]:
{labeled_transcript[:8000]}

반드시 아래 JSON 형식으로만 출력 (마크다운 코드블록 없이):
{{
  "title": "회의 제목 (맥락에서 추출)",
  "date": "{meeting_date}",
  "attendees": ["참석자1", "참석자2"],
  "agenda": ["안건1", "안건2"],
  "decisions": ["결정사항1", "결정사항2"],
  "action_items": [
    {{"task": "할 일", "owner": "담당자", "due": "기한(없으면 빈 문자열)"}},
  ],
  "next_meeting": "다음 회의 일정 (없으면 빈 문자열)",
  "summary": "3~5문장 요약"
}}"""

    client = openai.OpenAI(api_key=api_key)
    try:
        r = client.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
            temperature=0.2
        )
        raw = r.choices[0].message.content.strip()
        # JSON 추출
        import re
        m = re.search(r'\{[\s\S]+\}', raw)
        if m:
            return json.loads(m.group())
    except Exception:
        pass

    return _fallback_structure(labeled_transcript, meeting_date)


def _fallback_structure(transcript: str, meeting_date: str) -> dict:
    """API 실패 시 기본 구조 반환"""
    if not meeting_date:
        meeting_date = date.today().isoformat()
    return {
        "title": f"{meeting_date} 회의",
        "date": meeting_date,
        "attendees": [],
        "agenda": [],
        "decisions": [],
        "action_items": [],
        "next_meeting": "",
        "summary": transcript[:500]
    }
