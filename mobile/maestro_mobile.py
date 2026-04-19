# -*- coding: utf-8 -*-
"""
MAESTRO 모바일 어댑터

역할:
  - maestro.py를 Android에서 안전하게 실행
  - Rich 콘솔 출력 완전 차단 (logcat 민감정보 노출 방지)
  - 인터랙티브 확인 프롬프트 자동 처리 (auto_confirm=True)
  - 모바일에서 불가능한 도구(bash, claude-cli) 안전 처리
  - 구조화된 dict 반환

사용:
  engine = MaestroEngine()
  engine.initialize(keys_dict)       # API 키 설정 + 엔진 로드
  result = engine.chat(msg, history) # → {"answer":..., "model":..., "tier":...}
"""

import os, sys, json, logging, threading
from pathlib import Path
from typing import Optional

_log = logging.getLogger("maestro.engine")

# 모바일에서 불가능한 도구 목록 (안전 메시지로 대체)
_MOBILE_UNAVAILABLE_TOOLS = {
    "run_bash":        "모바일에서는 터미널 명령을 실행할 수 없습니다.",
    "ask_claude_code": None,  # None = Claude API 직접 폴백 사용
}


class _SilentConsole:
    """
    Rich Console 을 완전히 무음화.
    로그에 API 키·대화 내용이 기록되지 않도록 모든 출력 차단.
    """
    def __getattr__(self, name):
        return lambda *a, **kw: None

    def print(self, *a, **kw):  pass
    def rule(self,  *a, **kw):  pass
    def log(self,   *a, **kw):  pass


class _SilentConfirm:
    """Confirm.ask() → 항상 True (auto-approve)"""
    @staticmethod
    def ask(*a, **kw):
        return True


class _SilentPrompt:
    """Prompt.ask() → 빈 문자열"""
    @staticmethod
    def ask(*a, **kw):
        return ""


# ══════════════════════════════════════════════════════════════════
#  MAESTRO 모바일 엔진
# ══════════════════════════════════════════════════════════════════

