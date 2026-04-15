# -*- coding: utf-8 -*-
"""웹 리서치 어시스턴트 — 터미널 버전 v1"""

import os, sys, json, re, time
from datetime import datetime

# API 키 자동 주입
try:
    import _local_keys
except ImportError:
    pass

# ── Rich UI ──────────────────────────────────────────────────────
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.rule import Rule
from rich.prompt import Prompt, Confirm

# ── PDF / PPT ────────────────────────────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    _PDF = True
except Exception:
    _PDF = False

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    _PPT = True
except Exception:
    _PPT = False

import openpyxl
from openai import OpenAI
from anthropic import Anthropic

# ── API 클라이언트 ────────────────────────────────────────────────
OPENAI_KEY    = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEEPSEEK_KEY  = os.getenv("DEEPSEEK_API_KEY", "")
GROK_KEY      = os.getenv("GROK_API_KEY", "")

oai      = OpenAI(api_key=OPENAI_KEY)                                         if OPENAI_KEY    else None
claude_c = Anthropic(api_key=ANTHROPIC_KEY)                                   if ANTHROPIC_KEY else None
deepseek = OpenAI(api_key=DEEPSEEK_KEY, base_url="https://api.deepseek.com") if DEEPSEEK_KEY  else None
grok_ai  = OpenAI(api_key=GROK_KEY,     base_url="https://api.x.ai/v1")      if GROK_KEY      else None

