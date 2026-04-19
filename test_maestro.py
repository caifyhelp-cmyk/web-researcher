# -*- coding: utf-8 -*-
"""
MAESTRO 내부 테스트 스크립트
실행: python test_maestro.py
"""

import sys, os, time, json
from pathlib import Path

# API 키 로드
try:
    import _local_keys
except ImportError:
    pass

PASS = "  [PASS]"
FAIL = "  [FAIL]"
SKIP = "  [SKIP]"
SEP  = "=" * 60


# ═══════════════════════════════════════════════════════
#  1. 의존성 체크
# ═══════════════════════════════════════════════════════

def test_dependencies():
    print(f"\n{SEP}")
    print("1. 의존성 체크")
    print(SEP)

    required = {
        "openai":             "GPT-4o / DeepSeek / Grok / Gemini 연동",
        "anthropic":          "Claude API",
        "rich":               "터미널 UI",
        "requests":           "웹 크롤링",
        "bs4":                "HTML 파싱 (BeautifulSoup)",
        "openpyxl":           "Excel 저장",
        "sqlite3":            "응답 캐시 / 오케스트레이터 DB (내장)",
    }
    optional = {
        "selenium":           "Selenium 웹 드라이버 (JS 사이트 크롤링)",
        "webdriver_manager":  "ChromeDriver 자동 관리",
        "duckduckgo_search":  "DuckDuckGo 검색",
        "ddgs":               "DuckDuckGo 검색 (신버전)",
        "pdfplumber":         "PDF 읽기",
        "pypdf":              "PDF 읽기 (대체)",
        "docx":               "Word 파일 읽기",
        "matplotlib":         "차트 생성",
        "numpy":              "임베딩 유사도 계산 (캐시)",
        "reportlab":          "PDF 저장",
        "pptx":               "PPT 저장",
        "pandas":             "데이터 처리",
    }

    all_ok = True
    for pkg, desc in required.items():
        try:
            __import__(pkg)
            print(f"{PASS} {pkg:<25} {desc}")
        except ImportError:
            print(f"{FAIL} {pkg:<25} {desc}  ← pip install {pkg}")
            all_ok = False

    print()
    missing_opt = []
    for pkg, desc in optional.items():
        try:
            __import__(pkg)
            print(f"{PASS} {pkg:<25} {desc}")
        except ImportError:
            print(f"{SKIP} {pkg:<25} {desc}")
            missing_opt.append(pkg)

    if missing_opt:
        print(f"\n  선택 패키지 설치 (필요한 것만):")
        print(f"  pip install {' '.join(missing_opt)}")
    return all_ok


# ═══════════════════════════════════════════════════════
#  2. API 키 / 클라이언트 체크
# ═══════════════════════════════════════════════════════

def test_api_keys():
    print(f"\n{SEP}")
    print("2. API 키 / 클라이언트 상태")
    print(SEP)

    from openai import OpenAI
    from anthropic import Anthropic

    keys = {
        "OPENAI_API_KEY":    ("GPT-4o (오케스트레이터)", True),
        "ANTHROPIC_API_KEY": ("Claude (전략/글쓰기)",    False),
        "DEEPSEEK_API_KEY":  ("DeepSeek (추론/리서치 플랜)", False),
        "GROK_API_KEY":      ("Grok (실시간 정보)",      False),
        "GEMINI_API_KEY":    ("Gemini 2.0 Flash",        False),
        "NAVER_CLIENT_ID":   ("Naver 검색 API",          False),
        "VERCEL_TOKEN":      ("Vercel 배포",             False),
        "GITHUB_DATA_TOKEN": ("GitHub 집단지성 동기화",  False),
    }

    has_openai = False
    for key, (desc, required) in keys.items():
        val = os.getenv(key, "")
        if val:
            masked = val[:6] + "..." + val[-4:]
            tag = PASS
            if key == "OPENAI_API_KEY":
                has_openai = True
        else:
            masked = "(없음)"
            tag = FAIL if required else SKIP

        print(f"{tag} {key:<25} {desc:<25} {masked}")

    return has_openai


# ═══════════════════════════════════════════════════════
#  3. 오케스트레이터 DB 체크
# ═══════════════════════════════════════════════════════

