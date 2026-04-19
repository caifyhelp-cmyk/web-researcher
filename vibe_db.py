# -*- coding: utf-8 -*-
"""
MAESTRO 바이브코딩 프로젝트 DB

- 완성된 프로젝트를 SQLite에 저장
- 유사 요청 시 기존 코드 재활용 → 토큰 절약
- 사용 횟수 기반 인기 프로젝트 정렬
"""

import sqlite3, json, re, os
from datetime import datetime
from pathlib import Path

_DB_PATH = Path(os.path.expanduser("~")) / ".maestro" / "vibe_projects.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _get_db() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = _get_db()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            request     TEXT NOT NULL,
            spec        TEXT NOT NULL,
            code        TEXT NOT NULL,
            tags        TEXT DEFAULT '[]',
            use_count   INTEGER DEFAULT 1,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS project_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER,
            change_req  TEXT,
            new_code    TEXT,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        );
    """)
    con.commit()
    con.close()


init_db()


def save_project(request: str, spec: str, code: str, tags: list = None) -> int:
    """완성 프로젝트 저장, project_id 반환"""
    con = _get_db()
    now = datetime.now().isoformat()
    cur = con.execute(
        "INSERT INTO projects (request, spec, code, tags, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (request, spec, code, json.dumps(tags or [], ensure_ascii=False), now, now)
    )
    pid = cur.lastrowid
    con.commit()
    con.close()
    return pid


def increment_use(project_id: int):
    con = _get_db()
    con.execute("UPDATE projects SET use_count=use_count+1, updated_at=? WHERE id=?",
                (datetime.now().isoformat(), project_id))
    con.commit()
    con.close()


def save_history(project_id: int, change_req: str, new_code: str):
    con = _get_db()
    con.execute(
        "INSERT INTO project_history (project_id, change_req, new_code, created_at) VALUES (?,?,?,?)",
        (project_id, change_req, new_code, datetime.now().isoformat())
    )
    con.commit()
    con.close()


def find_similar(request: str, top_k: int = 3) -> list:
    """
    키워드 기반 유사 프로젝트 검색
    반환: [{"id", "request", "spec", "code", "use_count"}, ...]
    """
    keywords = _extract_keywords(request)
    if not keywords:
        return []

    con = _get_db()
    rows = con.execute(
        "SELECT id, request, spec, code, tags, use_count FROM projects ORDER BY use_count DESC LIMIT 50"
    ).fetchall()
    con.close()

    scored = []
    for row in rows:
        text = f"{row['request']} {row['spec']} {row['tags']}".lower()
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scored.append((score, dict(row)))

    scored.sort(key=lambda x: (-x[0], -x[1]["use_count"]))
    return [item for _, item in scored[:top_k]]


def _extract_keywords(text: str) -> list:
    """핵심 키워드 추출 (불용어 제거)"""
    stopwords = {"만들어줘", "만들고", "싶어", "해줘", "하고", "있어", "이거", "그거",
                 "좀", "그냥", "아", "음", "근데", "그런데", "뭔가", "뭐", "거"}
    words = re.findall(r'[가-힣a-zA-Z0-9]+', text.lower())
    return [w for w in words if w not in stopwords and len(w) > 1]


def get_project(project_id: int) -> dict | None:
    con = _get_db()
    row = con.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def list_projects(limit: int = 10) -> list:
    con = _get_db()
    rows = con.execute(
        "SELECT id, request, use_count, created_at FROM projects ORDER BY use_count DESC LIMIT ?",
        (limit,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]