console  = Console(highlight=False)
SAVE_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "리서치결과")
os.makedirs(SAVE_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════
#  LLM 호출
# ═══════════════════════════════════════════════════════
def call_gpt(prompt: str, system: str = "", model: str = "gpt-4o-mini") -> str:
    if not oai:
        return "[OpenAI 키 없음]"
    msgs = ([{"role": "system", "content": system}] if system else []) + \
           [{"role": "user", "content": prompt}]
    try:
        r = oai.chat.completions.create(model=model, messages=msgs, max_tokens=2000)
        return r.choices[0].message.content.strip()
    except Exception as e:
        return f"[GPT 오류: {e}]"

def call_claude(prompt: str, system: str = "") -> str:
    if not claude_c:
        return call_gpt(prompt, system)
    try:
        r = claude_c.messages.create(
            model="claude-opus-4-6", max_tokens=2000,
            system=system or "당신은 전문 리서치 분석가입니다.",
            messages=[{"role": "user", "content": prompt}]
        )
        return r.content[0].text.strip()
    except Exception as e:
        return f"[Claude 오류: {e}]"

def call_deepseek(prompt: str) -> str:
    if not deepseek:
        return call_gpt(prompt)
    try:
        r = deepseek.chat.completions.create(
            model="deepseek-reasoner",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000
        )
        return r.choices[0].message.content.strip()
    except Exception:
        return call_gpt(prompt)

# ═══════════════════════════════════════════════════════
#  리서치 플랜 (DeepSeek)
# ═══════════════════════════════════════════════════════
def make_plan(topic: str, depth: str) -> dict:
    prompt = f"""리서치 주제: {topic}
조사 깊이: {depth}

이 주제를 조사하기 위한 **구체적이고 직접적인** 한국어 검색어 5개와,
각 수집 페이지에서 GPT가 추출해야 할 구조화 항목 5~8개를 만드세요.
- 검색어는 반드시 주제의 핵심 키워드만 포함 (불필요한 단어 제거)
- 네이버에서 실제로 검색했을 때 관련 페이지가 나올 만한 검색어
- 너무 광범위하거나 다른 분야가 섞이지 않도록 주의
- needs는 주제에 맞는 실질적 정보 항목 (예: 경쟁사명, 주요서비스, 가격정책, 고객후기, 연락처)

JSON 형식으로만 답하세요:
{{
  "summary": "주제 한줄 요약",
  "keywords": ["핵심키워드1", "핵심키워드2"],
  "queries": ["구체적 검색어1", "구체적 검색어2", "구체적 검색어3", "구체적 검색어4", "구체적 검색어5"],
  "needs": ["항목1", "항목2", "항목3", "항목4", "항목5"],
  "focus_points": ["핵심1", "핵심2", "핵심3"],
  "analysis_angle": "분석 방향"
}}"""
    raw = call_deepseek(prompt)
    try:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            plan = json.loads(m.group())
            console.print(f"[dim]생성된 검색어:[/dim]")
            for i, q in enumerate(plan.get("queries", []), 1):
                console.print(f"[dim]  {i}. {q}[/dim]")
            return plan
    except Exception:
        pass
    return {
        "summary": topic,
        "keywords": [topic],
        "queries": [topic, f"{topic} 랜딩페이지", f"{topic} 서비스 비교", f"{topic} 업체 현황", f"{topic} 사례"],
        "needs": ["업체명", "주요서비스", "가격정책", "고객후기", "연락처"],
        "focus_points": ["주요 현황", "서비스 분석", "시장 트렌드"],
        "analysis_angle": "종합 전략 분석"
    }

def _filter_relevant(candidates: list, topic: str, keywords: list) -> list:
    """GPT로 관련없는 URL 제거"""
    if not candidates or not oai:
        return candidates
    items = "\n".join(f"{i+1}. [{c.get('title','')}] {c.get('url','')}"
                      for i, c in enumerate(candidates))
    kw = ", ".join(keywords) if keywords else topic
    resp = call_gpt(
        f"주제: {topic}\n핵심 키워드: {kw}\n\n아래 URL 목록 중 주제와 관련된 번호만 쉼표로 답하세요. 관련없으면 제외.\n\n{items}",
        system="URL이 주제와 관련있는지 판단하는 필터입니다. 번호만 쉼표로 답하세요.",
        model="gpt-4o-mini"
    )
    try:
        nums = [int(x.strip()) - 1 for x in re.findall(r'\d+', resp)]
        filtered = [candidates[i] for i in nums if 0 <= i < len(candidates)]
        return filtered if filtered else candidates[:3]
    except Exception:
        return candidates

# ═══════════════════════════════════════════════════════
#  간단 스크래퍼 (requests + BeautifulSoup)
# ═══════════════════════════════════════════════════════
import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

def _fetch_page(url: str, timeout: int = 8) -> dict:
    """URL 스크랩 → {text, headings, page_title, error}"""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        page_title = soup.title.string.strip() if soup.title and soup.title.string else ""
        headings = " | ".join(
            h.get_text(strip=True)
            for h in soup.find_all(["h1","h2","h3"])
            if h.get_text(strip=True)
        )[:500]
        for tag in soup(["script","style","nav","footer","header","aside"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())[:4000]
        return {"text": text, "headings": headings, "page_title": page_title, "error": ""}
    except Exception as e:
        return {"text": "", "headings": "", "page_title": "", "error": str(e)[:80]}

def _fetch_text(url: str, timeout: int = 8) -> str:
    return _fetch_page(url, timeout)["text"]

# ═══════════════════════════════════════════════════════
#  검색 + 스크랩
# ═══════════════════════════════════════════════════════
def run_research(plan: dict) -> list:
    try:
        from web_researcher import search_naver, search_duckduckgo
    except ImportError:
        console.print("[red]web_researcher 모듈 없음[/red]")
        return []

    from urllib.parse import urlparse
    results = []
    seen_urls = set()
    queries = plan.get("queries", [])
    depth_n = {"빠른 조사": 3, "일반 조사": 5, "심층 조사": 8}
    max_q = depth_n.get(plan.get("_depth", "일반 조사"), 5)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console, transient=True
    ) as prog:
        for q in queries[:max_q]:
            t = prog.add_task(f"[cyan]검색: {q[:45]}", total=None)
            try:
                candidates = search_naver(q, max_results=8)
                if not candidates:
                    candidates = search_duckduckgo(q, max_results=8)

                keywords = plan.get("keywords", [])
                candidates = _filter_relevant(candidates, q, keywords)

                for item in candidates[:4]:
                    url   = item.get("url", "")
                    title = item.get("title", url)
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    prog.update(t, description=f"[yellow]수집: {title[:40]}")
                    page = _fetch_page(url)
                    if page["text"] and len(page["text"]) > 150:
                        domain = urlparse(url).netloc
                        results.append({
                            "query":      q,
                            "url":        url,
                            "title":      title,
                            "domain":     domain,
                            "content":    page["text"][:3000],
                            "page_title": page["page_title"],
                            "headings":   page["headings"],
                            "error":      page["error"],
                        })
            except Exception:
                pass
            prog.remove_task(t)

    return results

# ═══════════════════════════════════════════════════════
#  URL별 GPT 구조화 추출
# ═══════════════════════════════════════════════════════
def _analyze_url(r: dict, topic: str, needs: list) -> dict:
    """URL 1개에 대해 GPT로 구조화 정보 추출"""
    if not oai:
        return {"한줄요약": "", **{n: "" for n in needs}}
    needs_str = "\n".join(f'  "{n}": ""' for n in needs)
    prompt = f"""웹 리서치 전문가로서 아래 페이지를 분석해주세요.

[조사 주제]: {topic}
[URL]: {r.get('url','')}
[제목]: {r.get('page_title', r.get('title',''))}
[헤딩]: {r.get('headings','')}
[본문]: {r.get('content','')}

없으면 "확인 불가". 각 항목 2~5문장.
JSON만:
{{
  "한줄요약": "",
{needs_str}
}}"""
    try:
        resp = oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=1500,
        )
        raw = resp.choices[0].message.content.strip()
        m = re.search(r"\{[\s\S]+\}", raw)
        if m:
            return json.loads(m.group())
    except Exception as e:
        console.print(f"[red]GPT 추출 오류: {e}[/red]")
    return {"한줄요약": "분석 실패", **{n: "" for n in needs}}

