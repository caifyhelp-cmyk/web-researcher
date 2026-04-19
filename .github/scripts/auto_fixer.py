# -*- coding: utf-8 -*-
"""
자동 수정 에이전트
- 트리거: GitHub 이슈에 'fix-approved' 라벨 추가
- 동작: Claude가 이슈 내용 읽고 코드 수정 → PR 자동 생성

안전 레이어 (3단계):
  1. 피드백 의도 검증  — 악의적/시스템 파괴적 요청 차단
  2. 변경 코드 안전성 검증 — 위험 패턴·문법 오류 차단
  3. 변경 범위 제한 — 과도한 수정 차단
"""

import os, json, re, ast, subprocess, urllib.request, urllib.error

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GH_TOKEN          = os.environ["GH_TOKEN"]
REPO              = os.environ["REPO"]        # "caifyhelp-cmyk/web-researcher"
ISSUE_NUMBER      = os.environ["ISSUE_NUMBER"]
ISSUE_TITLE       = os.environ.get("ISSUE_TITLE", "")
ISSUE_BODY        = os.environ.get("ISSUE_BODY", "")

# 수정 대상 파일
TARGET_FILES = ["maestro.py", "app_local.py", "orchestrator.py", "feedback_collector.py"]

# ══════════════════════════════════════════════
#  1단계: 피드백 의도 검증
# ══════════════════════════════════════════════

# 즉시 차단 키워드 (정규식)
_BLOCK_PATTERNS = [
    r"api.?key.*(출력|print|log|노출|표시)",   # API 키 노출 시도
    r"(보안|인증|검증|validation).*(제거|삭제|우회|bypass|skip)",  # 보안 우회
    r"(모든|all).*(사용자|user).*(관리자|admin|권한|access)",      # 권한 상승
    r"(rm|del|delete|drop).*(database|db|모든|all)",              # DB/파일 삭제
    r"os\.(system|popen|exec)|subprocess|eval\(|exec\(",          # 코드 주입
    r"(ignore|무시|skip).*(feedback|피드백|검증|safety|안전)",     # 안전장치 제거
    r"(백도어|backdoor|malware|ransomware|exploit)",              # 명시적 악성
]

def validate_feedback_intent(issue_title: str, issue_body: str) -> tuple[bool, str]:
    """
    1단계: 피드백이 MAESTRO를 망가뜨리려는 의도인지 검증.

    Returns:
        (True, "OK") — 안전
        (False, "이유") — 차단
    """
    combined = f"{issue_title}\n{issue_body}".lower()

    # 즉시 차단 패턴 검사
    for pattern in _BLOCK_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return False, f"위험 패턴 감지: {pattern}"

    # Claude로 의도 분석 (2차 검증)
    prompt = f"""당신은 MAESTRO 자동 수정 에이전트의 보안 검사관입니다.
아래 사용자 피드백이 시스템에 악영향을 줄 의도인지 판단하세요.

[피드백 제목]: {issue_title}
[피드백 내용]: {issue_body[:1000]}

판단 기준:
- 시스템 보안 약화, API 키 노출, 인증 우회, 권한 상승 → 위험
- 데이터 삭제, 악성 코드 주입, 안전장치 제거 → 위험
- 기능 개선, 버그 수정, UI 변경, 성능 향상 → 안전
- 모델 변경, 프롬프트 수정, 응답 형식 변경 → 안전

반드시 JSON만 출력:
{{"safe": true/false, "reason": "판단 근거 한 줄"}}"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        m = re.search(r'\{[^{}]+\}', raw)
        if m:
            data = json.loads(m.group())
            if not data.get("safe", True):
                return False, f"Claude 의도 분석: {data.get('reason', '위험')}"
    except Exception:
        pass  # Claude 호출 실패 시 패턴 검사만으로 통과

    return True, "OK"


# ══════════════════════════════════════════════
#  2단계: 변경 코드 안전성 검증
# ══════════════════════════════════════════════

# 코드 내 위험 패턴
_CODE_DANGER_PATTERNS = [
    (r'os\.system\s*\(', "os.system() 사용 금지"),
    (r'subprocess\.\w+\s*\(.*shell\s*=\s*True', "shell=True subprocess 금지"),
    (r'\beval\s*\(', "eval() 사용 금지"),
    (r'\bexec\s*\(', "exec() 사용 금지"),
    (r'__import__\s*\(', "__import__() 동적 임포트 금지"),
    (r'(ANTHROPIC|OPENAI|DEEPSEEK|GROK|GEMINI)_API_KEY.*print', "API 키 출력 금지"),
    (r'open\s*\(.*["\']w["\'].*\)\s*as.*:\s*.*os\.environ', "환경변수 파일 덮어쓰기 금지"),
    (r'shutil\.(rmtree|disk_usage).*["\'/]', "대량 파일 삭제 금지"),
]

# 한 번에 변경 가능한 최대 라인 수
_MAX_LINES_PER_CHANGE = 150
_MAX_CHANGES_TOTAL    = 5   # 파일 변경 최대 건수

def validate_code_changes(changes: list) -> tuple[bool, str]:
    """
    2단계: Claude가 제안한 코드 변경이 안전한지 검증.

    Returns:
        (True, "OK") — 안전
        (False, "이유") — 차단
    """
    if len(changes) > _MAX_CHANGES_TOTAL:
        return False, f"변경 건수 초과 ({len(changes)}건 > 최대 {_MAX_CHANGES_TOTAL}건)"

    for ch in changes:
        new_code = ch.get("new", "")
        fname    = ch.get("file", "")

        # 변경 라인 수 제한
        line_count = len(new_code.splitlines())
        if line_count > _MAX_LINES_PER_CHANGE:
            return False, f"{fname}: 변경 라인 {line_count}줄 > 최대 {_MAX_LINES_PER_CHANGE}줄"

        # Python 문법 검증
        if fname.endswith(".py"):
            try:
                ast.parse(new_code)
            except SyntaxError as e:
                return False, f"{fname}: Python 문법 오류 — {e}"

        # 위험 코드 패턴 검사
        for pattern, reason in _CODE_DANGER_PATTERNS:
            if re.search(pattern, new_code, re.IGNORECASE):
                return False, f"{fname}: {reason}"

        # 수정 대상 파일 외 접근 시도 차단
        if fname not in TARGET_FILES:
            return False, f"수정 불허 파일: {fname}"

    return True, "OK"


# ══════════════════════════════════════════════
#  소스 코드 로드
# ══════════════════════════════════════════════

def load_sources() -> dict:
    sources = {}
    for fname in TARGET_FILES:
        if os.path.exists(fname):
            with open(fname, encoding="utf-8") as f:
                sources[fname] = f.read()
    return sources


# ══════════════════════════════════════════════
#  Claude API 호출
# ══════════════════════════════════════════════

def ask_claude(issue_title: str, issue_body: str, sources: dict) -> dict:
    sources_text = "\n\n".join(
        f"=== {fname} ===\n{code}"
        for fname, code in sources.items()
    )

    prompt = f"""당신은 웹 리서치 어시스턴트 앱의 자동 수정 에이전트입니다.

