# -*- coding: utf-8 -*-
"""
고객 피드백 수집기

- 대화 전체 : 로컬 암호화 저장 (비공개, 절대 외부 전송 안 됨)
- 추출 인사이트: GitHub Issues 자동 생성 (조경일 리뷰용)
  → 불편함 / 원하는 기능 / 혼란 포인트 / 긍정 피드백
  → 개인 식별 정보 없음
"""

import os, json, hashlib, urllib.request, urllib.error
from datetime import datetime

# ── 경로 설정 ─────────────────────────────────────────────────────
_HERE      = os.path.dirname(os.path.abspath(__file__))
_LOG_DIR   = os.path.join(_HERE, "encrypted_logs")
_KEY_FILE  = os.path.join(_HERE, ".enc_key")          # gitignore 대상

# ── GitHub 설정 ───────────────────────────────────────────────────
_GH_REPO   = "caifyhelp-cmyk/web-researcher"
_GH_LABEL  = "customer-insight"
_GH_API    = f"https://api.github.com/repos/{_GH_REPO}"


# ══════════════════════════════════════════════
#  암호화 키 관리
# ══════════════════════════════════════════════

def _get_fernet():
    """Fernet 인스턴스 반환. 키 없으면 생성."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None

    if not os.path.exists(_KEY_FILE):
        key = Fernet.generate_key()
        with open(_KEY_FILE, "wb") as f:
            f.write(key)
    else:
        with open(_KEY_FILE, "rb") as f:
            key = f.read().strip()
    return Fernet(key)


def encrypt_and_save(topic: str, conversation: list, score: int = 0) -> str:
    """
    대화 전체를 암호화해서 로컬에 저장.
    외부 전송 없음. 반환값: 저장된 파일 경로 (없으면 빈 문자열)
    """
    fernet = _get_fernet()
    if not fernet:
        return ""

    os.makedirs(_LOG_DIR, exist_ok=True)

    payload = json.dumps({
        "topic":        topic,
        "score":        score,
        "timestamp":    datetime.now().isoformat(),
        "conversation": conversation,
    }, ensure_ascii=False)

    encrypted = fernet.encrypt(payload.encode("utf-8"))

    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    topic_hash = hashlib.md5(topic.encode()).hexdigest()[:8]
    path     = os.path.join(_LOG_DIR, f"{ts}_{topic_hash}.enc")
    with open(path, "wb") as f:
        f.write(encrypted)

    return path


def decrypt_log(path: str) -> dict:
    """암호화된 로그 파일 복호화 (개발자용)."""
    fernet = _get_fernet()
    if not fernet:
        return {}
    with open(path, "rb") as f:
        data = fernet.decrypt(f.read())
    return json.loads(data.decode("utf-8"))


# ══════════════════════════════════════════════
#  인사이트 추출 (GPT)
# ══════════════════════════════════════════════

def extract_insights(topic: str, conversation: list, score: int,
                     needs_used: list, useful_needs: list, bad_needs: list) -> dict:
    """
    대화 내용에서 개선 인사이트만 추출.
    개인 식별 정보 없이 패턴만 추출.
    """
    try:
        from openai import OpenAI
        oai = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
        if not oai:
            return _fallback_insights(score, useful_needs, bad_needs)
    except Exception:
        return _fallback_insights(score, useful_needs, bad_needs)

    # 대화 텍스트 구성 (마지막 10턴만, 너무 길지 않게)
    conv_text = "\n".join(
        f"[{'사용자' if m['role'] == 'user' else '어시스턴트'}]: {m['content'][:200]}"
        for m in conversation[-10:]
    )

    prompt = f"""웹 리서치 앱 사용 세션을 분석해서 제품 개선 인사이트를 추출하세요.

[리서치 주제]: {topic}
[만족도]: {score}/5
[사용된 추출 항목]: {', '.join(needs_used)}
[유용했던 항목]: {', '.join(useful_needs) if useful_needs else '없음'}
[불필요했던 항목]: {', '.join(bad_needs) if bad_needs else '없음'}

[대화 일부]:
{conv_text if conv_text else '(대화 없음)'}

다음 4가지만 추출하세요. 개인 식별 정보 절대 포함 금지.
JSON만 출력:
{{
  "pain_points": ["불편했던 점 1", "불편했던 점 2"],
  "feature_requests": ["원하는 기능 1", "원하는 기능 2"],
  "confusion_points": ["헷갈렸던 부분 1"],
  "positive_feedback": ["좋았던 점 1", "좋았던 점 2"]
}}

