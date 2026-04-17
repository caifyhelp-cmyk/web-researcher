# -*- coding: utf-8 -*-
"""
자동 수정 에이전트
- 트리거: GitHub 이슈에 'fix-approved' 라벨 추가
- 동작: Claude가 이슈 내용 읽고 코드 수정 → PR 자동 생성
"""

import os, json, re, subprocess, urllib.request, urllib.error

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GH_TOKEN          = os.environ["GH_TOKEN"]
REPO              = os.environ["REPO"]        # "caifyhelp-cmyk/web-researcher"
ISSUE_NUMBER      = os.environ["ISSUE_NUMBER"]
ISSUE_TITLE       = os.environ.get("ISSUE_TITLE", "")
ISSUE_BODY        = os.environ.get("ISSUE_BODY", "")

# 수정 대상 파일
TARGET_FILES = ["app_local.py", "orchestrator.py", "feedback_collector.py"]


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

    # 3. 변경 적용
    print("코드 수정 적용 중...")
    applied = apply_changes(result.get("changes", []))

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
        f"## 자동 수정 PR 생성됨\n\n"
        f"**수정 내용:** {description}\n\n"
        f"**PR:** {pr_url}\n\n"
        f"_검토 후 머지해 주세요._")

    print(f"완료! PR: {pr_url}")


if __name__ == "__main__":
    main()
