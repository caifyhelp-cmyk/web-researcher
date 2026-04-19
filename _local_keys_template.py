# -*- coding: utf-8 -*-
"""
MAESTRO API 키 설정 파일
이 파일을 복사해서 _local_keys.py 로 저장 후 키를 입력하세요.

  Windows: copy _local_keys_template.py _local_keys.py
  Mac/Linux: cp _local_keys_template.py _local_keys.py
"""
import os

_KEYS = {
    # ── OpenAI (GPT-4.1 오케스트레이터 + o3 추론 + o4-mini 경량)
    "OPENAI_API_KEY":      "",   # https://platform.openai.com/api-keys

    # ── Anthropic Claude Opus 4.6 (전략·문서·긴 분석)
    "ANTHROPIC_API_KEY":   "",   # https://console.anthropic.com/

    # ── DeepSeek R2 (추론·알고리즘·쿼리 생성)
    "DEEPSEEK_API_KEY":    "",   # https://platform.deepseek.com/

    # ── xAI Grok-3 (실시간 정보·트렌드)
    "GROK_API_KEY":        "",   # https://console.x.ai/

    # ── Google Gemini 2.5 Flash (thinking 내장·대용량 컨텍스트·시장 분석)
    "GEMINI_API_KEY":      "",   # https://aistudio.google.com/apikey

    # ── 기타
    "GITHUB_DATA_TOKEN":   "",   # https://github.com/settings/tokens (repo 권한)
    "NAVER_CLIENT_ID":     "",   # https://developers.naver.com/ (검색 API)
    "NAVER_CLIENT_SECRET": "",
    "VERCEL_TOKEN":        "",   # https://vercel.com/account/tokens

    # ── Notion (회의록 자동 기록)
    "NOTION_TOKEN":        "",   # https://www.notion.so/my-integrations → Integration Token
    "NOTION_PARENT_ID":    "",   # 회의록을 저장할 Notion 페이지 또는 DB ID
}

for _k, _v in _KEYS.items():
    if _v:
        os.environ.setdefault(_k, _v)
