# -*- coding: utf-8 -*-
"""
MAESTRO API 키 설정 파일
이 파일을 복사해서 _local_keys.py 로 저장 후 키를 입력하세요.

  Windows: copy _local_keys_template.py _local_keys.py
  Mac/Linux: cp _local_keys_template.py _local_keys.py
"""
import os

_KEYS = {
    "OPENAI_API_KEY":      "",   # https://platform.openai.com/api-keys
    "ANTHROPIC_API_KEY":   "",   # https://console.anthropic.com/
    "DEEPSEEK_API_KEY":    "",   # https://platform.deepseek.com/
    "GROK_API_KEY":        "",   # https://console.x.ai/
    "GITHUB_DATA_TOKEN":   "",   # https://github.com/settings/tokens (repo 권한)
    "NAVER_CLIENT_ID":     "",   # https://developers.naver.com/ (검색 API)
    "NAVER_CLIENT_SECRET": "",
    "VERCEL_TOKEN":        "",   # https://vercel.com/account/tokens
}

for _k, _v in _KEYS.items():
    if _v:
        os.environ.setdefault(_k, _v)