def test_orchestrator():
    print(f"\n{SEP}")
    print("3. 오케스트레이터 (orchestrator.py)")
    print(SEP)

    try:
        import orchestrator as orch
        print(f"{PASS} orchestrator.py import 성공")

        rows = orch.get_cache_summary()
        print(f"{PASS} DB 캐시 조회 성공 ({len(rows)}개 카테고리)")
        for r in rows:
            print(f"       {r['category']:<20} winner={r['winner']:<12} "
                  f"meta={r['meta_score']} self={r['self_score']} streak={r['low_score_streak']}")

        # get_best_model 테스트
        for cat in ["strategy_insight", "data_extraction", "query_generation"]:
            winner = orch.get_best_model(cat)
            print(f"{PASS} get_best_model('{cat}') → {winner}")

        stale = orch.get_stale_categories(days=7)
        print(f"{PASS} get_stale_categories() → {stale if stale else '없음 (최신)'}")

        return True
    except Exception as e:
        print(f"{FAIL} orchestrator 오류: {e}")
        return False


# ═══════════════════════════════════════════════════════
#  4. 응답 캐시 DB 체크
# ═══════════════════════════════════════════════════════

def test_cache():
    print(f"\n{SEP}")
    print("4. 응답 캐시 (SQLite)")
    print(SEP)

    import sqlite3
    cache_path = Path.home() / ".maestro" / "response_cache.db"
    try:
        conn = sqlite3.connect(str(cache_path))
        count = conn.execute("SELECT COUNT(*) FROM response_cache").fetchone()[0]
        conn.close()
        print(f"{PASS} 캐시 DB 연결 성공 (저장된 응답: {count}개)")
        print(f"       경로: {cache_path}")
        return True
    except Exception as e:
        print(f"{FAIL} 캐시 DB 오류: {e}")
        return False


# ═══════════════════════════════════════════════════════
#  5. tools_kb.json 체크
# ═══════════════════════════════════════════════════════

def test_tools_kb():
    print(f"\n{SEP}")
    print("5. 툴 지식 DB (tools_kb.json)")
    print(SEP)

    kb_path = Path(__file__).parent / "tools_kb.json"
    try:
        data = json.loads(kb_path.read_text(encoding="utf-8"))
        tools = data.get("tools", [])
        print(f"{PASS} tools_kb.json 로드 성공 ({len(tools)}개 툴, updated: {data.get('updated_at','?')})")
        for t in tools:
            print(f"       - {t['name']} ({t['category']})")
        return True
    except Exception as e:
        print(f"{FAIL} tools_kb.json 오류: {e}")
        return False


# ═══════════════════════════════════════════════════════
#  6. web_fetch 테스트 (requests + BeautifulSoup)
# ═══════════════════════════════════════════════════════

def test_web_fetch():
    print(f"\n{SEP}")
    print("6. web_fetch (requests + BeautifulSoup)")
    print(SEP)

    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        t0 = time.time()
        resp = requests.get("https://example.com", headers=headers, timeout=8)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())
        elapsed = time.time() - t0

        print(f"{PASS} example.com 크롤링 성공 ({elapsed:.1f}s, {len(text)}자)")
        print(f"       미리보기: {text[:80]}...")
        return True
    except Exception as e:
        print(f"{FAIL} web_fetch 오류: {e}")
        return False


# ═══════════════════════════════════════════════════════
#  7. DuckDuckGo 검색 테스트
# ═══════════════════════════════════════════════════════

def test_web_search():
    print(f"\n{SEP}")
    print("7. 웹 검색 (DuckDuckGo)")
    print(SEP)

    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        t0 = time.time()
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text("파이썬 웹 리서치", max_results=3):
                results.append(r)
        elapsed = time.time() - t0

        if results:
            print(f"{PASS} DuckDuckGo 검색 성공 ({elapsed:.1f}s, {len(results)}개 결과)")
            for r in results:
                print(f"       - {r.get('title','')[:50]}")
        else:
            print(f"{FAIL} DuckDuckGo 결과 없음 (rate limit 가능성)")
        return bool(results)
    except Exception as e:
        print(f"{FAIL} DuckDuckGo 오류: {e}")
        return False


