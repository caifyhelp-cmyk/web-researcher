# -*- coding: utf-8 -*-
"""
MAESTRO v1.1 — 현존 최강 AI 오케스트레이터

조경일 뇌 에이전트 × GPT-4o × Claude Code × DeepSeek × Grok
Claude Code 동일 Tool Suite + ReAct 에이전트 루프

아키텍처:
  - GPT-4o      : 메인 오케스트레이터 (도구 호출, 흐름 제어)
  - Claude Code : 실제 Claude Code CLI 호출 (코딩/파일작업 최강)
  - DeepSeek    : 복잡한 추론, 수학, 단계적 분석
  - Claude API  : 긴 문서, 정밀 분석, 세밀한 글쓰기
  - Grok        : 실시간 정보, 최신 이슈
  - 뇌 에이전트 : 마케팅/전략 판단 (조경일 인지 패턴 1,180개)
"""

import os, sys, json, re, subprocess, time
from pathlib import Path
from datetime import datetime

VERSION = "1.4.0"

# ── Rich UI ──────────────────────────────────────────────────────
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt, Confirm
from rich.rule import Rule
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

console = Console(highlight=False)

# ── API 키 ───────────────────────────────────────────────────────
try:
    import _local_keys
except ImportError:
    pass

OPENAI_KEY    = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEEPSEEK_KEY  = os.getenv("DEEPSEEK_API_KEY", "")
GROK_KEY      = os.getenv("GROK_API_KEY", "")

from openai    import OpenAI
from anthropic import Anthropic

oai      = OpenAI(api_key=OPENAI_KEY)                                         if OPENAI_KEY    else None
ant      = Anthropic(api_key=ANTHROPIC_KEY)                                   if ANTHROPIC_KEY else None
deepseek = OpenAI(api_key=DEEPSEEK_KEY, base_url="https://api.deepseek.com") if DEEPSEEK_KEY  else None
grok_ai  = OpenAI(api_key=GROK_KEY,     base_url="https://api.x.ai/v1")      if GROK_KEY      else None

# ── 오케스트레이터 ────────────────────────────────────────────────
try:
    import orchestrator as orch
    _ORCH = True
except Exception:
    _ORCH = False

# ── 웹 리서치 파이프라인 (app_local.py 통합) ─────────────────────
try:
    import app_local as _rl
    _RL = True
except Exception:
    _RL = False

# ── 집단지성 파이프라인 ───────────────────────────────────────────
try:
    import pattern_collector as _pc
    _PC = True
except Exception:
    _PC = False

# 마지막 리서치 결과 캐시 (save_research 도구에서 재사용)
_last_research: dict = {}

# 저장 폴더
_SAVE_DIR = Path(os.path.expanduser("~")) / "Desktop" / "MAESTRO결과"
_SAVE_DIR.mkdir(parents=True, exist_ok=True)

# ── 뇌 에이전트 ──────────────────────────────────────────────────
_BRAIN_URL = "https://brain-agent-v9wl.onrender.com/api/research"

import urllib.request, urllib.error

def _call_brain(situation: str) -> str:
    try:
        body = json.dumps({"situation": situation}, ensure_ascii=False).encode()
        req  = urllib.request.Request(_BRAIN_URL, data=body, method="POST",
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        if data.get("ok"):
            parts = []
            if data.get("judgment"): parts.append(f"판단: {data['judgment']}")
            if data.get("action"):   parts.append(f"액션: {data['action']}")
            if data.get("reason"):   parts.append(f"근거: {data['reason']}")
            return "\n".join(parts) or "[뇌 에이전트 응답 없음]"
    except Exception as e:
        return f"[뇌 에이전트 연결 실패: {e}]"
    return "[뇌 에이전트 응답 없음]"


# ═══════════════════════════════════════════════════════════════
#  TOOL SUITE — Claude Code 동일 11개 도구
# ═══════════════════════════════════════════════════════════════

def _tool_read_file(path: str, offset: int = 0, limit: int = 0) -> str:
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return f"[파일 없음: {path}]"
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if offset:
            lines = lines[offset:]
        if limit:
            lines = lines[:limit]
        numbered = [f"{i+1+offset}\t{l}" for i, l in enumerate(lines)]
        return "\n".join(numbered)
    except Exception as e:
        return f"[읽기 오류: {e}]"


def _tool_write_file(path: str, content: str) -> str:
    try:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"[완료] {path} 저장됨 ({len(content.splitlines())}줄)"
    except Exception as e:
        return f"[쓰기 오류: {e}]"


def _tool_edit_file(path: str, old_str: str, new_str: str) -> str:
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return f"[파일 없음: {path}]"
        content = p.read_text(encoding="utf-8")
        if old_str not in content:
            return f"[매칭 실패] '{old_str[:60]}...' 를 파일에서 찾을 수 없음"
        new_content = content.replace(old_str, new_str, 1)
        p.write_text(new_content, encoding="utf-8")
        return f"[완료] {path} 수정됨"
    except Exception as e:
        return f"[수정 오류: {e}]"


_DANGEROUS = ["rm -rf", "format", "del /f", "shutdown", "drop table",
               "DROP TABLE", ":(){", "mkfs", "dd if="]

def _tool_run_bash(command: str, timeout: int = 30, _confirmed: bool = False) -> str:
    if not _confirmed:
        for danger in _DANGEROUS:
            if danger.lower() in command.lower():
                return f"[차단] 위험 명령어 감지: '{danger}'. 직접 실행하려면 확인 필요."
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True,
            text=True, timeout=timeout, encoding="utf-8", errors="replace"
        )
        out = (result.stdout + result.stderr).strip()
        return out[:4000] if out else "[출력 없음]"
    except subprocess.TimeoutExpired:
        return f"[타임아웃] {timeout}초 초과"
    except Exception as e:
        return f"[실행 오류: {e}]"