# ═══════════════════════════════════════════════════════
#  AI 분석
# ═══════════════════════════════════════════════════════
def analyze(topic: str, plan: dict, results: list) -> dict:
    if not results:
        return {"gpt_analysis": "수집된 데이터가 없습니다.",
                "claude_insights": "", "source_count": 0, "sources": [],
                "per_url": []}

    needs = plan.get("needs", ["업체명", "주요서비스", "가격정책", "고객후기", "연락처"])

    # URL별 구조화 추출
    per_url = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console, transient=True
    ) as prog:
        t = prog.add_task("[cyan]URL별 GPT 분석 중...", total=len(results))
        for r in results:
            gpt = _analyze_url(r, topic, needs)
            per_url.append({**r, "gpt": gpt})
            prog.advance(t)

    # 전체 요약 분석
    ctx = "\n\n".join(
        f"[{r['title']}]\n출처: {r['url']}\n{r['content'][:1000]}"
        for r in results[:8]
    )

    gpt_out = call_gpt(
        f"리서치 주제: {topic}\n\n수집 데이터:\n{ctx}\n\n"
        f"핵심 분석, 주요 플레이어, 시장 현황, 시사점을 한국어로 작성하세요.",
        system="당신은 시니어 마케팅 리서치 애널리스트입니다. 핵심만 간결하게.",
        model="gpt-4o"
    )

    claude_out = call_claude(
        f"주제: {topic}\n\nGPT 분석 결과:\n{gpt_out}\n\n"
        f"전략적 시사점과 실행 가능한 액션 아이템 5개를 번호 목록으로 제시하세요.",
        system="마케팅 전략 전문가로서 실용적인 인사이트를 제공하세요."
    )

    return {
        "gpt_analysis":    gpt_out,
        "claude_insights": claude_out,
        "source_count":    len(results),
        "sources":         [{"title": r["title"], "url": r["url"]} for r in results[:10]],
        "per_url":         per_url,
        "needs":           needs,
    }