아래 고객 피드백 이슈를 보고 소스 코드에서 수정 가능한 부분을 찾아 수정하세요.

[이슈 제목]
{issue_title}

[이슈 내용]
{issue_body}

[소스 코드]
{sources_text}

규칙:
1. 이슈에 명시된 내용만 수정 (추측으로 추가 기능 구현 금지)
2. 최소한의 변경 (기능 전체 재작성 금지)
3. old 값은 파일에서 정확히 복사한 문자열이어야 함
4. 수정 불가능한 경우 can_fix: false로 이유 설명
5. 반드시 아래 JSON 형식으로만 출력 (코드블록, 설명 없이 JSON만)

{{
  "can_fix": true,
  "reason": "수정 가능 이유 한 줄",
  "description": "어떤 파일의 무엇을 왜 수정했는지 요약",
  "changes": [
    {{
      "file": "파일명.py",
      "old": "기존 코드 (파일에서 정확히 복사)",
      "new": "수정된 코드"
    }}
  ]
}}"""

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()

    # JSON 파싱
    m = re.search(r'\{[\s\S]+\}', raw)
    if not m:
        return {"can_fix": False, "reason": "Claude 응답 파싱 실패", "changes": []}
    return json.loads(m.group())


# ══════════════════════════════════════════════
#  코드 수정 적용
# ══════════════════════════════════════════════

def apply_changes(changes: list) -> list:
    applied = []
    for ch in changes:
        fname = ch.get("file", "")
        old   = ch.get("old", "")
        new   = ch.get("new", "")
        if not fname or not old or not os.path.exists(fname):
            continue
        with open(fname, encoding="utf-8") as f:
            content = f.read()
        if old not in content:
            print(f"  [SKIP] {fname}: old 코드 매칭 실패")
            continue
        with open(fname, "w", encoding="utf-8") as f:
            f.write(content.replace(old, new, 1))
        print(f"  [OK] {fname} 수정 완료")
        applied.append(fname)
    return applied


# ══════════════════════════════════════════════
#  Git 브랜치 + 커밋 + 푸시
# ══════════════════════════════════════════════

def git_push(issue_number: str, applied_files: list, description: str) -> str:
    branch = f"fix/issue-{issue_number}"

    subprocess.run(["git", "config", "user.name",  "auto-fixer[bot]"], check=True)
    subprocess.run(["git", "config", "user.email", "auto-fixer@caify.ai"], check=True)
    subprocess.run(["git", "checkout", "-b", branch], check=True)

    for f in applied_files:
        subprocess.run(["git", "add", f], check=True)

    commit_msg = f"fix: #{issue_number} 고객 피드백 자동 수정\n\n{description}"
    subprocess.run(["git", "commit", "-m", commit_msg], check=True)
    subprocess.run(["git", "push", "origin", branch], check=True)

    return branch


# ══════════════════════════════════════════════
#  GitHub PR 생성
# ══════════════════════════════════════════════

def _gh_api(method: str, path: str, data: dict = None) -> dict:
    url = f"https://api.github.com/repos/{REPO}/{path}"
    body = json.dumps(data, ensure_ascii=False).encode() if data else None
    req  = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"token {GH_TOKEN}",
        "Content-Type":  "application/json",
        "Accept":        "application/vnd.github.v3+json",
        "User-Agent":    "auto-fixer",
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def create_pr(branch: str, issue_number: str, description: str) -> str:
    result = _gh_api("POST", "pulls", {
        "title": f"[자동수정] #{issue_number} 고객 피드백 반영",
        "body": (
            f"## 수정 내용\n{description}\n\n"
            f"## 연관 이슈\nCloses #{issue_number}\n\n"
            f"---\n_고객 피드백 자동 수정 에이전트가 생성한 PR입니다._"
        ),
        "head":  branch,
        "base":  "master",
    })
    return result.get("html_url", "")


def comment_issue(issue_number: str, body: str):
    _gh_api("POST", f"issues/{issue_number}/comments", {"body": body})


# ══════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════

def main():
    print(f"=== 자동 수정 에이전트 시작 (이슈 #{ISSUE_NUMBER}) ===")

    # ── [안전 1단계] 피드백 의도 검증 ───────────────────────────────
    print("피드백 의도 검증 중...")
    intent_ok, intent_reason = validate_feedback_intent(ISSUE_TITLE, ISSUE_BODY)
    if not intent_ok:
        print(f"[BLOCKED] 피드백 차단: {intent_reason}")
        comment_issue(ISSUE_NUMBER,
            f"## 🚫 자동 수정 차단\n\n"
            f"**차단 이유:** {intent_reason}\n\n"
            f"이 피드백은 시스템에 악영향을 줄 수 있어 자동 수정이 거부되었습니다.\n"
            f"정상적인 개선 요청이라면 내용을 수정 후 재제출하거나 관리자에게 직접 문의하세요.\n\n"
            f"_MAESTRO 안전 레이어 1단계 (의도 검증)에서 차단됨_")
        return

    print(f"의도 검증 통과: {intent_reason}")

    # 1. 소스 로드
    sources = load_sources()
    print(f"소스 파일 로드: {list(sources.keys())}")

    # 2. Claude 분석
    print("Claude 분석 중...")
    result = ask_claude(ISSUE_TITLE, ISSUE_BODY, sources)

    if not result.get("can_fix"):
        reason = result.get("reason", "수정 불가")
        print(f"수정 불가: {reason}")
        comment_issue(ISSUE_NUMBER,
            f"## 자동 수정 불가\n\n**이유:** {reason}\n\n"
            f"_수동으로 처리가 필요합니다._")
        return

    # ── [안전 2단계] 변경 코드 안전성 검증 ──────────────────────────
    print("코드 변경 안전성 검증 중...")
    changes = result.get("changes", [])
    code_ok, code_reason = validate_code_changes(changes)
    if not code_ok:
        print(f"[BLOCKED] 코드 변경 차단: {code_reason}")
        comment_issue(ISSUE_NUMBER,
            f"## 🚫 코드 변경 차단\n\n"
            f"**차단 이유:** {code_reason}\n\n"
            f"Claude가 제안한 코드 변경이 안전 기준을 충족하지 않습니다.\n"
            f"피드백을 더 구체적으로 작성하거나 관리자에게 직접 문의하세요.\n\n"
            f"_MAESTRO 안전 레이어 2단계 (코드 안전성)에서 차단됨_")
        return

    print(f"코드 안전성 검증 통과")

    # 3. 변경 적용
    print("코드 수정 적용 중...")
    applied = apply_changes(changes)

    if not applied:
        comment_issue(ISSUE_NUMBER,
            "## 자동 수정 실패\n\n코드 매칭에 실패했습니다. 수동 처리가 필요합니다.")
        return

    # 4. Git 푸시
    description = result.get("description", "")
    print("브랜치 생성 + 푸시 중...")
    branch = git_push(ISSUE_NUMBER, applied, description)

    # 5. PR 생성
    print("PR 생성 중...")
    pr_url = create_pr(branch, ISSUE_NUMBER, description)

    # 6. 이슈에 PR 링크 댓글
    comment_issue(ISSUE_NUMBER,
        f"## ✅ 자동 수정 PR 생성됨\n\n"
        f"**수정 내용:** {description}\n\n"
        f"**PR:** {pr_url}\n\n"
        f"**안전 검증:** 의도 검증 ✓ | 코드 안전성 ✓ | 문법 검증 ✓\n\n"
        f"_검토 후 머지해 주세요._")

    print(f"완료! PR: {pr_url}")


if __name__ == "__main__":
    main()
