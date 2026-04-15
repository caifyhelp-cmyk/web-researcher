# -*- coding: utf-8 -*-
import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from anthropic import Anthropic

ANTHROPIC_API_KEY = "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"
claude = Anthropic(api_key=ANTHROPIC_API_KEY)

def current_process_feedback(feedback_text, current_rules=None, current_prompt="(없음)"):
    if current_rules is None:
        current_rules = {}
    prompt = (
        '이 웹리서치 도구 사용자의 피드백입니다.\n\n'
        f'피드백: "{feedback_text}"\n\n'
        f'현재 사용자 규칙:\n{json.dumps(current_rules, ensure_ascii=False)}\n\n'
        f'현재 시스템 프롬프트:\n{current_prompt}\n\n'
        '다음 작업 수행\n'
        '1. 피드백에서 구체적이고 실행 가능한 규칙을 추출하세요.\n'
        '2. 기존 규칙을 업데이트하거나 새 규칙을 추가하세요.\n'
        '3. 이 사용자의 특성을 반영하는 시스템 프롬프트를 재작성하세요.\n'
        '4. 변경 내용을 명확히 요약하세요.\n\n'
        'JSON만 반환:\n'
        '{\n'
        '  "system_prompt": "이 사용자는 ... (2~4문장)",\n'
        '  "rules": {\n'
        '    "force_strict_filter": "high 또는 medium 또는 low 또는 null",\n'
        '    "min_count": 숫자 또는 null,\n'
        '    "count_multiplier": 1.0,\n'
        '    "exclude_blogs": false,\n'
        '    "force_official_only": false,\n'
        '    "extra_excluded_domains": [],\n'
        '    "preferred_domains": [],\n'
        '    "query_style": null\n'
        '  },\n'
        '  "changes": ["변경 사항 1"],\n'
        '  "changes_summary": "한 줄 요약"\n'
        '}'
    )
    resp = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    m = re.search(r'\{[\s\S]+\}', text)
    if m:
        try:
            return json.loads(m.group()), None
        except Exception as e:
            return None, f"JSON 파싱 오류: {e}\n원문: {text[:300]}"
    return None, "JSON 없음"

cases = [
    ("케이스1 감정적 불만 (뻔함)",
     "결과가 너무 뻔한 것들만 나와. 다 아는 얘기잖아",
     "경쟁사 분석 후 12개 결과",
     "이 피드백에서 실행 규칙 추출 가능? system_prompt가 한국 B2B 맥락에 맞는가?"),

    ("케이스2 업종 암묵 요청",
     "우리 B2B 교육업체 특성상 수강생 후기나 인지도 위주로 봐야 하는데",
     "직무교육 경쟁사 조사 직후",
     "업종/관점이 system_prompt에 녹아드는가? '수강생 후기' 방향 반영?"),

    ("케이스3 수량 간접 불만",
     "이걸로 보고서 쓰기엔 좀 부족한 것 같은데",
     "결과 12개 받은 후",
     "min_count/count_multiplier가 올라가는가?"),

    ("케이스4 분석 깊이 요청",
     "분석이 너무 표면적이야. 실제 실무에서 쓸 만한 인사이트를 줘",
     "인사이트 리포트 읽은 후",
     "system_prompt에 실무적 깊이 지침이 들어가는가?"),

    ("케이스5 특정 사이트 불만",
     "왜 자꾸 네이버 블로그가 나와? 이런 거 빼줘",
     "블로그 결과 섞인 후",
     "exclude_blogs: true 또는 blog.naver.com exclusion?"),

    ("케이스6 포맷/톤 요청",
     "인사이트를 좀 더 짧게 bullet으로 써줘. 지금 너무 길어",
     "긴 인사이트 리포트 읽은 후",
     "포맷 요청 — 현재 rules 구조로 반영 불가 영역. 어떻게 처리하는가?"),

    ("케이스7 모호한 칭찬",
     "오 이번엔 괜찮네",
     "만족스러운 리서치 후",
     "규칙 변경이 없어야 정상"),

    ("케이스8 복합 피드백",
     "결과 수가 더 많았으면 하고, 공식 기관/협회 위주로 나왔으면 좋겠어. 분석 톤도 좀 더 냉정하게",
     "국내 교육 시장 조사 후",
     "count_multiplier, force_official_only, system_prompt 톤 — 3가지 동시 반영?"),

    ("케이스9 무관한 잡담",
     "오늘 날씨 좋다. 이 프로그램 색깔 좀 바꿔줄 수 없어?",
     "사용 중 잡담",
     "rules 오염 없어야 함"),
]

print("=== 현재 process_feedback 시뮬레이션 ===\n")

issues_found = []

for label, feedback, ctx, check in cases:
    print(f"{'='*65}")
    print(f"[{label}]")
    print(f"상황: {ctx}")
    print(f"피드백: \"{feedback}\"")
    print(f"검수: {check}")
    print()

    result, err = current_process_feedback(feedback)
    if err:
        print(f"오류: {err}")
        issues_found.append(f"{label}: {err}")
        continue

    sp = result.get("system_prompt", "")
    rules = result.get("rules", {})
    changes = result.get("changes", [])

    active = {k: v for k, v in rules.items()
              if v is not None and v is not False
              and v != 1.0 and v != [] and v != "null" and v != ""}

    print(f"system_prompt:\n  {sp}")
    print(f"활성 규칙: {json.dumps(active, ensure_ascii=False)}")
    print(f"changes: {changes}")

    # 자동 문제 감지
    if "케이스7" in label and active:
        msg = f"칭찬인데 규칙 변경됨: {list(active.keys())}"
        print(f"[ISSUE] {msg}")
        issues_found.append(f"{label} => {msg}")

    if "케이스9" in label and active:
        msg = f"무관 잡담인데 rules 오염: {list(active.keys())}"
        print(f"[ISSUE] {msg}")
        issues_found.append(f"{label} => {msg}")

    if "케이스6" in label:
        fmt_ok = any(w in sp for w in ["bullet", "짧게", "간결", "포맷", "형식", "짧고"])
        if not fmt_ok:
            msg = "포맷 요청인데 system_prompt에 미반영 (rules 구조 한계)"
            print(f"[WARN] {msg}")
            issues_found.append(f"{label} => {msg}")

    if "케이스1" in label:
        bad = [d for d in active.get("preferred_domains", [])
               if any(x in d for x in ["arxiv", "jstor", "scholar.google", "nature.com", "science.org"])]
        if bad:
            msg = f"한국 B2B 맥락인데 학술 도메인 추출됨: {bad}"
            print(f"[ISSUE] {msg}")
            issues_found.append(f"{label} => {msg}")

    print()

print("="*65)
print("총 이슈 목록:")
if issues_found:
    for i in issues_found:
        print(f"  !! {i}")
else:
    print("  자동 감지 이슈 없음")
