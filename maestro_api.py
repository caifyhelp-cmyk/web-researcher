# -*- coding: utf-8 -*-
"""
MAESTRO FastAPI 서버
모바일 앱(Kivy) ↔ 마에스트로 엔진 사이의 REST API 브리지.

사용:
  python maestro_api.py              # 기본 포트 8765
  python maestro_api.py --port 9000  # 포트 지정
  python maestro_api.py --host 0.0.0.0  # 외부 접근 허용

엔드포인트:
  POST /chat          메시지 전송 → 스트리밍 응답
  GET  /status        서버/엔진 상태
  GET  /models        현재 모델 랭킹
  POST /settings      API 키 등 설정 업데이트
  GET  /history       대화 기록
  DELETE /history     대화 기록 초기화
  GET  /personalize   현재 개인화 설정
  POST /personalize   개인화 설정 변경
"""

import os, sys, json, asyncio, argparse, uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ── 마에스트로 엔진 로드 ────────────────────────────────────────────
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

app = FastAPI(
    title="MAESTRO API",
    version="2.1.0",
    description="MAESTRO 멀티-LLM 오케스트레이터 REST API"
)

# CORS - Kivy 앱은 로컬에서 호출하므로 전체 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 전역 상태 ──────────────────────────────────────────────────────
_engine = None          # maestro 모듈
_session_id = None      # 현재 대화 세션
_conversation: list = []

# ── 요청/응답 모델 ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    stream: bool = True

class SettingsRequest(BaseModel):
    openai_key:    Optional[str] = None
    anthropic_key: Optional[str] = None
    deepseek_key:  Optional[str] = None
    gemini_key:    Optional[str] = None
    grok_key:      Optional[str] = None
    vercel_token:  Optional[str] = None
    notion_token:  Optional[str] = None

class PersonalizeRequest(BaseModel):
    response_style:      Optional[str] = None   # concise/balanced/detailed
    output_format:       Optional[str] = None   # table/bullet/prose/auto
    language_formality:  Optional[str] = None   # formal/casual
    domain_expertise:    Optional[list] = None
    system_prompt_extra: Optional[str] = None


# ── 엔진 초기화 ────────────────────────────────────────────────────

def _load_engine():
    """마에스트로 엔진 지연 로드"""
    global _engine
    if _engine is not None:
        return _engine
    try:
        import maestro as _m
        _engine = _m
        return _engine
    except Exception as e:
        raise RuntimeError(f"마에스트로 엔진 로드 실패: {e}")


# ── 채팅 스트리밍 ──────────────────────────────────────────────────

async def _stream_response(message: str) -> AsyncGenerator[bytes, None]:
    """마에스트로 run_agent()를 비동기로 실행하고 결과를 SSE 스트림으로 반환"""
    engine = _load_engine()
    loop = asyncio.get_event_loop()

    # 진행 상태 이벤트
    yield _sse("status", {"type": "thinking", "text": "MAESTRO 분석 중..."})

    try:
        # run_agent는 동기 함수이므로 executor에서 실행
        result = await loop.run_in_executor(
            None,
            lambda: engine.run_agent(message, _conversation)
        )

        # 대화 기록 업데이트
        answer_text = result if isinstance(result, str) else result.get("answer", "")
        _conversation.append({"role": "user",      "content": message})
        _conversation.append({"role": "assistant",  "content": answer_text})

        # run_agent()는 str 또는 dict 반환 모두 처리
        if isinstance(result, str):
            answer = result
            model_used = ""
            tier = ""
            tools_used = []
        else:
            answer     = result.get("answer", "")
            model_used = result.get("model_used", "")
            tier       = result.get("tier", "")
            tools_used = result.get("tools_used", [])

        # 응답 데이터
        yield _sse("answer", {
            "text":       answer,
            "model_used": model_used,
            "tier":       tier,
            "tools_used": tools_used,
            "timestamp":  datetime.now().isoformat()
        })

        # 개인화 감지 결과
        if result.get("preference_changed"):
            yield _sse("personalize", {"changed": result["preference_changed"]})

    except Exception as e:
        yield _sse("error", {"text": str(e)})

    yield _sse("done", {})


