# -*- coding: utf-8 -*-
"""
화자 분리 — GPT-4.1 기반 텍스트 레벨 화자 추정
(pyannote.audio 없이 동작하는 경량 버전)

텍스트에서 발화 패턴·문체·맥락으로 화자를 추정합니다.
speaker_map 이 주어지면 SPEAKER_00 → 실제 이름으로 치환합니다.
"""
import os
import json
import re


def diarize_transcript(transcript: str, speaker_map: dict | None = None) -> str:
    """
    전사 텍스트에 화자 레이블을 붙입니다.

    Args:
        transcript : Whisper 전사 결과 (raw text)
        speaker_map: {"SPEAKER_00": "조경일", "SPEAKER_01": "소지민"} 형식

    Returns:
        "조경일: 안녕하세요\n소지민: 네, 안녕하세요" 형식 문자열
    """
    import openai

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return transcript  # 키 없으면 원본 반환

    # 이미 화자 레이블이 있는 경우
    if re.search(r'^(SPEAKER_\d+|[가-힣A-Za-z]{2,10})\s*:', transcript, re.MULTILINE):
        labeled = transcript
    else:
        labeled = _gpt_label_speakers(transcript, api_key)

    # speaker_map 적용
    if speaker_map:
        for code, name in speaker_map.items():
            labeled = labeled.replace(code + ":", name + ":")
            labeled = labeled.replace(code + " ", name + " ")

    return labeled


def _gpt_label_speakers(text: str, api_key: str) -> str:
    """GPT-4.1-mini 로 화자 레이블 추정 (비용 절감)"""
    import openai
    client = openai.OpenAI(api_key=api_key)

    prompt = (
        "다음 회의 전사 텍스트에 화자를 구분해 레이블을 붙여주세요.\n"
        "형식: 'SPEAKER_00: 발화내용\\nSPEAKER_01: 발화내용\\n...'\n"
        "문체·맥락·질문-답변 패턴으로 화자를 구분하세요.\n"
        "화자가 1명이면 SPEAKER_00 만 사용하세요.\n\n"
        f"[전사 텍스트]\n{text[:6000]}"
    )

    try:
        r = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
            temperature=0.2
        )
        return r.choices[0].message.content.strip()
    except Exception as e:
        return text  # 실패 시 원본 반환
