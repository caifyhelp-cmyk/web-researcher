# -*- coding: utf-8 -*-
"""
MAESTRO 집단지성 파이프라인

사용자 대화에서 좋은 아이디어/패턴/로직을 추출 → GitHub 집중 → 큐레이션 → MAESTRO 반영.

흐름:
  암호화 대화 로그 → PII 제거 → GPT-4o-mini 패턴 추출
  → knowledge_pending.json → GitHub 자동 푸시
  → 조경일 큐레이션 (python pattern_collector.py)
  → knowledge_base.json → MAESTRO 시스템 프롬프트 자동 반영

개인정보 보호:
  - 실제 대화: 암호화 로컬 저장, 절대 외부 전송 안 됨
  - 패턴 추출 전 PII 필터링 (이름/번호/이메일/주소 제거)
  - GitHub에는 행동 패턴만 저장, 개인 식별 불가
"""

import os, json, re, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).parent
_KB_PATH      = _HERE / "knowledge_base.json"
_PENDING_PATH = _HERE / "knowledge_pending.json"

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
_GH_TOKEN  = (os.getenv("GITHUB_TOKEN", "") or os.getenv("GH_TOKEN", "")
              or os.getenv("GITHUB_DATA_TOKEN", ""))
_GH_REPO   = "caifyhelp-cmyk/web-researcher"
_GH_BRANCH = "master"


# ══════════════════════════════════════════════
#  PII 필터링 — 개인정보 제거 후 패턴 추출
# ══════════════════════════════════════════════

_PII_PATTERNS = [
    (r'\b\d{3}[-.\s]?\d{4}[-.\s]?\d{4}\b', '[전화번호]'),       # 전화번호
    (r'\b\d{6}[-]\d{7}\b', '[주민번호]'),                         # 주민등록번호
    (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[이메일]'),  # 이메일
    (r'\b(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주).{0,20}(?:구|동|로|길)\s*\d+', '[주소]'),  # 주소
    (r'\b\d{3}-\d{2}-\d{5}\b', '[사업자번호]'),                   # 사업자번호
    (r'(?:이름|성함|name)\s*[:：]\s*\S+', '[이름]'),               # 이름 필드
]

def _remove_pii(text: str) -> str:
    """개인식별정보 제거"""
    for pattern, replacement in _PII_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


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

def _gh_api(method: str, path: str, data: dict = None) -> dict:
    """GitHub API 호출"""
    url  = f"https://api.github.com/repos/{_GH_REPO}/{path}"
    body = json.dumps(data, ensure_ascii=False).encode() if data else None
    req  = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"token {_GH_TOKEN}",
        "Content-Type":  "application/json",
        "Accept":        "application/vnd.github.v3+json",
        "User-Agent":    "maestro-pattern-collector",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": str(e), "body": e.read().decode()}
    except Exception as e:
        return {"error": str(e)}


def push_pending_to_github():
    """
    knowledge_pending.json을 GitHub에 푸시.
    모든 PC의 패턴이 GitHub 하나로 집중됨.
    """
    if not _GH_TOKEN:
        return False

    pending = load_pending()
    if not pending:
        return False

    import base64

    content = json.dumps(pending, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(content.encode()).decode()

    # 현재 파일의 SHA 가져오기 (업데이트 시 필요)
    existing = _gh_api("GET", f"contents/knowledge_pending.json")
    sha = existing.get("sha", "")

    payload = {
        "message": f"chore: 패턴 업데이트 ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
        "content": content_b64,
        "branch":  _GH_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    result = _gh_api("PUT", "contents/knowledge_pending.json", payload)
    return "content" in result


def pull_pending_from_github() -> bool:
    """
    GitHub의 knowledge_pending.json을 로컬로 가져옴.
    큐레이션 전 최신 상태 동기화.
    """
    if not _GH_TOKEN:
        return False
    try:
        import base64
        result = _gh_api("GET", "contents/knowledge_pending.json")
        if "content" in result:
            content = base64.b64decode(result["content"]).decode()
            items = json.loads(content)
            save_pending(items)
            return True
    except Exception:
        pass
    return False


def push_kb_to_github():
    """승인된 knowledge_base.json도 GitHub에 푸시 — 모든 PC가 공유"""
    if not _GH_TOKEN:
        return False
    try:
        import base64
        kb = load_kb()
        content = json.dumps(kb, ensure_ascii=False, indent=2)
        content_b64 = base64.b64encode(content.encode()).decode()

        existing = _gh_api("GET", "contents/knowledge_base.json")
        sha = existing.get("sha", "")

        payload = {
            "message": f"chore: 지식베이스 업데이트 ({datetime.now().strftime('%Y-%m-%d %H:%M')})",
            "content": content_b64,
            "branch":  _GH_BRANCH,
        }
        if sha:
            payload["sha"] = sha

        result = _gh_api("PUT", "contents/knowledge_base.json", payload)
        return "content" in result
    except Exception:
        return False


def pull_kb_from_github() -> bool:
    """GitHub의 knowledge_base.json을 로컬로 가져옴 — MAESTRO 시작 시 자동 호출"""
    if not _GH_TOKEN:
        return False
    try:
        import base64
        result = _gh_api("GET", "contents/knowledge_base.json")
        if "content" in result:
            content = base64.b64decode(result["content"]).decode()
            kb = json.loads(content)
            save_kb(kb)
            return True
    except Exception:
        pass
    return False


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

        # PII 제거 후 GPT 전송
        safe_conv = _remove_pii(conversation[:3000])

        prompt = f"""아래 대화에서 다른 사용자들에게도 도움이 될 만한 좋은 아이디어, 활용 패턴, 효과적인 요청 방식을 추출하세요.

주제: {topic}
대화:
{safe_conv}

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
    # GitHub에서 최신 패턴 가져오기 (모든 PC 패턴 통합)
    print("GitHub에서 최신 패턴 동기화 중...")
    pull_pending_from_github()

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

    # GitHub 업데이트 (큐레이션 결과 반영)
    if approved_count > 0:
        print("승인된 지식베이스 GitHub 동기화 중...")
        push_kb_to_github()
    if remaining or approved_count > 0:
        print("대기 목록 GitHub 동기화 중...")
        push_pending_to_github()


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
    """대화 처리 → 패턴 추출 → 대기열 추가 → GitHub 동기화"""
    patterns = extract_patterns(topic, conversation, score)
    if patterns:
        add_to_pending(patterns, topic)
        print(f"  [집단지성] {len(patterns)}개 패턴 추출 → 검토 대기열 추가")
        push_pending_to_github()  # 모든 PC의 패턴이 GitHub으로 집중


if __name__ == "__main__":
    # python pattern_collector.py 로 큐레이션 실행
    curate_pending()
