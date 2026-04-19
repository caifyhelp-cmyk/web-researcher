# -*- coding: utf-8 -*-
"""
MAESTRO 개인 맞춤화 엔진

역할:
  1. ~/.maestro/custom.json 로드/저장
  2. 대화 중 사용자 선호도 실시간 감지
  3. 시스템 프롬프트에 개인화 레이어 추가
  4. 오케스트레이터 모델 오버라이드

custom.json 구조:
  user_hash          : 익명 머신 ID (개인식별 불가)
  system_prompt_extras: 시스템 프롬프트에 추가할 규칙
  model_overrides    : {category: model} — 오케스트레이터 DB보다 우선
  response_style     : concise / balanced / detailed
  domain_expertise   : ["marketing", "ecommerce", ...] 사용자 전문 분야
  liked_patterns     : 더 많이 해줬으면 하는 것들
  disliked_patterns  : 하지 말아야 할 것들
"""

import os, json, hashlib, re
from pathlib import Path
from datetime import datetime

_CUSTOM_PATH = Path(os.path.expanduser("~")) / ".maestro" / "custom.json"
_CUSTOM_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── 선호 감지 패턴 ──────────────────────────────────────────────
_PREF_PATTERNS = [
    # 응답 스타일
    (r"(항상|매번|앞으로).*(표|테이블|table)\s*(형식|으로)",     "output_format", "table"),
    (r"(항상|앞으로).*(bullet|불릿|목록|리스트)\s*(형식|으로)", "output_format", "bullet"),
    (r"(짧게|간결하게|간단하게).*(답해|말해|응답)",              "response_style", "concise"),
    (r"(자세하게|상세하게|길게).*(답해|말해|설명)",              "response_style", "detailed"),
    (r"(반말|편하게|캐주얼하게)",                                "language_formality", "casual"),
    (r"(존댓말|격식있게|공식적으로)",                            "language_formality", "formal"),
    # 도메인
    (r"(나는|저는|우리는).{0,10}(마케팅|marketing)",            "domain_expertise", "marketing"),
    (r"(나는|저는|우리는).{0,10}(이커머스|쇼핑몰|e-commerce)",  "domain_expertise", "ecommerce"),
    (r"(나는|저는|우리는).{0,10}(스타트업|startup)",            "domain_expertise", "startup"),
    (r"(나는|저는|우리는).{0,10}(개발자|프로그래머|developer)", "domain_expertise", "developer"),
    (r"(나는|저는|우리는).{0,10}(디자이너|designer)",           "domain_expertise", "designer"),
    (r"(나는|저는|우리는).{0,10}(컨설턴트|consultant)",         "domain_expertise", "consultant"),
    # 싫어하는 패턴
    (r"(너무|지나치게).*(길어|많아|장황)",                       "disliked", "long_responses"),
    (r"(영어|english).*(쓰지|말고|금지)",                        "disliked", "english_output"),
    (r"(요약|정리).*(말고|빼고|필요없어)",                        "disliked", "summary_endings"),
]

# GPT가 감지할 선호 추출 프롬프트
_DETECT_PROMPT = """사용자 발언에서 MAESTRO에 대한 응답 선호도나 개인 설정을 추출하세요.

[사용자 발언]: {utterance}

아래 항목 중 해당하는 것만 JSON으로 반환. 없으면 {{}}.
{{
  "system_prompt_extra": "시스템 프롬프트에 추가할 규칙 (없으면 생략)",
  "response_style": "concise/balanced/detailed 중 하나 (없으면 생략)",
  "output_format": "table/bullet/prose/auto 중 하나 (없으면 생략)",
  "language_formality": "formal/casual 중 하나 (없으면 생략)",
  "domain_expertise": "분야명 (없으면 생략)",
  "model_override": {{"category": "모델명"}} // 특정 모델 선호 시 (없으면 생략)
}}

선호가 전혀 없으면 반드시 {{}} 만 반환."""


# ══════════════════════════════════════════════
#  custom.json 로드/저장
# ══════════════════════════════════════════════

def _make_user_hash() -> str:
    """익명 머신 ID 생성 (개인식별 불가)"""
    try:
        import uuid
        mid = str(uuid.getnode())
    except Exception:
        mid = os.path.expanduser("~")
    return hashlib.sha256(mid.encode()).hexdigest()[:16]


def load_custom() -> dict:
    """개인 설정 로드 (없으면 기본값 반환)"""
    default = {
        "version": 1,
        "user_hash": _make_user_hash(),
        "created_at": datetime.now().isoformat()[:10],
        "updated_at": datetime.now().isoformat()[:10],
        "system_prompt_extras": [],
        "model_overrides": {},
        "response_style": "balanced",
        "output_format": "auto",
        "language_formality": "formal",
        "domain_expertise": [],
        "liked_patterns": [],
        "disliked_patterns": [],
    }
    try:
        if _CUSTOM_PATH.exists():
            saved = json.loads(_CUSTOM_PATH.read_text(encoding="utf-8"))
            default.update(saved)
    except Exception:
        pass
    return default