class MaestroEngine:

    def __init__(self):
        self._module    = None
        self._ready     = False
        self._lock      = threading.Lock()
        self._init_err  = ""

    # ── 초기화 ────────────────────────────────────────────────────

    def initialize(self, keys: dict) -> bool:
        """
        API 키를 환경변수에 설정하고 maestro 모듈을 임포트.
        반드시 백그라운드 스레드에서 호출할 것 (임포트 시간 3~8초).

        Args:
            keys: {"OPENAI_API_KEY": "sk-...", "ANTHROPIC_API_KEY": "sk-ant-..."}
        Returns:
            True if success
        """
        with self._lock:
            try:
                # 1. 환경변수 설정 (maestro.py는 임포트 시 os.getenv 읽음)
                for k, v in keys.items():
                    if v and v.strip():
                        os.environ[k] = v.strip()

                # 2. 경로 설정: 업데이트 디렉터리 최우선, 그 다음 번들 파일
                here = Path(__file__).parent
                maestro_dir = here.parent  # web-researcher/

                # mobile_updater가 sys.path[0]에 이미 update_dir 추가해둠
                # (setup_update_path() 가 앱 시작 시 호출됨)
                # 번들 경로는 그 다음 순서로
                if str(maestro_dir) not in sys.path:
                    sys.path.append(str(maestro_dir))

                # 3. 이미 로드됐으면 기존 클라이언트 재초기화만
                if self._module is not None:
                    self._reinit_clients()
                    self._ready = True
                    return True

                # 4. 최초 임포트
                import maestro as _m

                # 5. 민감 출력 완전 차단
                _m.console = _SilentConsole()

                # Rich 관련 글로벌 패치
                try:
                    import rich.prompt as _rp
                    _rp.Confirm = _SilentConfirm
                    _rp.Prompt  = _SilentPrompt
                    _m.Confirm  = _SilentConfirm
                    _m.Prompt   = _SilentPrompt
                except Exception:
                    pass

                # 6. 모바일 불가 도구 패치
                self._patch_unavailable_tools(_m)

                self._module = _m
                self._ready  = True
                self._init_err = ""
                _log.info("MaestroEngine initialized OK")
                return True

            except Exception as e:
                self._init_err = str(e)
                _log.error("Init failed: %s", type(e).__name__)
                return False

    def _reinit_clients(self):
        """환경변수 변경 후 LLM 클라이언트 재생성"""
        m = self._module
        if m is None:
            return
        try:
            from openai    import OpenAI
            from anthropic import Anthropic

            oai_key = os.getenv("OPENAI_API_KEY", "")
            ant_key = os.getenv("ANTHROPIC_API_KEY", "")
            ds_key  = os.getenv("DEEPSEEK_API_KEY", "")
            gm_key  = os.getenv("GEMINI_API_KEY", "")
            gk_key  = os.getenv("GROK_API_KEY", "")

            m.oai       = OpenAI(api_key=oai_key) if oai_key else None
            m.ant       = Anthropic(api_key=ant_key) if ant_key else None
            m.deepseek  = OpenAI(api_key=ds_key,
                                 base_url="https://api.deepseek.com") if ds_key else None
            m.gemini_ai = OpenAI(api_key=gm_key,
                                 base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
                                 ) if gm_key else None
            m.grok_ai   = OpenAI(api_key=gk_key,
                                 base_url="https://api.x.ai/v1") if gk_key else None
        except Exception as e:
            _log.warning("Client reinit partial failure: %s", type(e).__name__)

    def _patch_unavailable_tools(self, m):
        """모바일에서 실행 불가능한 도구를 안전한 대체 함수로 교체"""
        original_dispatch = getattr(m, "_dispatch_tool", None)
        if original_dispatch is None:
            return

        def _safe_dispatch(tool_name: str, tool_args: dict) -> str:
            if tool_name in _MOBILE_UNAVAILABLE_TOOLS:
                msg = _MOBILE_UNAVAILABLE_TOOLS[tool_name]
                if msg:
                    return msg
                # None = Claude API 직접 폴백
                return self._claude_fallback(tool_args.get("prompt", ""))
            return original_dispatch(tool_name, tool_args)

        m._dispatch_tool = _safe_dispatch

    def _claude_fallback(self, prompt: str) -> str:
        """Claude Code CLI 없을 때 Claude API 직접 호출"""
        m = self._module
        if m is None or m.ant is None:
            return "[Anthropic API 키가 없습니다]"
        try:
            r = m.ant.messages.create(
                model="claude-opus-4-6",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            return r.content[0].text if r.content else ""
        except Exception as e:
            return f"[Claude 오류: {type(e).__name__}]"

    # ── 채팅 ──────────────────────────────────────────────────────

    def chat(self, message: str, history: list) -> dict:
        """
        마에스트로 에이전트 호출.

        Returns:
            {
                "answer":     str,    최종 답변
                "tier":       str,    medium / complex
                "model_used": str,    사용된 주요 모델
                "error":      str,    오류 시 설명 (없으면 "")
            }
        """
        if not self._ready or self._module is None:
            return {
                "answer": f"엔진이 초기화되지 않았습니다. 설정에서 API 키를 입력해 주세요.\n{self._init_err}",
                "tier": "", "model_used": "", "error": self._init_err
            }

        try:
            result = self._module.run_agent(
                message, history, auto_confirm=True
            )

            if isinstance(result, str):
                return {"answer": result, "tier": "auto", "model_used": "", "error": ""}
            if isinstance(result, dict):
                return {
                    "answer":     result.get("answer", ""),
                    "tier":       result.get("tier", ""),
                    "model_used": result.get("model_used", ""),
                    "error":      result.get("error", ""),
                }
            return {"answer": str(result), "tier": "", "model_used": "", "error": ""}

        except Exception as e:
            err_type = type(e).__name__
            _log.error("chat() exception: %s", err_type)  # 내용은 로그 안 함
            return {
                "answer": f"오류가 발생했습니다: {err_type}",
                "tier": "", "model_used": "", "error": err_type
            }

    # ── 상태 조회 ──────────────────────────────────────────────────

    def is_ready(self) -> bool:
        return self._ready

    def init_error(self) -> str:
        return self._init_err

    def available_keys(self) -> dict:
        """어떤 API 키가 설정됐는지 (값은 반환 안 함)"""
        keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
                "GEMINI_API_KEY", "GROK_API_KEY"]
        return {k: bool(os.getenv(k)) for k in keys}

    def model_status(self) -> dict:
        """오케스트레이터 DB의 현재 모델 랭킹"""
        try:
            import orchestrator as orch
            return orch.load_model_db()
        except Exception:
            return {}

    def clear_keys_from_env(self):
        """메모리에서 API 키 제거 (앱 백그라운드 전환 시 호출 권장)"""
        for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
                  "GEMINI_API_KEY", "GROK_API_KEY", "VERCEL_TOKEN"]:
            os.environ.pop(k, None)
        self._ready = False


# 싱글턴 인스턴스
engine = MaestroEngine()
