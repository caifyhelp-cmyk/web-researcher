# -*- coding: utf-8 -*-
"""
MAESTRO 집단지성 파이프라인

사용자 대화에서 좋은 아이디어/패턴/로직을 추출하여
knowledge_base.json에 축적 → MAESTRO 시스템 프롬프트 자동 반영.

흐름:
  암호화 대화 로그 → GPT-4o-mini 분석 → 패턴 추출
  → knowledge_base.json 저장
  → 조경일 큐레이션(승인/거부)
  → MAESTRO 시스템 프롬프트에 반영
"""

import os, json, re
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).parent
_KB_PATH = _HERE / "knowledge_base.json"
_PENDING_PATH = _HERE / "knowledge_pending.json"

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")


# ══════════════════════════════════════════════
#  knowledge_base 로드/저장
# ══════════════════════════════════════════════

def load_kb() -> dict:
    """승인된 지식 베이스 로드"""
    if _KB_PATH.exists():
        try:
            return json.loads(_KB_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"patterns": [], "ideas": [], "workflows": [], "updated_at": ""}


def save_kb(kb: dict):
    kb["updated_at"] = datetime.now().isoformat()
    _KB_PATH.write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8")


def load_pending() -> list:
    """검토 대기 중인 패턴 로드"""
    if _PENDING_PATH.exists():
        try:
            return json.loads(_PENDING_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_pending(items: list):
    _PENDING_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


# ══════════════════════════════════════════════
#  대화에서 패턴 추출
# ══════════════════════════════════════════════

def extract_patterns(topic: str, conversation: str, score: int) -> list:
    """
    대화에서 좋은 아이디어/패턴/로직을 추출.
    점수 3 이상 대화만 분석 (좋은 경험에서만 추출).
    """
    if score < 3:
        return []
    if not OPENAI_KEY:
        return []

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_KEY)

        prompt = f"""아래 대화에서 다른 사용자들에게도 도움이 될 만한 좋은 아이디어, 활용 패턴, 효과적인 요청 방식을 추출하세요.

주제: {topic}
대화:
{conversation[:3000]}

추출 기준:
- 창의적인 활용 방식
- 효과적인 문제 해결 접근
- 다른 사용자도 참고할 만한 사고방식
- 좋은 요청 패턴 (어떻게 요청하면 좋은 결과가 나왔는지)

반드시 아래 JSON 형식으로만 출력:
{{
  "patterns": [
    {{
      "type": "활용패턴|아이디어|요청방식|사고로직",
      "summary": "한 줄 요약",
      "detail": "구체적 내용 (2-3문장)",
      "example": "실제 사용 예시"
    }}
  ]
}}

패턴이 없으면: {{"patterns": []}}"""

        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3
        )
        raw = r.choices[0].message.content.strip()
        m = re.search(r'\{[\s\S]+\}', raw)
        if m:
            data = json.loads(m.group())
            return data.get("patterns", [])
    except Exception:
        pass
    return []


# ══════════════════════════════════════════════
#  패턴 → 대기열 추가
# ══════════════════════════════════════════════

def add_to_pending(patterns: list, topic: str):
    """추출된 패턴을 검토 대기열에 추가"""
    if not patterns:
        return
    pending = load_pending()
    for p in patterns:
        p["source_topic"] = topic
        p["extracted_at"] = datetime.now().isoformat()
        p["status"] = "pending"
        pending.append(p)
    save_pending(pending)


# ══════════════════════════════════════════════
#  큐레이션 CLI (조경일 전용)
# ══════════════════════════════════════════════

def curate_pending():
    """대기 중인 패턴을 검토하고 승인/거부"""
    pending = load_pending()
    if not pending:
        print("검토할 패턴이 없습니다.")
        return

    kb = load_kb()
    approved_count = 0
    remaining = []

    for item in pending:
        if item.get("status") != "pending":
            continue
        print("\n" + "="*60)
        print(f"[{item['type']}] {item['summary']}")
        print(f"내용: {item['detail']}")
        print(f"예시: {item.get('example', '')}")
        print(f"출처 주제: {item.get('source_topic', '')}")
        print("-"*60)
        choice = input("승인(y) / 거부(n) / 나중에(s): ").strip().lower()

        if choice == "y":
            item["status"] = "approved"
            kb["patterns"].append(item)
            approved_count += 1
            print("  승인됨")
        elif choice == "s":
            remaining.append(item)
        else:
            print("  거부됨")

    save_kb(kb)
    save_pending(remaining)
    print(f"\n완료. 승인: {approved_count}개, 대기: {len(remaining)}개")


# ══════════════════════════════════════════════
#  MAESTRO 시스템 프롬프트 확장 텍스트 생성
# ══════════════════════════════════════════════

def build_knowledge_prompt() -> str:
    """
    승인된 패턴을 시스템 프롬프트에 삽입할 텍스트로 변환.
    MAESTRO가 임포트 시 자동 호출.
    """
    kb = load_kb()
    patterns = kb.get("patterns", [])
    if not patterns:
        return ""

    lines = ["\n## 사용자들의 효과적인 활용 패턴 (집단지성)"]
    lines.append("아래는 실제 사용자들이 발견한 효과적인 방식들입니다.")
    lines.append("사용자가 비슷한 상황에 처했을 때 자연스럽게 참고하여 안내하세요.\n")

    by_type: dict = {}
    for p in patterns[-30:]:  # 최근 30개만
        t = p.get("type", "기타")
        by_type.setdefault(t, []).append(p)

    for t, items in by_type.items():
        lines.append(f"### {t}")
        for item in items[:5]:
            lines.append(f"- {item['summary']}: {item['detail']}")

    return "\n".join(lines)


# ══════════════════════════════════════════════
#  전체 파이프라인 (feedback_collector에서 호출)
# ══════════════════════════════════════════════

def process_conversation(topic: str, conversation: str, score: int):
    """대화 처리 → 패턴 추출 → 대기열 추가"""
    patterns = extract_patterns(topic, conversation, score)
    if patterns:
        add_to_pending(patterns, topic)
        print(f"  [집단지성] {len(patterns)}개 패턴 추출 → 검토 대기열 추가")


if __name__ == "__main__":
    # python pattern_collector.py 로 큐레이션 실행
    curate_pending()