없으면 빈 배열 []. 추측 금지, 대화/피드백에 명시된 것만."""

    try:
        r = oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600, temperature=0.3
        )
        import re
        raw = r.choices[0].message.content.strip()
        m = re.search(r'\{[\s\S]+\}', raw)
        if m:
            return json.loads(m.group())
    except Exception:
        pass

    return _fallback_insights(score, useful_needs, bad_needs)


def _fallback_insights(score: int, useful_needs: list, bad_needs: list) -> dict:
    """GPT 호출 실패 시 피드백 데이터만으로 구성"""
    return {
        "pain_points":      [f"불필요 항목: {n}" for n in bad_needs],
        "feature_requests": [],
        "confusion_points": [],
        "positive_feedback": [f"유용 항목: {n}" for n in useful_needs],
    }


# ══════════════════════════════════════════════
#  GitHub Issues 전송
# ══════════════════════════════════════════════

def push_to_github(topic: str, research_type: str, score: int,
                   insights: dict, models_used: dict = None) -> str:
    """
    추출된 인사이트를 GitHub Issue로 생성.
    반환: issue URL (실패 시 빈 문자열)
    """
    token = os.getenv("GITHUB_DATA_TOKEN", "")
    if not token:
        return ""

    rtype_label = {
        "competitor": "경쟁사 조사", "news": "뉴스 트렌드",
        "institution": "기관 분석",  "general": "일반 조사"
    }.get(research_type, research_type)

    score_emoji = {1: "😞", 2: "😕", 3: "😐", 4: "😊", 5: "😄"}.get(score, "")

    def _list_md(items):
        if not items:
            return "_없음_"
        return "\n".join(f"- {it}" for it in items)

    models_md = ""
    if models_used:
        models_md = "\n".join(f"| {cat} | `{m}` |" for cat, m in models_used.items())
        models_md = f"\n### 사용 모델\n| 카테고리 | 모델 |\n|---|---|\n{models_md}"

    body = f"""## 세션 요약
| 항목 | 내용 |
|---|---|
| 리서치 주제 | {topic} |
| 조사 유형 | {rtype_label} |
| 만족도 | {score_emoji} {score}/5 |
| 수집 일시 | {datetime.now().strftime('%Y-%m-%d %H:%M')} |
{models_md}

---

### 불편했던 점
{_list_md(insights.get('pain_points', []))}

### 원하는 기능
{_list_md(insights.get('feature_requests', []))}

### 헷갈렸던 부분
{_list_md(insights.get('confusion_points', []))}

### 좋았던 점
{_list_md(insights.get('positive_feedback', []))}

---
_자동 수집 — 개인 식별 정보 없음_"""

    score_tag = "low" if score <= 2 else ("mid" if score == 3 else "high")
    # 제목에 태그 포함 (라벨 대신 필터링용)
    title = f"[feedback/{score_tag}/{score}점] [{rtype_label}] {topic[:35]}"

    data = json.dumps({
        "title": title,
        "body":  body,
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        f"{_GH_API}/issues", data=data, method="POST",
        headers={
            "Authorization":  f"token {token}",
            "Content-Type":   "application/json",
            "Accept":         "application/vnd.github.v3+json",
            "User-Agent":     "web-researcher-feedback",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            return result.get("html_url", "")
    except Exception as e:
        return ""


# ══════════════════════════════════════════════
#  메인 진입점 — 세션 종료 시 한 번 호출
# ══════════════════════════════════════════════

def process_session(topic: str, research_type: str, plan: dict, analysis: dict,
                    conversation: list, score: int,
                    useful_needs: list, bad_needs: list,
                    models_used: dict) -> dict:
    """
    세션 종료 후 전체 처리:
    1. 대화 암호화 저장 (로컬)
    2. 인사이트 추출 (GPT)
    3. GitHub Issue 전송

    반환: {"log_path": "...", "issue_url": "...", "insights": {...}}
    """
    result = {"log_path": "", "issue_url": "", "insights": {}}

    # 1. 암호화 저장
    if conversation:
        result["log_path"] = encrypt_and_save(topic, conversation, score)

    # 2. 인사이트 추출 (대화 없어도 피드백 데이터로 가능)
    needs_used = analysis.get("needs", plan.get("needs", []))
    insights   = extract_insights(
        topic=topic, conversation=conversation, score=score,
        needs_used=needs_used, useful_needs=useful_needs, bad_needs=bad_needs
    )
    result["insights"] = insights

    # 3. GitHub 전송 (인사이트가 있을 때만)
    has_content = any(insights.get(k) for k in
                      ("pain_points", "feature_requests", "confusion_points", "positive_feedback"))
    if has_content:
        result["issue_url"] = push_to_github(
            topic=topic, research_type=research_type,
            score=score, insights=insights, models_used=models_used
        )

    # 4. 집단지성 파이프라인 — 좋은 패턴 추출 (점수 3 이상)
    if score >= 3 and conversation:
        try:
            import pattern_collector as _pc
            conv_text = "\n".join(
                f"{'사용자' if m.get('role')=='user' else '어시스턴트'}: {m.get('content','')}"
                for m in conversation if isinstance(m, dict)
            ) if conversation and isinstance(conversation[0], dict) else str(conversation)
            _pc.process_conversation(topic, conv_text, score)
        except Exception:
            pass

    return result
