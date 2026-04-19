# -*- coding: utf-8 -*-
"""
음성 파일 → 텍스트 (OpenAI Whisper API)
지원 형식: mp3, mp4, wav, m4a, webm, ogg
파일 크기 제한: 25MB (초과 시 자동 분할)
"""
import os
from pathlib import Path


def transcribe_audio(audio_path: str) -> str:
    """
    음성 파일을 Whisper API로 전사합니다.

    Args:
        audio_path: 음성 파일 경로 (.mp3/.mp4/.wav/.m4a 등)

    Returns:
        전사된 텍스트 (str). 실패 시 오류 메시지 반환.
    """
    import openai

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return "[오류] OPENAI_API_KEY 가 설정되지 않았습니다."

    path = Path(audio_path)
    if not path.exists():
        return f"[오류] 파일을 찾을 수 없습니다: {audio_path}"

    client = openai.OpenAI(api_key=api_key)

    # 25MB 초과 시 분할 처리
    file_size_mb = path.stat().st_size / (1024 * 1024)
    if file_size_mb > 24:
        return _transcribe_chunked(client, path)

    try:
        with open(path, "rb") as f:
            result = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="ko",       # 한국어 우선; 혼합 언어면 None 으로
                response_format="text"
            )
        return str(result).strip()
    except Exception as e:
        return f"[Whisper 오류] {e}"


def _transcribe_chunked(client, path: Path, chunk_minutes: int = 10) -> str:
    """25MB 초과 파일 분할 전사 (pydub 필요)"""
    try:
        from pydub import AudioSegment
    except ImportError:
        return "[오류] 파일이 25MB를 초과합니다. `pip install pydub ffmpeg-python` 을 실행하세요."

    try:
        audio = AudioSegment.from_file(str(path))
    except Exception as e:
        return f"[오류] 오디오 로드 실패: {e}"

    chunk_ms    = chunk_minutes * 60 * 1000
    chunks      = [audio[i:i+chunk_ms] for i in range(0, len(audio), chunk_ms)]
    parts: list[str] = []
    tmp_dir = path.parent / "_whisper_tmp"
    tmp_dir.mkdir(exist_ok=True)

    for idx, chunk in enumerate(chunks):
        tmp_file = tmp_dir / f"chunk_{idx:03d}.mp3"
        chunk.export(str(tmp_file), format="mp3")
        try:
            with open(tmp_file, "rb") as f:
                result = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language="ko",
                    response_format="text"
                )
            parts.append(str(result).strip())
        except Exception as e:
            parts.append(f"[청크 {idx} 오류: {e}]")
        finally:
            tmp_file.unlink(missing_ok=True)

    # 임시 폴더 정리
    try:
        tmp_dir.rmdir()
    except Exception:
        pass

    return "\n".join(parts)