# ═══════════════════════════════════════════════════════
#  8. Selenium / Chrome 체크 + web_fetch 폴백 연동 테스트
# ═══════════════════════════════════════════════════════

def test_selenium():
    print(f"\n{SEP}")
    print("8. Selenium + Chrome + web_fetch 폴백 연동")
    print(SEP)
    print("  ※ API 키 불필요. Chrome + pip install selenium webdriver-manager 만 있으면 됩니다.")

    # ── 8-1. 패키지 존재 확인 ────────────────────────────────────
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
        print(f"{PASS} selenium / webdriver-manager 설치 확인")
    except ImportError as e:
        print(f"{FAIL} 패키지 미설치: {e}")
        print(f"       pip install selenium webdriver-manager")
        return False

    # ── 8-2. Chrome 드라이버 초기화 ──────────────────────────────
    try:
        from web_researcher import make_driver, scrape_page
        print("  ChromeDriver 초기화 중 (첫 실행 시 자동 다운로드)...")
        t0 = time.time()
        driver = make_driver()
        elapsed = time.time() - t0

        if driver is None:
            print(f"{FAIL} Chrome 드라이버 초기화 실패 (Chrome 설치 필요)")
            print(f"       https://www.google.com/chrome/")
            return False

        print(f"{PASS} Chrome 드라이버 초기화 성공 ({elapsed:.1f}s)")
    except Exception as e:
        print(f"{FAIL} make_driver() 오류: {e}")
        return False

    # ── 8-3. 정적 페이지 크롤링 ──────────────────────────────────
    try:
        t0 = time.time()
        page = scrape_page(driver, "https://example.com")
        elapsed = time.time() - t0
        text = page.get("full_text", "")
        if text and len(text) > 50:
            print(f"{PASS} 정적 페이지 크롤링 (example.com) → {len(text)}자 ({elapsed:.1f}s)")
        else:
            print(f"{FAIL} 정적 페이지 내용 부족: {len(text)}자")
    except Exception as e:
        print(f"{FAIL} scrape_page() 오류: {e}")

    # ── 8-4. maestro._tool_web_fetch Selenium 폴백 연동 확인 ─────
    print()
    print("  [web_fetch Selenium 폴백 테스트]")
    try:
        # JS 헤비 사이트 — requests만으론 내용 없는 대표 사례
        JS_TEST_URLS = [
            ("https://www.netflix.com/kr/", "JS 렌더링 사이트 (Netflix)"),
            ("https://www.coupang.com/",    "JS 렌더링 사이트 (쿠팡)"),
        ]
        import requests as _req
        from bs4 import BeautifulSoup as _BS

        _HEADERS = {"User-Agent": "Mozilla/5.0 Chrome/124.0"}
        for url, label in JS_TEST_URLS:
            try:
                resp = _req.get(url, headers=_HEADERS, timeout=8, allow_redirects=True)
                soup = _BS(resp.content, "html.parser")
                for tag in soup(["script", "style"]): tag.decompose()
                requests_text = " ".join(soup.get_text(separator=" ").split())

                page = scrape_page(driver, url)
                selenium_text = page.get("full_text", "")

                r_len = len(requests_text)
                s_len = len(selenium_text)
                gain  = s_len - r_len
                emoji = "▲" if gain > 200 else "─"

                print(f"  {label}")
                print(f"    requests : {r_len:,}자")
                print(f"    Selenium : {s_len:,}자  {emoji} 차이: {gain:+,}자")

                if gain > 200:
                    print(f"    → Selenium 폴백이 유의미한 추가 정보 수집")
                elif r_len > 200:
                    print(f"    → requests만으로 충분 (Selenium 폴백 불필요)")
                else:
                    print(f"    → 둘 다 부족 (로그인 필요 사이트)")
            except Exception as e:
                print(f"    {label}: 오류 — {e}")
    except Exception as e:
        print(f"{FAIL} 폴백 테스트 오류: {e}")

    # ── 드라이버 종료 ─────────────────────────────────────────────
    try:
        driver.quit()
        print(f"\n{PASS} Chrome 드라이버 정상 종료")
    except Exception:
        pass

    return True