def _sse(event: str, data: dict) -> bytes:
    """Server-Sent Event 포맷"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


# ── API 엔드포인트 ──────────────────────────────────────────────────

@app.get("/status")
async def status():
    """서버 상태 확인"""
    try:
        engine = _load_engine()
        keys_ok = {
            "openai":    bool(os.getenv("OPENAI_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "deepseek":  bool(os.getenv("DEEPSEEK_API_KEY")),
            "gemini":    bool(os.getenv("GEMINI_API_KEY")),
            "grok":      bool(os.getenv("GROK_API_KEY")),
        }
        return {
            "status":    "ok",
            "version":   getattr(engine, "VERSION", "unknown"),
            "keys":      keys_ok,
            "session":   _session_id,
            "history_count": len(_conversation) // 2
        }
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})


@app.post("/chat")
async def chat(req: ChatRequest):
    """메시지 전송 → 스트리밍 응답"""
    global _session_id
    if not req.session_id:
        _session_id = str(uuid.uuid4())[:8]

    if req.stream:
        return StreamingResponse(
            _stream_response(req.message),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )
    else:
        # 비스트리밍
        engine = _load_engine()
        result = engine.run_agent(req.message, _conversation)
        # run_agent()는 str 또는 dict 모두 반환 가능
        if isinstance(result, str):
            result = {"answer": result, "model_used": "", "tier": "", "tools_used": []}
        _conversation.append({"role": "user",      "content": req.message})
        _conversation.append({"role": "assistant",  "content": result.get("answer", "")})
        return result


@app.get("/models")
async def models():
    """현재 모델 랭킹 DB 반환"""
    try:
        import orchestrator as orch
        db = orch.load_model_db()
        return {"models": db, "updated_at": datetime.now().isoformat()}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/history")
async def get_history():
    """대화 기록 반환"""
    return {
        "session_id": _session_id,
        "count": len(_conversation) // 2,
        "messages": _conversation
    }


@app.delete("/history")
async def clear_history():
    """대화 기록 초기화"""
    global _conversation, _session_id
    _conversation = []
    _session_id = str(uuid.uuid4())[:8]
    return {"cleared": True, "session_id": _session_id}


@app.post("/settings")
async def update_settings(req: SettingsRequest):
    """API 키 환경변수 업데이트 (런타임만, 재시작 시 초기화)"""
    updated = []
    mapping = {
        "openai_key":    "OPENAI_API_KEY",
        "anthropic_key": "ANTHROPIC_API_KEY",
        "deepseek_key":  "DEEPSEEK_API_KEY",
        "gemini_key":    "GEMINI_API_KEY",
        "grok_key":      "GROK_API_KEY",
        "vercel_token":  "VERCEL_TOKEN",
        "notion_token":  "NOTION_TOKEN",
    }
    for field, env_key in mapping.items():
        val = getattr(req, field, None)
        if val:
            os.environ[env_key] = val
            updated.append(env_key)

    # 키 저장 (앱 데이터 폴더)
    keys_path = Path(os.path.expanduser("~")) / ".maestro" / "keys.json"
    existing = {}
    if keys_path.exists():
        try:
            existing = json.loads(keys_path.read_text())
        except Exception:
            pass
    for field, env_key in mapping.items():
        val = getattr(req, field, None)
        if val:
            existing[env_key] = val
    keys_path.write_text(json.dumps(existing, indent=2))

    return {"updated": updated}


@app.get("/personalize")
async def get_personalize():
    """현재 개인화 설정 반환"""
    try:
        import personalizer as pers
        custom = pers.load_custom()
        return custom
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/personalize")
async def update_personalize(req: PersonalizeRequest):
    """개인화 설정 변경"""
    try:
        import personalizer as pers
        custom = pers.load_custom()
        changed = []

        if req.response_style:
            custom["response_style"] = req.response_style
            changed.append(f"response_style → {req.response_style}")
        if req.output_format:
            custom["output_format"] = req.output_format
            changed.append(f"output_format → {req.output_format}")
        if req.language_formality:
            custom["language_formality"] = req.language_formality
            changed.append(f"language_formality → {req.language_formality}")
        if req.domain_expertise:
            for d in req.domain_expertise:
                if d not in custom.get("domain_expertise", []):
                    custom.setdefault("domain_expertise", []).append(d)
                    changed.append(f"domain_expertise + {d}")
        if req.system_prompt_extra:
            rule = req.system_prompt_extra
            if rule not in custom.get("system_prompt_extras", []):
                custom.setdefault("system_prompt_extras", []).append(rule)
                changed.append(f"rule: {rule[:40]}")

        pers.save_custom(custom)
        return {"changed": changed, "custom": custom}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── 시작 시 저장된 키 로드 ──────────────────────────────────────────

def _load_saved_keys():
    """앱 재시작 시 이전에 저장한 API 키 복원"""
    keys_path = Path(os.path.expanduser("~")) / ".maestro" / "keys.json"
    if not keys_path.exists():
        return
    try:
        data = json.loads(keys_path.read_text())
        for key, val in data.items():
            if val and not os.getenv(key):
                os.environ[key] = val
    except Exception:
        pass


# ── 메인 ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MAESTRO API 서버")
    parser.add_argument("--host", default="127.0.0.1", help="바인딩 호스트 (기본: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="포트 (기본: 8765)")
    parser.add_argument("--reload", action="store_true", help="개발 모드 자동 재로드")
    args = parser.parse_args()

    _load_saved_keys()
    print(f"MAESTRO API 서버 시작: http://{args.host}:{args.port}")
    uvicorn.run(
        "maestro_api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="warning"
    )