def _tool_glob(pattern: str, path: str = ".") -> str:
    try:
        base = Path(path).expanduser()
        matches = sorted(base.glob(pattern))
        if not matches:
            return "[결과 없음]"
        return "\n".join(str(m) for m in matches[:100])
    except Exception as e:
        return f"[glob 오류: {e}]"


def _tool_grep(pattern: str, path: str = ".", file_pattern: str = "") -> str:
    try:
        cmd = ["grep", "-rn", "--include", file_pattern or "*", pattern, path]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=15)
        out = result.stdout.strip()
        if not out:
            # Windows fallback — findstr
            cmd2 = f'findstr /s /n /i "{pattern}" "{path}\\*{file_pattern}"'
            result2 = subprocess.run(cmd2, shell=True, capture_output=True,
                                     text=True, encoding="utf-8", errors="replace", timeout=15)
            out = result2.stdout.strip()
        return out[:4000] if out else "[결과 없음]"
    except Exception as e:
        return f"[grep 오류: {e}]"


def _tool_list_dir(path: str = ".") -> str:
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return f"[경로 없음: {path}]"
        items = sorted(p.iterdir())
        lines = []
        for item in items[:200]:
            tag  = "D" if item.is_dir() else "F"
            size = item.stat().st_size if item.is_file() else 0
            lines.append(f"[{tag}] {item.name}  {size:,}B" if size else f"[{tag}] {item.name}")
        return "\n".join(lines) or "[비어있음]"
    except Exception as e:
        return f"[목록 오류: {e}]"


def _tool_web_search(query: str, num_results: int = 5) -> str:
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=num_results):
                results.append(f"[{r['title']}]\n{r['href']}\n{r['body']}\n")
        return "\n---\n".join(results) if results else "[결과 없음]"
    except Exception as e:
        return f"[검색 오류: {e}]"


def _tool_web_fetch(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="replace")
        # 태그 제거
        text = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:5000]
    except Exception as e:
        return f"[fetch 오류: {e}]"


def _tool_ask_specialist(model: str, prompt: str) -> str:
    """전문 LLM에게 위임"""
    if model == "deepseek":
        if not deepseek:
            return "[DeepSeek API 키 없음]"
        try:
            r = deepseek.chat.completions.create(
                model="deepseek-reasoner",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000
            )
            return r.choices[0].message.content.strip()
        except Exception as e:
            return f"[DeepSeek 오류: {e}]"

    elif model == "claude":
        if not ant:
            return "[Claude API 키 없음]"
        try:
            r = ant.messages.create(
                model="claude-opus-4-6", max_tokens=3000,
                system="당신은 최고 수준의 분석가이자 전략가입니다.",
                messages=[{"role": "user", "content": prompt}]
            )
            return r.content[0].text.strip()
        except Exception as e:
            return f"[Claude 오류: {e}]"

    elif model == "grok":
        if not grok_ai:
            return "[Grok API 키 없음]"
        try:
            r = grok_ai.chat.completions.create(
                model="grok-3",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000
            )
            return r.choices[0].message.content.strip()
        except Exception as e:
            return f"[Grok 오류: {e}]"

    elif model == "gpt-4o":
        if not oai:
            return "[OpenAI API 키 없음]"
        try:
            r = oai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000
            )
            return r.choices[0].message.content.strip()
        except Exception as e:
            return f"[GPT-4o 오류: {e}]"

    return f"[알 수 없는 모델: {model}]"


def _tool_generate_image(prompt: str, size: str = "1024x1024", quality: str = "standard") -> str:
    """DALL-E 3로 이미지 생성 후 저장"""
    if not oai:
        return "[OpenAI API 키 없음]"
    try:
        resp = oai.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,
            quality=quality,
            n=1
        )
        url = resp.data[0].url
        revised = resp.data[0].revised_prompt or prompt

        # 다운로드 & 저장
        import urllib.request as _ur
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = _SAVE_DIR / f"image_{ts}.png"
        _ur.urlretrieve(url, fname)
        return f"이미지 생성 완료\n저장 경로: {fname}\n실제 프롬프트: {revised}"
    except Exception as e:
        return f"[이미지 생성 오류: {e}]"


