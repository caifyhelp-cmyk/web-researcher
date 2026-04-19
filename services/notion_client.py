# -*- coding: utf-8 -*-
"""
Notion API — 회의록 페이지 생성

필요 환경변수:
  NOTION_TOKEN      : Notion Integration Token (secret_xxxx)
  NOTION_PARENT_ID  : 회의록을 저장할 Notion 페이지/데이터베이스 ID

페이지 구조:
  제목 → 날짜/참석자 → 안건 → 결정사항 → 액션 아이템 → 요약 → 원문
"""
import os
import json


def push_to_notion(analysis: dict, labeled_transcript: str = "") -> str:
    """
    분석 결과를 Notion 페이지로 업로드합니다.

    Args:
        analysis          : analyze_meeting() 반환 딕셔너리
        labeled_transcript: 원문 전사록 (선택)

    Returns:
        성공 시 "✅ Notion 페이지 생성: <URL>" 또는 오류 메시지
    """
    token     = os.environ.get("NOTION_TOKEN", "")
    parent_id = os.environ.get("NOTION_PARENT_ID", "")

    if not token:
        return "[오류] NOTION_TOKEN 환경변수가 없습니다."
    if not parent_id:
        return "[오류] NOTION_PARENT_ID 환경변수가 없습니다."

    blocks = _build_blocks(analysis, labeled_transcript)
    title  = analysis.get("title", "회의록")
    date_  = analysis.get("date", "")

    # Notion API — 페이지 생성
    import urllib.request
    headers = {
        "Authorization":  f"Bearer {token}",
        "Content-Type":   "application/json",
        "Notion-Version": "2022-06-28",
    }

    # 부모가 데이터베이스인지 페이지인지 자동 판별
    parent = _resolve_parent(parent_id, token)
    payload = {
        "parent": parent,
        "properties": _build_properties(title, date_, parent),
        "children": blocks[:100],   # Notion 한 번에 최대 100 블록
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req  = urllib.request.Request(
        "https://api.notion.com/v1/pages",
        data=body,
        headers=headers,
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        page_url = data.get("url", "")
        return f"✅ Notion 페이지 생성 완료: {page_url}"
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return f"[Notion API 오류 {e.code}] {err_body[:300]}"
    except Exception as e:
        return f"[Notion 오류] {e}"


# ─────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────

def _resolve_parent(parent_id: str, token: str) -> dict:
    """parent_id 가 DB 인지 Page 인지 Notion API 로 확인"""
    import urllib.request
    headers = {
        "Authorization":  f"Bearer {token}",
        "Notion-Version": "2022-06-28",
    }
    # DB 조회 시도
    try:
        req = urllib.request.Request(
            f"https://api.notion.com/v1/databases/{parent_id}",
            headers=headers
        )
        with urllib.request.urlopen(req, timeout=10):
            return {"database_id": parent_id}
    except Exception:
        return {"page_id": parent_id}


def _build_properties(title: str, date_: str, parent: dict) -> dict:
    """부모가 DB 면 Name+Date 속성, 페이지면 title만"""
    if "database_id" in parent:
        props = {
            "Name": {"title": [{"text": {"content": title}}]},
        }
        if date_:
            props["Date"] = {"date": {"start": date_}}
        return props
    return {"title": [{"text": {"content": title}}]}


def _build_blocks(analysis: dict, transcript: str) -> list:
    blocks = []

    def _heading(text: str, level: int = 2) -> dict:
        return {"object": "block",
                "type": f"heading_{level}",
                f"heading_{level}": {"rich_text": [{"text": {"content": text}}]}}

    def _bullet(text: str) -> dict:
        return {"object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"text": {"content": text[:2000]}}]}}

    def _para(text: str) -> dict:
        return {"object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"text": {"content": text[:2000]}}]}}

    def _divider() -> dict:
        return {"object": "block", "type": "divider", "divider": {}}

    # 참석자
    attendees = analysis.get("attendees", [])
    if attendees:
        blocks.append(_heading("👥 참석자"))
        blocks.append(_para(", ".join(attendees)))

    # 안건
    agenda = analysis.get("agenda", [])
    if agenda:
        blocks.append(_heading("📋 주요 안건"))
        for item in agenda:
            blocks.append(_bullet(item))

    # 결정사항
    decisions = analysis.get("decisions", [])
    if decisions:
        blocks.append(_heading("✅ 결정 사항"))
        for item in decisions:
            blocks.append(_bullet(item))

    # 액션 아이템
    actions = analysis.get("action_items", [])
    if actions:
        blocks.append(_heading("🎯 액션 아이템"))
        for a in actions:
            task  = a.get("task", "")
            owner = a.get("owner", "")
            due   = a.get("due", "")
            label = task
            if owner: label += f" — {owner}"
            if due:   label += f" (기한: {due})"
            blocks.append(_bullet(label))

    # 다음 회의
    next_mtg = analysis.get("next_meeting", "")
    if next_mtg:
        blocks.append(_heading("📅 다음 회의"))
        blocks.append(_para(next_mtg))

    # 요약
    summary = analysis.get("summary", "")
    if summary:
        blocks.append(_divider())
        blocks.append(_heading("🗒 회의 요약"))
        blocks.append(_para(summary))

    # 원문 (접어두기)
    if transcript:
        blocks.append(_divider())
        blocks.append(_heading("📝 전사 원문", level=3))
        # 2000자씩 분할 (Notion 블록 한도)
        for i in range(0, min(len(transcript), 20000), 2000):
            blocks.append(_para(transcript[i:i+2000]))

    return blocks