# ═══════════════════════════════════════════════════════
#  결과 출력
# ═══════════════════════════════════════════════════════
def display_results(topic: str, plan: dict, analysis: dict):
    console.print()
    console.print(Rule(f"[bold cyan]📊  {topic}[/bold cyan]", style="bright_blue"))

    console.print(Panel(
        f"[bold]요약[/bold]  {plan.get('summary', topic)}\n"
        f"[bold]수집[/bold]  {analysis['source_count']}개 페이지\n"
        f"[bold]방향[/bold]  {plan.get('analysis_angle','')}",
        title="[bold]📋 개요[/bold]", border_style="blue", padding=(0,2)
    ))

    if analysis.get("gpt_analysis"):
        console.print()
        console.print(Panel(
            analysis["gpt_analysis"],
            title="[bold]🤖 GPT-4o 분석[/bold]",
            border_style="green", padding=(1,2)
        ))

    if analysis.get("claude_insights"):
        console.print()
        console.print(Panel(
            analysis["claude_insights"],
            title="[bold]💡 Claude 전략 인사이트[/bold]",
            border_style="yellow", padding=(1,2)
        ))

    if analysis.get("sources"):
        console.print()
        tbl = Table(title="📌 참고 출처", border_style="dim", show_header=True, header_style="bold")
        tbl.add_column("#", style="dim", width=3)
        tbl.add_column("제목", style="cyan", max_width=50)
        tbl.add_column("URL", style="dim", max_width=55)
        for i, s in enumerate(analysis["sources"], 1):
            tbl.add_row(str(i), s["title"][:50], s["url"][:55])
        console.print(tbl)

# ═══════════════════════════════════════════════════════
#  파일 저장
# ═══════════════════════════════════════════════════════
def save_results(topic: str, plan: dict, analysis: dict, results: list):
    console.print()
    console.print("[bold]저장 형식:[/bold]  [cyan]1[/cyan] Excel  [cyan]2[/cyan] PDF  "
                  "[cyan]3[/cyan] PPT  [cyan]4[/cyan] 전체  [cyan]0[/cyan] 건너뜀")
    choice = Prompt.ask("선택", choices=["0","1","2","3","4"], default="1")
    if choice == "0":
        return

    ts   = datetime.now().strftime("%Y%m%d_%H%M")
    safe = re.sub(r'[^\w가-힣]', '_', topic)[:30]
    base = f"리서치_{safe}_{ts}"
    saved = []

    if choice in ("1","4"):
        p = _save_excel(base, topic, analysis, results)
        if p: saved.append(p)

    if choice in ("2","4") and _PDF:
        p = _save_pdf(base, topic, analysis)
        if p: saved.append(p)
    elif choice == "2" and not _PDF:
        console.print("[yellow]reportlab 패키지 없음 — PDF 불가[/yellow]")

    if choice in ("3","4") and _PPT:
        p = _save_ppt(base, topic, analysis)
        if p: saved.append(p)
    elif choice == "3" and not _PPT:
        console.print("[yellow]python-pptx 패키지 없음 — PPT 불가[/yellow]")

    if saved:
        console.print()
        console.print(Panel(
            "\n".join(f"[green]✅[/green]  {s}" for s in saved),
            title="[bold]저장 완료[/bold]", border_style="green"
        ))