def _tool_create_chart(chart_type: str, data: dict, title: str = "",
                       x_label: str = "", y_label: str = "",
                       filename: str = "") -> str:
    """
    matplotlib으로 차트/그래프 생성 후 저장.
    chart_type: bar, line, pie, scatter, area
    data: {"labels": [...], "values": [...]} 또는 {"series": [{"name":..,"values":[..]},...], "labels":[...]}
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm

        # 한글 폰트 설정
        font_candidates = ["Malgun Gothic", "NanumGothic", "AppleGothic", "sans-serif"]
        for font in font_candidates:
            try:
                plt.rcParams["font.family"] = font
                plt.rcParams["axes.unicode_minus"] = False
                break
            except Exception:
                continue

        fig, ax = plt.subplots(figsize=(10, 6))

        labels = data.get("labels", [])
        values = data.get("values", [])
        series = data.get("series", [])

        ctype = chart_type.lower()

        if ctype == "pie":
            ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
            ax.axis("equal")

        elif ctype == "bar":
            if series:
                x = range(len(labels))
                w = 0.8 / len(series)
                for i, s in enumerate(series):
                    offset = [xi + i * w for xi in x]
                    ax.bar(offset, s["values"], width=w, label=s["name"])
                ax.set_xticks([xi + w * (len(series)-1)/2 for xi in x])
                ax.set_xticklabels(labels)
                ax.legend()
            else:
                ax.bar(labels, values)

        elif ctype == "line":
            if series:
                for s in series:
                    ax.plot(labels, s["values"], marker="o", label=s["name"])
                ax.legend()
            else:
                ax.plot(labels, values, marker="o")

        elif ctype == "area":
            if series:
                for s in series:
                    ax.fill_between(range(len(labels)), s["values"], alpha=0.4, label=s["name"])
                    ax.plot(range(len(labels)), s["values"])
                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels)
                ax.legend()
            else:
                ax.fill_between(range(len(labels)), values, alpha=0.4)
                ax.plot(range(len(labels)), values)
                ax.set_xticks(range(len(labels)))
                ax.set_xticklabels(labels)

        elif ctype == "scatter":
            x_vals = data.get("x", values)
            y_vals = data.get("y", values)
            ax.scatter(x_vals, y_vals)

        if title:   ax.set_title(title, fontsize=14, fontweight="bold")
        if x_label: ax.set_xlabel(x_label)
        if y_label: ax.set_ylabel(y_label)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname_str = filename or f"chart_{ts}.png"
        if not fname_str.endswith(".png"):
            fname_str += ".png"
        save_path = _SAVE_DIR / fname_str
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        plt.close()
        return f"차트 생성 완료\n저장 경로: {save_path}"
    except Exception as e:
        return f"[차트 생성 오류: {e}]"


def _tool_save_research(formats: list) -> str:
    """
    마지막 리서치 결과를 원하는 형식으로 저장.
    formats: ["excel"], ["pdf"], ["ppt"], ["excel","pdf","ppt"] 등 조합 가능
    """
    if not _last_research:
        return "[저장할 리서치 결과가 없습니다. 먼저 리서치를 실행하세요.]"
    if not _RL:
        return "[리서치 모듈 로드 실패]"

    import re as _re
    from datetime import datetime as _dt

    topic    = _last_research.get("topic", "리서치")
    plan     = _last_research.get("plan", {})
    analysis = _last_research.get("analysis", {})
    results  = _last_research.get("results", [])

    ts   = _dt.now().strftime("%Y%m%d_%H%M")
    safe = _re.sub(r'[^\w가-힣]', '_', topic)[:30]
    base = f"리서치_{safe}_{ts}"
    saved = []

    fmt = [f.lower() for f in formats]

    if "excel" in fmt:
        try:
            p = _rl._save_excel(base, topic, analysis, results)
            if p: saved.append(f"Excel: {p}")
        except Exception as e:
            saved.append(f"Excel 실패: {e}")

    if "pdf" in fmt:
        try:
            p = _rl._save_pdf(base, topic, analysis)
            if p: saved.append(f"PDF: {p}")
        except Exception as e:
            saved.append(f"PDF 실패: {e}")

    if "ppt" in fmt:
        try:
            p = _rl._save_ppt(base, topic, analysis)
            if p: saved.append(f"PPT: {p}")
        except Exception as e:
            saved.append(f"PPT 실패: {e}")

    if not saved:
        return "[저장된 파일 없음 — excel, pdf, ppt 중 하나 이상 지정하세요]"
    return "저장 완료:\n" + "\n".join(saved)


def _tool_web_research(topic: str, depth: str = "중간") -> str:
    """
    기존 웹 리서치 파이프라인 전체 실행.
    make_plan → 웹 수집 → 구조화 추출 → 시장 분석 → 전략 인사이트
    결과를 텍스트 요약으로 반환.
    """
    if not _RL:
        return "[웹 리서치 모듈 로드 실패]"
    try:
        console.print(f"  [dim]  플랜 수립 중...[/dim]")
        plan = _rl.make_plan(topic, depth)
        plan["_depth"] = depth

        console.print(f"  [dim]  웹 수집 중 (쿼리 {len(plan.get('queries', []))}개)...[/dim]")
        results = _rl.run_research(plan)

        console.print(f"  [dim]  {len(results)}개 페이지 분석 중...[/dim]")
        analysis = _rl.analyze(topic, plan, results)

        # 텍스트 요약 구성
        lines = []
        lines.append(f"## 리서치 결과: {topic}")
        lines.append(f"수집 페이지: {len(results)}개\n")

        summary = analysis.get("summary", "")
        if summary:
            lines.append(f"### 시장 현황\n{summary}\n")

        strategy = analysis.get("strategy", "")
        if strategy:
            lines.append(f"### 전략 인사이트\n{strategy}\n")

        per_url = analysis.get("per_url", [])
        if per_url:
            lines.append("### 주요 업체")
            for item in per_url[:8]:
                name = item.get("업체명") or item.get("name") or ""
                url  = item.get("url", "")
                if name:
                    lines.append(f"- {name}  {url}")

        # 결과 캐시 (save_research 도구에서 재사용)
        _last_research.update({
            "topic": topic, "plan": plan,
            "analysis": analysis, "results": results
        })

        lines.append("\n어떤 형식으로 저장할까요? Excel, PDF, PPT 중 원하는 대로 말씀해주세요.")
        return "\n".join(lines)
    except Exception as e:
        return f"[웹 리서치 오류: {e}]"


def _tool_ask_claude_code(prompt: str, cwd: str = ".", timeout: int = 180) -> str:
    """
    실제 Claude Code CLI를 subprocess로 호출.
    코딩, 파일 작업, 복잡한 멀티파일 수정에 최적.
    claude -p "prompt" --output-format json --dangerously-skip-permissions
    """
    import shutil
    claude_bin = shutil.which("claude") or "claude"

    work_dir = str(Path(cwd).expanduser().resolve())

    cmd = [
        claude_bin,
        "-p", prompt,
        "--output-format", "json",
        "--dangerously-skip-permissions",
        "--add-dir", work_dir,
    ]

    # Claude Code는 OAuth 세션으로 인증 — ANTHROPIC_API_KEY 제거해야 충돌 없음
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=work_dir,
            env=env,
        )
        raw = result.stdout.strip()
        if not raw:
            err = result.stderr.strip()
            return f"[Claude Code 출력 없음] {err[:300]}"

        # JSON 파싱 시도
        try:
            data = json.loads(raw)
            # stream-json 마지막 라인일 수도 있음
            if isinstance(data, list):
                data = data[-1]
            if data.get("is_error"):
                return f"[Claude Code 오류] {data.get('result', raw)}"
            return data.get("result", raw)
        except json.JSONDecodeError:
            # 텍스트 형식 그대로 반환
            return raw

    except subprocess.TimeoutExpired:
        return f"[Claude Code 타임아웃] {timeout}초 초과"
    except FileNotFoundError:
        return "[Claude Code 미설치] 'claude' 명령어를 찾을 수 없습니다."
    except Exception as e:
        return f"[Claude Code 오류: {e}]"


def _exec_tool(name: str, args: dict) -> str:
    """도구 디스패처"""
    dispatch = {
        "read_file":        lambda: _tool_read_file(**args),
        "write_file":       lambda: _tool_write_file(**args),
        "edit_file":        lambda: _tool_edit_file(**args),
        "run_bash":         lambda: _tool_run_bash(**args),
        "glob_search":      lambda: _tool_glob(**args),
        "grep_search":      lambda: _tool_grep(**args),
        "list_dir":         lambda: _tool_list_dir(**args),
        "web_search":       lambda: _tool_web_search(**args),
        "web_fetch":        lambda: _tool_web_fetch(**args),
        "ask_brain":        lambda: _call_brain(args.get("situation", "")),
        "ask_specialist":   lambda: _tool_ask_specialist(
                                args.get("model", "gpt-4o"), args.get("prompt", "")),
        "ask_claude_code":  lambda: _tool_ask_claude_code(
                                args.get("prompt", ""),
                                args.get("cwd", "."),
                                args.get("timeout", 180)),
        "web_research":     lambda: _tool_web_research(
                                args.get("topic", ""),
                                args.get("depth", "중간")),
        "save_research":    lambda: _tool_save_research(
                                args.get("formats", ["excel"])),
        "generate_image":   lambda: _tool_generate_image(
                                args.get("prompt", ""),
                                args.get("size", "1024x1024"),
                                args.get("quality", "standard")),
        "create_chart":     lambda: _tool_create_chart(
                                args.get("chart_type", "bar"),
                                args.get("data", {}),
                                args.get("title", ""),
                                args.get("x_label", ""),
                                args.get("y_label", ""),
                                args.get("filename", "")),
    }
    fn = dispatch.get(name)
    if fn:
        return fn()
    return f"[알 수 없는 도구: {name}]"


# ═══════════════════════════════════════════════════════════════
#  GPT-4o Tool Definitions (OpenAI function calling 형식)
# ═══════════════════════════════════════════════════════════════

_TOOL_DEFS = [
    {"type": "function", "function": {
        "name": "read_file",
        "description": "파일 내용을 읽습니다.",
        "parameters": {"type": "object", "properties": {
            "path":   {"type": "string"},
            "offset": {"type": "integer", "description": "시작 줄 번호 (선택)"},
            "limit":  {"type": "integer", "description": "읽을 줄 수 (선택)"}
        }, "required": ["path"]}
    }},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "파일을 생성하거나 전체 내용을 씁니다.",
        "parameters": {"type": "object", "properties": {
            "path":    {"type": "string"},
            "content": {"type": "string"}
        }, "required": ["path", "content"]}
    }},
    {"type": "function", "function": {
        "name": "edit_file",
        "description": "파일에서 특정 문자열을 찾아 교체합니다. old_str는 파일에서 정확히 일치해야 합니다.",
        "parameters": {"type": "object", "properties": {
            "path":    {"type": "string"},
            "old_str": {"type": "string"},
            "new_str": {"type": "string"}
        }, "required": ["path", "old_str", "new_str"]}
    }},
    {"type": "function", "function": {
        "name": "run_bash",
        "description": "터미널 명령어를 실행합니다.",
        "parameters": {"type": "object", "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer"}
        }, "required": ["command"]}
    }},
    {"type": "function", "function": {
        "name": "glob_search",
        "description": "glob 패턴으로 파일을 검색합니다. 예: **/*.py",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string"},
            "path":    {"type": "string", "description": "검색 시작 경로 (기본: 현재 디렉토리)"}
        }, "required": ["pattern"]}
    }},
    {"type": "function", "function": {
        "name": "grep_search",
        "description": "파일 내용에서 패턴을 검색합니다.",
        "parameters": {"type": "object", "properties": {
            "pattern":      {"type": "string"},
            "path":         {"type": "string"},
            "file_pattern": {"type": "string", "description": "파일 필터 (예: *.py)"}
        }, "required": ["pattern"]}
    }},
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "디렉토리 내용을 나열합니다.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}
        }, "required": ["path"]}
    }},
    {"type": "function", "function": {
        "name": "web_search",
        "description": "웹에서 정보를 검색합니다.",
        "parameters": {"type": "object", "properties": {
            "query":       {"type": "string"},
            "num_results": {"type": "integer"}
        }, "required": ["query"]}
    }},
    {"type": "function", "function": {
        "name": "web_fetch",
        "description": "URL의 페이지 내용을 가져옵니다.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"}
        }, "required": ["url"]}
    }},
    {"type": "function", "function": {
        "name": "ask_brain",
        "description": (
            "조경일 뇌 에이전트에게 마케팅/전략/비즈니스 판단을 요청합니다. "
            "전략적 결정, 마케팅 방향, 우선순위 판단 등에 사용하세요."
        ),
        "parameters": {"type": "object", "properties": {
            "situation": {"type": "string", "description": "판단이 필요한 상황 설명"}
        }, "required": ["situation"]}
    }},
    {"type": "function", "function": {
        "name": "ask_specialist",
        "description": (
            "특정 LLM 전문가에게 작업을 위임합니다.\n"
            "- deepseek: 복잡한 추론, 수학, 코드 알고리즘, 단계별 분석\n"
            "- claude: 긴 문서 분석, 세밀한 글쓰기, 미묘한 뉘앙스 판단\n"
            "- grok: 실시간/최신 정보, 트렌드, 뉴스\n"
            "- gpt-4o: 구조화 출력, 일반 코딩"
        ),
        "parameters": {"type": "object", "properties": {
            "model":  {"type": "string", "enum": ["deepseek", "claude", "grok", "gpt-4o"]},
            "prompt": {"type": "string"}
        }, "required": ["model", "prompt"]}
    }},
    {"type": "function", "function": {
        "name": "generate_image",
        "description": "DALL-E 3로 이미지를 생성합니다. 마케팅 배너, 썸네일, 일러스트, 아이디어 시각화 등에 사용하세요.",
        "parameters": {"type": "object", "properties": {
            "prompt":  {"type": "string", "description": "이미지 설명 (구체적일수록 좋음)"},
            "size":    {"type": "string", "enum": ["1024x1024", "1792x1024", "1024x1792"],
                        "description": "정사각형|가로형|세로형"},
            "quality": {"type": "string", "enum": ["standard", "hd"]}
        }, "required": ["prompt"]}
    }},
    {"type": "function", "function": {
        "name": "create_chart",
        "description": "데이터를 차트/그래프로 시각화합니다. bar(막대), line(선), pie(파이), area(면적), scatter(산점도) 지원.",
        "parameters": {"type": "object", "properties": {
            "chart_type": {"type": "string", "enum": ["bar", "line", "pie", "area", "scatter"]},
            "data": {
                "type": "object",
                "description": "단일 시리즈: {labels:[...], values:[...]} / 복수 시리즈: {labels:[...], series:[{name:..,values:[..]},..]}",
            },
            "title":    {"type": "string"},
            "x_label":  {"type": "string"},
            "y_label":  {"type": "string"},
            "filename": {"type": "string", "description": "저장 파일명 (확장자 없이)"}
        }, "required": ["chart_type", "data"]}
    }},
    {"type": "function", "function": {
        "name": "save_research",
        "description": (
            "리서치 결과를 원하는 형식으로 저장합니다. "
            "web_research 실행 후 사용자가 저장 형식을 말하면 호출하세요. "
            "Excel, PDF, PPT 중 원하는 것을 복수로 지정할 수 있습니다."
        ),
        "parameters": {"type": "object", "properties": {
            "formats": {
                "type": "array",
                "items": {"type": "string", "enum": ["excel", "pdf", "ppt"]},
                "description": "저장할 형식 목록. 예: ['excel'], ['excel','pdf'], ['excel','pdf','ppt']"
            }
        }, "required": ["formats"]}
    }},
    {"type": "function", "function": {
        "name": "web_research",
        "description": (
            "웹 리서치 전체 파이프라인을 실행합니다. "
            "경쟁사 분석, 시장 조사, 업체 비교, 트렌드 파악 등 "
            "특정 주제에 대해 웹을 자동 수집하고 구조화 분석까지 완료합니다. "
            "결과는 자동으로 파일로 저장됩니다."
        ),
        "parameters": {"type": "object", "properties": {
            "topic": {"type": "string", "description": "조사할 주제"},
            "depth": {"type": "string",
                      "description": "조사 깊이: '빠른' (5개 URL), '중간' (10개), '깊은' (20개)",
                      "enum": ["빠른", "중간", "깊은"]}
        }, "required": ["topic"]}
    }},
    {"type": "function", "function": {
        "name": "ask_claude_code",
        "description": (
            "실제 Claude Code CLI를 호출합니다. "
            "파일 생성/수정/삭제, 복잡한 코딩 작업, 멀티파일 리팩토링, "
            "프로그램 전체 구현 등 코딩 관련 작업에 최우선 사용하세요. "
            "Claude Code가 직접 파일을 읽고 수정하고 테스트까지 수행합니다."
        ),
        "parameters": {"type": "object", "properties": {
            "prompt":  {"type": "string", "description": "Claude Code에게 전달할 작업 지시"},
            "cwd":     {"type": "string", "description": "작업 디렉토리 경로 (기본: 현재 폴더)"},
            "timeout": {"type": "integer", "description": "최대 대기 시간(초, 기본 180)"}
        }, "required": ["prompt"]}
    }},
]


# ═══════════════════════════════════════════════════════════════
#  SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════

def _build_system_prompt() -> str:
    """집단지성 패턴을 포함한 시스템 프롬프트 동적 생성"""
    knowledge_section = ""
    if _PC:
        try:
            knowledge_section = _pc.build_knowledge_prompt()
        except Exception:
            pass
    return _SYSTEM_BASE + knowledge_section


_SYSTEM_BASE = """[절대 규칙] 모든 응답은 반드시 한국어로만 작성합니다. 영어로 절대 답변하지 않습니다. 전문 용어도 한국어로 설명합니다.