# ═══════════════════════════════════════════════════════
#  9. LLM API 실제 호출 테스트 (키 있는 것만)
# ═══════════════════════════════════════════════════════

def test_llm_calls():
    print(f"\n{SEP}")
    print("9. LLM API 실제 호출 테스트")
    print(SEP)

    from openai import OpenAI
    from anthropic import Anthropic

    PROMPT = "한국어로 한 문장만: 지금 몇 시인지 모르지만 안녕하세요라고 답해줘."
    results = {}

    # GPT-4o-mini (저렴하게 테스트)
    key = os.getenv("OPENAI_API_KEY", "")
    if key:
        try:
            t0 = time.time()
            oai = OpenAI(api_key=key)
            r = oai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": PROMPT}],
                max_tokens=50
            )
            resp = r.choices[0].message.content.strip()
            elapsed = time.time() - t0
            print(f"{PASS} GPT-4o-mini  ({elapsed:.1f}s) → {resp}")
            results["gpt"] = True
        except Exception as e:
            print(f"{FAIL} GPT-4o-mini → {e}")
            results["gpt"] = False
    else:
        print(f"{SKIP} GPT-4o-mini  (OPENAI_API_KEY 없음)")

    # Claude
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if key:
        try:
            t0 = time.time()
            ant = Anthropic(api_key=key)
            r = ant.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=50,
                messages=[{"role": "user", "content": PROMPT}]
            )
            resp = r.content[0].text.strip()
            elapsed = time.time() - t0
            print(f"{PASS} Claude Haiku ({elapsed:.1f}s) → {resp}")
            results["claude"] = True
        except Exception as e:
            print(f"{FAIL} Claude Haiku → {e}")
            results["claude"] = False
    else:
        print(f"{SKIP} Claude       (ANTHROPIC_API_KEY 없음)")

    # DeepSeek
    key = os.getenv("DEEPSEEK_API_KEY", "")
    if key:
        try:
            t0 = time.time()
            ds = OpenAI(api_key=key, base_url="https://api.deepseek.com")
            r = ds.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": PROMPT}],
                max_tokens=50
            )
            resp = r.choices[0].message.content.strip()
            elapsed = time.time() - t0
            print(f"{PASS} DeepSeek     ({elapsed:.1f}s) → {resp}")
            results["deepseek"] = True
        except Exception as e:
            print(f"{FAIL} DeepSeek → {e}")
            results["deepseek"] = False
    else:
        print(f"{SKIP} DeepSeek     (DEEPSEEK_API_KEY 없음)")

    # Grok
    key = os.getenv("GROK_API_KEY", "")
    if key:
        try:
            t0 = time.time()
            gk = OpenAI(api_key=key, base_url="https://api.x.ai/v1")
            r = gk.chat.completions.create(
                model="grok-3",
                messages=[{"role": "user", "content": PROMPT}],
                max_tokens=50
            )
            resp = r.choices[0].message.content.strip()
            elapsed = time.time() - t0
            print(f"{PASS} Grok-3       ({elapsed:.1f}s) → {resp}")
            results["grok"] = True
        except Exception as e:
            print(f"{FAIL} Grok → {e}")
            results["grok"] = False
    else:
        print(f"{SKIP} Grok         (GROK_API_KEY 없음)")

    # Gemini
    key = os.getenv("GEMINI_API_KEY", "")
    if key:
        try:
            t0 = time.time()
            gm = OpenAI(
                api_key=key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
            r = gm.chat.completions.create(
                model="gemini-2.0-flash",
                messages=[{"role": "user", "content": PROMPT}],
                max_tokens=50
            )
            resp = r.choices[0].message.content.strip()
            elapsed = time.time() - t0
            print(f"{PASS} Gemini Flash ({elapsed:.1f}s) → {resp}")
            results["gemini"] = True
        except Exception as e:
            print(f"{FAIL} Gemini → {e}")
            results["gemini"] = False
    else:
        print(f"{SKIP} Gemini       (GEMINI_API_KEY 없음)")

    return results


# ═══════════════════════════════════════════════════════
#  10. maestro.py import 테스트 (전체 모듈 로드)
# ═══════════════════════════════════════════════════════

def test_maestro_import():
    print(f"\n{SEP}")
    print("10. maestro.py 전체 모듈 로드 테스트")
    print(SEP)

    try:
        t0 = time.time()
        import maestro
        elapsed = time.time() - t0

        # 주요 함수 존재 확인
        checks = [
            "_tool_web_fetch",
            "_tool_web_search",
            "_tool_ask_specialist",
            "_tool_web_research",
            "_tool_save_research",
            "_tool_generate_image",
            "_tool_create_chart",
            "_tool_analyze_document",
            "_tool_vercel_deploy",
            "run_agent",
        ]
        print(f"{PASS} maestro.py import 성공 ({elapsed:.1f}s)")
        for fn in checks:
            exists = hasattr(maestro, fn)
            tag = PASS if exists else FAIL
            print(f"  {tag} {fn}")

        # orchestrator 연결 확인
        orch_ok = getattr(maestro, "_ORCH", False)
        rl_ok   = getattr(maestro, "_RL",   False)
        pc_ok   = getattr(maestro, "_PC",   False)
        print(f"\n  {'[OK]' if orch_ok else '[X]'} orchestrator 연결: {orch_ok}")
        print(f"  {'[OK]' if rl_ok   else '[X]'} app_local 연결:    {rl_ok}")
        print(f"  {'[OK]' if pc_ok   else '[X]'} pattern_collector: {pc_ok}")
        print(f"\n  VERSION = {getattr(maestro, 'VERSION', '?')}")
        return True
    except Exception as e:
        import traceback
        print(f"{FAIL} maestro.py import 실패:")
        traceback.print_exc()
        return False


# ═══════════════════════════════════════════════════════
#  11. 세션 시스템 체크
# ═══════════════════════════════════════════════════════

def test_session():
    print(f"\n{SEP}")
    print("11. 세션 로그 시스템")
    print(SEP)

    sessions_dir = Path.home() / ".maestro" / "sessions"
    sessions = list(sessions_dir.glob("*.json")) if sessions_dir.exists() else []
    print(f"{PASS} 세션 폴더: {sessions_dir}")
    print(f"       저장된 세션 수: {len(sessions)}개")
    if sessions:
        latest = sorted(sessions)[-1]
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            print(f"       최근 세션: {data.get('session_id','')}  "
                  f"{data.get('turn_count',0)}턴  "
                  f"\"{data.get('first_message','')[:30]}\"")
        except Exception:
            pass
    return True


# ═══════════════════════════════════════════════════════
#  메인
# ═══════════════════════════════════════════════════════

def main():
    print("\n" + "=" * 60)
    print("  MAESTRO 내부 테스트")
    print("=" * 60)

    results = {}

    results["deps"]       = test_dependencies()
    results["api_keys"]   = test_api_keys()
    results["orchestr"]   = test_orchestrator()
    results["cache"]      = test_cache()
    results["tools_kb"]   = test_tools_kb()
    results["web_fetch"]  = test_web_fetch()
    results["web_search"] = test_web_search()
    results["selenium"]   = test_selenium()
    llm_results           = test_llm_calls()
    results["maestro"]    = test_maestro_import()
    results["session"]    = test_session()

    # 최종 요약
    print(f"\n{SEP}")
    print("  최종 요약")
    print(SEP)

    ok  = sum(1 for v in results.values() if v is True)
    err = sum(1 for v in results.values() if v is False)
    print(f"  전체: {len(results)}개 테스트  →  통과 {ok}개  /  실패 {err}개")

    llm_connected = [k for k, v in llm_results.items() if v]
    llm_missing   = [k for k, v in llm_results.items() if not v]
    if llm_connected:
        print(f"  연결된 LLM: {', '.join(llm_connected)}")
    if llm_missing:
        print(f"  미연결 LLM: {', '.join(llm_missing)}")

    if err == 0:
        print("\n  모든 테스트 통과. MAESTRO 실행 준비 완료!")
    else:
        print(f"\n  {err}개 항목 수정 필요. 위 [FAIL] 항목을 확인하세요.")

    print()


if __name__ == "__main__":
    main()