def _save_excel(base, topic, analysis, results):
    try:
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter

        per_url = analysis.get("per_url", [])
        needs   = analysis.get("needs", [])
        path    = os.path.join(SAVE_DIR, base+".xlsx")

        THIN = Side(style="thin", color="CCCCCC")
        def cell(ws, row, col, value, bold=False, bg=None, fc="000000",
                 wrap=True, size=10, align="left"):
            c = ws.cell(row=row, column=col, value=value)
            c.font      = Font(bold=bold, color=fc, size=size, name="맑은 고딕")
            c.alignment = Alignment(horizontal=align, vertical="top", wrap_text=wrap)
            c.border    = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
            if bg:
                c.fill = PatternFill("solid", fgColor=bg)
            return c

        wb = openpyxl.Workbook()

        # ── 시트1: 상세 데이터 ──────────────────────────────
        ws = wb.active
        ws.title = "리서치 결과"

        fixed_cols = [("No",5),("출처",8),("URL",32),("도메인",18),
                      ("페이지 제목",26),("한줄 요약",30)]
        all_headers = fixed_cols + [(n, 28) for n in needs] + [("헤딩 구조",28),("오류",14)]
        total_cols  = len(all_headers)

        # 타이틀 행
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
        tc = ws.cell(row=1, column=1,
                     value=f"웹 리서치 — {topic}  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        tc.font      = Font(bold=True, size=13, color="FFFFFF", name="맑은 고딕")
        tc.fill      = PatternFill("solid", fgColor="1F3864")
        tc.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 28

        # 헤더 행
        for ci, (hdr, width) in enumerate(all_headers, 1):
            cell(ws, 2, ci, hdr, bold=True, bg="2F5496", fc="FFFFFF", align="center")
            ws.column_dimensions[get_column_letter(ci)].width = width
        ws.row_dimensions[2].height = 22

        # 데이터 행
        for ri, data in enumerate(per_url, 1):
            er  = ri + 2
            bg  = "EBF0FA" if ri % 2 else "FFFFFF"
            gpt = data.get("gpt", {})
            ws.row_dimensions[er].height = 80

            # 출처: 네이버/DDG 구분 (URL 기반 추정)
            src = "네이버" if "naver" in data.get("url","") else "웹"

            row_vals = [
                ri,
                src,
                data.get("url",""),
                data.get("domain",""),
                data.get("page_title", data.get("title","")),
                gpt.get("한줄요약",""),
            ]
            for n in needs:
                row_vals.append(gpt.get(n, ""))
            row_vals += [data.get("headings",""), data.get("error","")]

            for ci, val in enumerate(row_vals, 1):
                cell(ws, er, ci, str(val) if val else "", bg=bg,
                     align="center" if ci == 1 else "left")

        ws.freeze_panes = "B3"

        # ── 시트2: 종합 분석 ────────────────────────────────
        ws2 = wb.create_sheet("종합 분석")
        ws2.column_dimensions["A"].width = 20
        ws2.column_dimensions["B"].width = 90

        def r2(row, label, text):
            ws2.cell(row=row, column=1, value=label).font = Font(bold=True, name="맑은 고딕", size=10)
            c = ws2.cell(row=row, column=2, value=text)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.font = Font(name="맑은 고딕", size=10)
            ws2.row_dimensions[row].height = max(60, len(str(text))//3)

        r2(1, "리서치 주제", topic)
        r2(2, "GPT-4o 분석",    analysis.get("gpt_analysis",""))
        r2(3, "Claude 인사이트", analysis.get("claude_insights",""))

        wb.save(path)
        return path
    except Exception as e:
        console.print(f"[red]Excel 오류: {e}[/red]")

def _save_pdf(base, topic, analysis):
    try:
        path = os.path.join(SAVE_DIR, base+".pdf")
        pdfmetrics.registerFont(UnicodeCIDFont('HYSMyeongJo-Medium'))
        ks = ParagraphStyle('k', fontName='HYSMyeongJo-Medium', fontSize=10, leading=16)
        kh = ParagraphStyle('h', fontName='HYSMyeongJo-Medium', fontSize=14, leading=20, spaceAfter=8)
        doc = SimpleDocTemplate(path, pagesize=A4)
        story = [Paragraph(f"리서치 리포트: {topic}", kh), Spacer(1,10),
                 Paragraph("GPT-4o 분석", kh)]
        for ln in analysis.get("gpt_analysis","").split("\n"):
            if ln.strip(): story.append(Paragraph(ln, ks))
        story += [Spacer(1,10), Paragraph("Claude 전략 인사이트", kh)]
        for ln in analysis.get("claude_insights","").split("\n"):
            if ln.strip(): story.append(Paragraph(ln, ks))
        doc.build(story)
        return path
    except Exception as e:
        console.print(f"[red]PDF 오류: {e}[/red]")

def _save_ppt(base, topic, analysis):
    try:
        path = os.path.join(SAVE_DIR, base+".pptx")
        prs = Presentation()
        def add_slide(title_text, body_text):
            sl = prs.slides.add_slide(prs.slide_layouts[1])
            sl.shapes.title.text = title_text
            sl.placeholders[1].text = body_text[:900]
        sl0 = prs.slides.add_slide(prs.slide_layouts[0])
        sl0.shapes.title.text = f"리서치 리포트: {topic}"
        sl0.placeholders[1].text = datetime.now().strftime("%Y-%m-%d")
        add_slide("GPT-4o 분석",        analysis.get("gpt_analysis","")[:900])
        add_slide("Claude 전략 인사이트", analysis.get("claude_insights","")[:900])
        prs.save(path)
        return path
    except Exception as e:
        console.print(f"[red]PPT 오류: {e}[/red]")

# ═══════════════════════════════════════════════════════
#  메인
# ═══════════════════════════════════════════════════════
def main():
    console.clear()
    console.print(Panel(
        "[bold cyan]🔍  웹 리서치 어시스턴트[/bold cyan]\n"
        "[dim]DeepSeek · GPT-4o · Claude 기반 자동 웹조사 & 전략 분석[/dim]",
        border_style="bright_blue", padding=(1,6)
    ))
    console.print(f"\n[dim]결과 저장 폴더: {SAVE_DIR}[/dim]")

    while True:
        console.print()
        console.print(Rule(style="dim"))
        console.print("[bold]무엇을 조사할까요?[/bold]")
        console.print("[dim]예) 관리감독자 교육 경쟁사   /   AI 마케팅 툴 비교   /   대한산업안전협회 분석[/dim]")
        console.print("[dim]종료: q[/dim]")

        topic = Prompt.ask("\n[bold cyan]→[/bold cyan]").strip()
        if not topic or topic.lower() == "q":
            console.print("\n[dim]프로그램을 종료합니다.[/dim]")
            break

        console.print()
        console.print("[bold]조사 깊이:[/bold]  [cyan]1[/cyan] 빠른(3분)  [cyan]2[/cyan] 보통(7분)  [cyan]3[/cyan] 심층(15분)")
        dc = Prompt.ask("선택", choices=["1","2","3"], default="2")
        depth = {"1":"빠른 조사","2":"일반 조사","3":"심층 조사"}[dc]

        console.print()
        console.print(Rule("[cyan]리서치 시작[/cyan]", style="bright_blue"))

        # 1. 플랜
        with console.status("[cyan]DeepSeek R1 — 리서치 계획 수립 중...[/cyan]"):
            plan = make_plan(topic, depth)
            plan["_depth"] = depth
        console.print(f"[green]✓[/green] 검색 쿼리 {len(plan['queries'])}개 생성")

        # 2. 수집
        console.print("[cyan]웹 검색 및 페이지 수집 중...[/cyan]")
        results = run_research(plan)
        console.print(f"[green]✓[/green] {len(results)}개 페이지 수집 완료")

        # 3. 분석 (URL별 GPT 추출 + 종합 분석)
        console.print("[cyan]URL별 GPT 구조화 추출 + 종합 분석 중...[/cyan]")
        analysis = analyze(topic, plan, results)
        console.print("[green]✓[/green] 분석 완료")

        # 4. 출력
        display_results(topic, plan, analysis)

        # 5. 저장
        save_results(topic, plan, analysis, results)

        # 6. 계속?
        console.print()
        if not Confirm.ask("[bold]새 주제를 조사할까요?[/bold]", default=True):
            console.print("\n[dim]프로그램을 종료합니다.[/dim]")
            break

if __name__ == "__main__":
    main()