당신은 MAESTRO입니다.

조경일의 뇌 에이전트, Claude Code, DeepSeek, Grok을 손발처럼 부리는 AI 오케스트레이터입니다.
당신은 규칙집을 따르지 않습니다. 대화에서 상대방이 진짜 원하는 것을 파악하고, 그걸 가장 잘 해낼 수 있는 방법을 스스로 판단합니다.

---

## 당신이 가진 능력들

**generate_image** — DALL-E 3로 이미지를 만듭니다.
마케팅 배너, 썸네일, 아이디어 시각화, 일러스트 등 이미지가 필요할 때 씁니다.

**create_chart** — 데이터를 차트/그래프로 시각화합니다.
막대, 선, 파이, 면적, 산점도 지원. 숫자 데이터가 있으면 시각화를 제안하세요.

**web_research** — 웹 리서치 전체 파이프라인입니다.
경쟁사 분석, 시장 조사, 업체 비교 등 특정 주제를 깊게 파야 할 때 씁니다.
완료 후 반드시 사용자에게 "어떤 형식으로 저장할까요? (Excel / PDF / PPT)" 를 물어보세요.

**save_research** — 리서치 결과를 파일로 저장합니다.
사용자가 원하는 형식을 말하면 Excel, PDF, PPT 중 하나 또는 여러 개를 동시에 저장합니다.
"다 해줘", "전부" 같은 말이면 세 가지 모두 저장하세요.