def save_custom(custom: dict):
    """개인 설정 저장"""
    custom["updated_at"] = datetime.now().isoformat()[:10]
    _CUSTOM_PATH.write_text(
        json.dumps(custom, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ══════════════════════════════════════════════
#  시스템 프롬프트 개인화 레이어 생성
# ══════════════════════════════════════════════

def build_personalized_prompt(custom: dict) -> str:
    """
    custom.json을 읽어 시스템 프롬프트에 추가할 개인화 섹션 생성.
    메인 시스템 프롬프트 끝에 덧붙임.
    """
    parts = []

    # 도메인 전문성
    domains = custom.get("domain_expertise", [])
    if domains:
        parts.append(f"이 사용자는 {', '.join(domains)} 분야 전문가입니다. "
                     f"해당 분야 맥락으로 답변하세요.")

    # 응답 스타일
    style = custom.get("response_style", "balanced")
    if style == "concise":
        parts.append("응답은 핵심만 간결하게. 불필요한 설명 생략.")
    elif style == "detailed":
        parts.append("응답은 상세하게. 근거와 예시를 풍부하게 포함.")

    # 출력 형식
    fmt = custom.get("output_format", "auto")
    if fmt == "table":
        parts.append("비교·목록 정보는 항상 표(markdown table) 형식으로.")
    elif fmt == "bullet":
        parts.append("항목 나열은 항상 bullet point로.")

    # 언어 격식
    formality = custom.get("language_formality", "formal")
    if formality == "casual":
        parts.append("반말로 편하게 대화하세요.")

    # 싫어하는 패턴
    dislikes = custom.get("disliked_patterns", [])
    if "long_responses" in dislikes:
        parts.append("응답이 길어지지 않도록 주의.")
    if "english_output" in dislikes:
        parts.append("영어 단어 최소화. 가능한 한국어 표현 사용.")
    if "summary_endings" in dislikes:
        parts.append("응답 끝에 요약 반복하지 말 것.")

    # 사용자 정의 추가 규칙
    extras = custom.get("system_prompt_extras", [])
    parts.extend(extras)

    if not parts:
        return ""

    return "\n\n---\n## 이 사용자 맞춤 설정\n" + "\n".join(f"- {p}" for p in parts)


# ══════════════════════════════════════════════
#  실시간 선호 감지
# ══════════════════════════════════════════════

def detect_preference_fast(utterance: str) -> dict:
    """정규식 기반 빠른 선호 감지 (API 호출 없음)"""
    updates = {}
    for pattern, key, value in _PREF_PATTERNS:
        if re.search(pattern, utterance, re.IGNORECASE):
            if key == "domain_expertise":
                updates.setdefault("domain_expertise_add", []).append(value)
            elif key == "disliked":
                updates.setdefault("disliked_patterns_add", []).append(value)
            else:
                updates[key] = value
    return updates


def detect_preference_gpt(utterance: str, oai_client) -> dict:
    """GPT-4.1-mini 기반 정밀 선호 감지"""
    if not oai_client:
        return {}
    try:
        r = oai_client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user",
                       "content": _DETECT_PROMPT.format(utterance=utterance[:500])}],
            max_tokens=200,
            temperature=0.1
        )
        raw = r.choices[0].message.content.strip()
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    return {}


def apply_preference_updates(custom: dict, updates: dict) -> tuple[dict, list]:
    """
    감지된 선호를 custom.json에 반영.

    Returns:
        (updated_custom, changed_descriptions)
    """
    changed = []

    for key in ("response_style", "output_format", "language_formality"):
        if key in updates:
            old = custom.get(key)
            new = updates[key]
            if old != new:
                custom[key] = new
                changed.append(f"{key}: {old} → {new}")

    if "system_prompt_extra" in updates and updates["system_prompt_extra"]:
        rule = updates["system_prompt_extra"]
        if rule not in custom.get("system_prompt_extras", []):
            custom.setdefault("system_prompt_extras", []).append(rule)
            changed.append(f"규칙 추가: {rule[:40]}")

    for d in updates.get("domain_expertise_add", []):
        if d not in custom.get("domain_expertise", []):
            custom.setdefault("domain_expertise", []).append(d)
            changed.append(f"도메인 추가: {d}")

    for d in updates.get("disliked_patterns_add", []):
        if d not in custom.get("disliked_patterns", []):
            custom.setdefault("disliked_patterns", []).append(d)
            changed.append(f"기피 패턴 추가: {d}")

    if "model_override" in updates:
        for cat, model in updates["model_override"].items():
            custom.setdefault("model_overrides", {})[cat] = model
            changed.append(f"모델 오버라이드: {cat} → {model}")

    return custom, changed


def get_model_override(custom: dict, category: str) -> str | None:
    """오케스트레이터 DB보다 우선하는 사용자 모델 선호 반환"""
    return custom.get("model_overrides", {}).get(category)
