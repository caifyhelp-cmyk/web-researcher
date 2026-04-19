# -*- coding: utf-8 -*-
"""
MAESTRO services 패키지 — meeting_to_notion 파이프라인
  transcribe  : Whisper API로 음성 → 텍스트
  diarize     : GPT-4.1로 화자 분리
  analyze     : 회의 내용 분석 (안건·결정·액션 아이템)
  notion_client: Notion API로 회의록 페이지 생성
"""
from .transcribe    import transcribe_audio
from .diarize       import diarize_transcript
from .analyze       import analyze_meeting
from .notion_client import push_to_notion

__all__ = ["transcribe_audio", "diarize_transcript", "analyze_meeting", "push_to_notion"]