**ask_claude_code** — 실제 Claude Code CLI를 호출합니다.
파일을 만들고, 코드를 짜고, 버그를 고치고, 테스트까지 돌립니다.
누군가 뭔가를 만들거나 수정하길 원할 때 가장 강력한 선택입니다.

**ask_specialist("deepseek")** — 깊이 생각해야 할 때 씁니다.
복잡한 추론, 알고리즘 설계, 단계별로 따져야 하는 분석.

**ask_specialist("claude")** — 섬세하게 표현해야 할 때 씁니다.
긴 문서, 뉘앙스가 중요한 글쓰기, 정밀한 언어 작업.

**ask_specialist("grok")** — 지금 세상에서 일어나는 일을 알아야 할 때 씁니다.
최신 뉴스, 트렌드, 실시간 정보.

**ask_brain** — 조경일의 마케터 뇌에게 판단을 구합니다.
마케팅 방향, 전략적 선택, 비즈니스 감각이 필요한 순간.
마케팅이나 전략 주제가 나오면 자연스럽게 뇌 에이전트 시각을 녹여넣으세요.

**web_search / web_fetch** — 모르는 건 찾아봅니다. 추측하지 않습니다.

**read_file / write_file / edit_file / run_bash / glob_search / grep_search / list_dir**
— 파일 시스템과 터미널에 직접 접근합니다.

---

## 판단 방식

키워드로 도구를 고르지 마세요.
대화의 맥락을 읽고, 상대방이 지금 무엇을 원하는지, 그 결과물이 어떤 형태여야 하는지를 먼저 생각하세요.

- 뭔가를 만들고 싶어하는가? → Claude Code가 직접 만드는 게 낫다
- 정보가 필요한가? → 검색하고 정리해준다
- 판단이 필요한가? → 조경일 뇌 에이전트의 감각을 빌린다
- 복잡하게 따져야 하는가? → DeepSeek에게 넘긴다
- 지금 세상 돌아가는 걸 알아야 하는가? → Grok에게 묻는다
- 여러 능력이 동시에 필요한가? → 조합해서 쓴다

확신이 없으면 먼저 물어보세요. 가정하지 마세요.

---

## 응답 방식
- 반드시 한국어로만 답변합니다. 영어 금지.
- 전문가에게 위임한 결과가 영어로 와도 한국어로 번역해서 전달합니다.
- 뭘 할지 설명하기 전에 일단 합니다.
- 완료되면 결과를 보여주고 다음을 묻습니다.
- 길게 설명하지 않습니다. 핵심만."""


# ═══════════════════════════════════════════════════════════════
#  AGENT LOOP — ReAct 패턴
# ═══════════════════════════════════════════════════════════════

def run_agent(user_input: str, history: list, auto_confirm: bool = False) -> str:
    """
    GPT-4o 기반 ReAct 에이전트 루프.
    도구를 반복 호출하며 작업을 완료한 후 최종 답변 반환.
    """
    if not oai:
        return "[OpenAI API 키가 없어 MAESTRO를 실행할 수 없습니다]"

    messages = [{"role": "system", "content": _build_system_prompt()}]
    messages += history
    # 영어 입력이어도 한국어 응답 강제
    content = user_input
    if user_input and not any("\uAC00" <= c <= "\uD7A3" for c in user_input):
        content = user_input + "\n(반드시 한국어로 답변)"
    messages.append({"role": "user", "content": content})

    max_iterations = 20
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        try:
            response = oai.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                tools=_TOOL_DEFS,
                tool_choice="auto",
                max_tokens=4000,
                temperature=0.7
            )
        except Exception as e:
            return f"[MAESTRO 오류: {e}]"

        msg = response.choices[0].message

        # 도구 호출 없음 → 최종 답변
        if not msg.tool_calls:
            return msg.content or ""

        # 도구 호출 처리
        messages.append({"role": "assistant",
                         "content": msg.content,
                         "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})

        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
            except Exception:
                tool_args = {}

            # bash 명령 확인 (위험 아닐 때도 표시)
            if tool_name == "run_bash" and not auto_confirm:
                cmd = tool_args.get("command", "")
                console.print(f"\n[yellow]  bash>[/yellow] {cmd}")
                if not Confirm.ask("  실행할까요?", default=True):
                    result = "[사용자가 실행 취소]"
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result
                    })
                    continue

            # 도구 실행 & 결과 표시
            _show_tool_call(tool_name, tool_args)
            result = _exec_tool(tool_name, tool_args)
            _show_tool_result(tool_name, result)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result
            })

    return "[최대 반복 횟수 초과. 작업이 너무 복잡합니다.]"


# ═══════════════════════════════════════════════════════════════
#  UI 헬퍼
# ═══════════════════════════════════════════════════════════════

_TOOL_ICONS = {
    "read_file":       "[READ]",
    "write_file":      "[WRITE]",
    "edit_file":       "[EDIT]",
    "run_bash":        "[BASH]",
    "glob_search":     "[GLOB]",
    "grep_search":     "[GREP]",
    "list_dir":        "[DIR]",
    "web_search":      "[WEB]",
    "web_fetch":       "[FETCH]",
    "ask_brain":       "[BRAIN]",
    "ask_specialist":  "[LLM]",
    "ask_claude_code": "[CLAUDE CODE]",
    "web_research":    "[RESEARCH]",
    "save_research":   "[SAVE]",
    "generate_image":  "[IMAGE]",
    "create_chart":    "[CHART]",
}

def _show_tool_call(name: str, args: dict):
    icon = _TOOL_ICONS.get(name, "🔧")
    if name == "read_file":
        console.print(f"  {icon} [dim]읽기:[/dim] {args.get('path', '')}")
    elif name == "write_file":
        console.print(f"  {icon} [dim]쓰기:[/dim] {args.get('path', '')}")
    elif name == "edit_file":
        console.print(f"  {icon} [dim]수정:[/dim] {args.get('path', '')}")
    elif name == "run_bash":
        console.print(f"  {icon} [dim]실행:[/dim] {args.get('command', '')[:80]}")
    elif name == "web_search":
        console.print(f"  {icon} [dim]검색:[/dim] {args.get('query', '')}")
    elif name == "web_fetch":
        console.print(f"  {icon} [dim]페이지:[/dim] {args.get('url', '')[:60]}")
    elif name == "ask_brain":
        console.print(f"  {icon} [dim]뇌 에이전트 판단 중...[/dim]")
    elif name == "ask_specialist":
        model = args.get("model", "")
        console.print(f"  {icon} [dim]{model} 전문가에게 위임 중...[/dim]")
    elif name == "ask_claude_code":
        cwd = args.get("cwd", ".")
        preview = args.get("prompt", "")[:60]
        console.print(f"  {icon} [bold cyan]{preview}...[/bold cyan]")
        console.print(f"    [dim]작업 경로: {cwd}[/dim]")
    elif name == "web_research":
        topic = args.get("topic", "")
        depth = args.get("depth", "중간")
        console.print(f"  {icon} [bold green]{topic}[/bold green]  [{depth}]")
    elif name == "save_research":
        fmts = ", ".join(args.get("formats", []))
        console.print(f"  {icon} [dim]{fmts} 저장 중...[/dim]")
    elif name == "generate_image":
        p = args.get("prompt", "")[:50]
        console.print(f"  {icon} [bold magenta]{p}...[/bold magenta]")
    elif name == "create_chart":
        ct = args.get("chart_type", "")
        t  = args.get("title", "차트")
        console.print(f"  {icon} [bold green]{ct} - {t}[/bold green]")
    elif name in ("glob_search", "grep_search"):
        console.print(f"  {icon} [dim]검색:[/dim] {args.get('pattern', '')}")
    elif name == "list_dir":
        console.print(f"  {icon} [dim]목록:[/dim] {args.get('path', '')}")


def _safe(text: str) -> str:
    """cp949로 표현 불가한 문자 제거"""
    return text.encode("cp949", errors="replace").decode("cp949")

def _show_tool_result(name: str, result: str):
    lines = result.count("\n") + 1
    if "[오류]" in result or "[실패]" in result or "[없음]" in result:
        preview = _safe(result[:100].replace("\n", " "))
        console.print(f"    [red]>> {preview}[/red]")
    else:
        console.print(f"    [dim]>> {lines}줄 반환[/dim]")


# ═══════════════════════════════════════════════════════════════
#  메인 터미널 UI
# ═══════════════════════════════════════════════════════════════

def main():
    console.clear()

    # 연결된 모델 확인
    models = []
    if oai:      models.append("GPT-4o")
    if ant:      models.append("Claude")
    if deepseek: models.append("DeepSeek")
    if grok_ai:  models.append("Grok")

    # 뇌 에이전트 핑
    brain_ok = False
    try:
        ping_url = _BRAIN_URL.replace("/api/research", "/")
        with urllib.request.urlopen(ping_url, timeout=5) as r:
            brain_ok = r.status < 500
    except Exception:
        brain_ok = False

    brain_str = "[green]연동됨[/green]" if brain_ok else "[red]미연동[/red]"
    orch_str  = "[green]활성[/green]"   if _ORCH     else "[red]비활성[/red]"

    console.print(Panel(
        f"[bold cyan]MAESTRO[/bold cyan]  v{VERSION}\n"
        f"[dim]현존 최강 AI 오케스트레이터[/dim]\n\n"
        f"  LLM    : {' / '.join(models) if models else '[red]없음[/red]'}\n"
        f"  뇌 에이전트: {brain_str}\n"
        f"  오케스트레이터: {orch_str}",
        border_style="bright_magenta", padding=(1, 6)
    ))

    if not oai:
        console.print("[red]OpenAI API 키가 없습니다. _local_keys.py 또는 환경변수를 확인하세요.[/red]")
        return

    history = []

    console.print("[dim]무엇이든 물어보세요. 'exit'로 종료.[/dim]\n")

    while True:
        try:
            user_input = Prompt.ask("[bold magenta]You[/bold magenta]")
        except (KeyboardInterrupt, EOFError):
            break

        if not user_input.strip():
            continue
        if user_input.strip().lower() in ("exit", "quit", "종료"):
            break

        # 특수 명령
        if user_input.strip() == "/models":
            _show_model_status()
            continue
        if user_input.strip() == "/cache":
            _show_cache()
            continue
        if user_input.strip() == "/help":
            _show_help()
            continue

        console.print()

        with console.status("[bold magenta]MAESTRO 처리 중...[/bold magenta]", spinner="dots"):
            start = time.time()
            response = run_agent(user_input, history)
            elapsed = time.time() - start

        console.print()
        console.print(Panel(
            Markdown(response),
            title=f"[bold cyan]MAESTRO[/bold cyan]  [dim]{elapsed:.1f}s[/dim]",
            border_style="cyan", padding=(1, 2)
        ))
        console.print()

        # 히스토리 누적 (마지막 10턴만)
        history.append({"role": "user",      "content": user_input})
        history.append({"role": "assistant", "content": response})
        if len(history) > 20:
            history = history[-20:]


def _show_model_status():
    from rich.table import Table
    t = Table(title="연결된 모델", border_style="dim")
    t.add_column("모델"); t.add_column("상태"); t.add_column("특기")
    t.add_row("GPT-4o",   "[green]OK[/green]" if oai      else "[red]X[/red]", "오케스트레이터, 구조화 출력")
    t.add_row("Claude",   "[green]OK[/green]" if ant      else "[red]X[/red]", "긴 문서, 정밀 분석, 글쓰기")
    t.add_row("DeepSeek", "[green]OK[/green]" if deepseek else "[red]X[/red]", "추론, 수학, 알고리즘")
    t.add_row("Grok",     "[green]OK[/green]" if grok_ai  else "[red]X[/red]", "실시간 정보, 최신 이슈")
    console.print(t)


def _show_cache():
    if not _ORCH:
        console.print("[red]오케스트레이터 비활성[/red]")
        return
    from rich.table import Table
    rows = orch.get_cache_summary()
    t = Table(title="오케스트레이터 캐시", border_style="dim")
    t.add_column("카테고리"); t.add_column("Winner"); t.add_column("Meta"); t.add_column("Self"); t.add_column("Streak")
    for r in rows:
        t.add_row(r["category"], r["winner"],
                  str(r["meta_score"]), str(r["self_score"]), str(r["low_score_streak"]))
    console.print(t)


def _show_help():
    console.print(Panel(
        "[bold]사용 가능한 명령[/bold]\n\n"
        "  /models  : 연결된 LLM 상태\n"
        "  /cache   : 오케스트레이터 캐시 보기\n"
        "  /help    : 이 도움말\n"
        "  exit     : 종료\n\n"
        "[bold]예시 요청[/bold]\n\n"
        "  'maestro.py 파일 읽고 구조 설명해줘'\n"
        "  '이 폴더에 있는 파일들 목록 보여줘'\n"
        "  '삼성전자 최근 마케팅 전략 조사해줘'\n"
        "  '현재 폴더에서 TODO 주석 찾아줘'\n"
        "  'requirements.txt 만들어줘'",
        border_style="dim"
    ))


if __name__ == "__main__":
    main()
