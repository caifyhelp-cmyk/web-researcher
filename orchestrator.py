# -*- coding: utf-8 -*-
"""AI 오케스트레이터 — 동적 모델 선택 + 학습 DB (v1.1)

설계 원칙:
  - Meta LLM(DeepSeek R1)이 모델별 적합도 점수 매김
  - 각 모델이 자기평가 병렬 실행
  - 두 순위에서 겹치는 지점 → 최적 모델 선택
  - 결과는 SQLite 캐시에 저장 → 다음 호출 즉시 사용
  - 사용자 피드백으로 재평가 트리거
"""

import os, json, sqlite3, concurrent.futures, re
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_HERE, "orchestrator.db")

# 캐시 버전 — 기본값이 바뀔 때 올리면 DB 강제 업데이트
_CACHE_VERSION = 4

# 카테고리별 설명 (Meta LLM 프롬프트용)
CATEGORY_DESC = {
    "query_generation": "검색어/쿼리 생성 및 리서치 계획 수립. 주제를 분석해 효과적인 검색어 5개와 추출 항목을 생성하는 작업.",
    "url_filtering":    "URL 관련성 판단 및 필터링. 검색 결과 URL 목록에서 주제와 무관한 것을 골라내는 작업.",
    "data_extraction":  "웹페이지 본문에서 정해진 항목(업체명, 가격, 서비스 등)을 JSON으로 구조화 추출하는 작업.",
    "market_analysis":  "수집된 다수 사이트 정보를 종합해 시장 현황, 경쟁 구도, 트렌드를 분석하는 작업. 대용량 컨텍스트 처리 필요.",
    "strategy_insight": "시장 분석 결과를 바탕으로 마케팅 전략과 실행 가능한 액션 아이템을 도출하는 작업. 깊은 추론과 창의성 필요.",
    "document_writing": "분석 결과를 바탕으로 보고서/제안서를 작성하는 작업. 긴 글, 구조화, 한국어 품질 중요.",
    "quick_qa":         "짧고 간단한 정보 조회나 단순 질문에 빠르게 답하는 작업. 속도와 비용 효율 중요.",
}

# 콜드 스타트용 기본 캐시 — 첫 실행 시 DB에 시드됨
# v4: 2026-04 최신 모델 반영 (gpt-4.1, claude-opus-4-6, gemini-2.5-flash, o3, o4-mini)
_DEFAULT_CACHE = {
    "query_generation": {"winner": "deepseek",  "meta_score": 88, "self_score": 85},
    "url_filtering":    {"winner": "gpt-4.1",   "meta_score": 92, "self_score": 88},
    "data_extraction":  {"winner": "gpt-4.1",   "meta_score": 95, "self_score": 90},
    "market_analysis":  {"winner": "gemini",    "meta_score": 91, "self_score": 89},
    "strategy_insight": {"winner": "claude",    "meta_score": 96, "self_score": 94},
    "document_writing": {"winner": "claude",    "meta_score": 94, "self_score": 92},
    "quick_qa":         {"winner": "o4-mini",   "meta_score": 85, "self_score": 88},
}

ALL_MODELS = ["claude", "gpt-4.1", "gpt-4.1-mini", "deepseek", "gemini", "o3", "o4-mini"]


# ══════════════════════════════════════════════
#  DB 초기화
# ══════════════════════════════════════════════

def _get_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    """DB 테이블 생성 + 기본 캐시 시드 (버전 관리 포함)"""
    con = _get_db()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS evaluation_cache (
            category         TEXT PRIMARY KEY,
            winner           TEXT NOT NULL,
            meta_score       INTEGER DEFAULT 0,
            self_score       INTEGER DEFAULT 0,
            low_score_streak INTEGER DEFAULT 0,
            cache_version    INTEGER DEFAULT 1,
            updated_at       TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS feedback_records (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            topic          TEXT,
            research_type  TEXT,
            filter_mode    TEXT,
            queries_json   TEXT,
            needs_json     TEXT,
            url_count      INTEGER,
            useful_count   INTEGER,
            score          INTEGER,
            useful_needs   TEXT,
            bad_needs      TEXT,
            models_used    TEXT,
            comment        TEXT,
            timestamp      TEXT
        );
    """)
    # cache_version 컬럼 없는 구버전 DB 마이그레이션
    try:
        con.execute("ALTER TABLE evaluation_cache ADD COLUMN cache_version INTEGER DEFAULT 1")
        con.commit()
    except Exception:
        pass  # 이미 존재하면 무시

    cur = con.cursor()
    now = datetime.now().isoformat()
    for cat, data in _DEFAULT_CACHE.items():
        # 새 카테고리 삽입 (없을 때만)
        cur.execute("""
            INSERT OR IGNORE INTO evaluation_cache
            (category, winner, meta_score, self_score, cache_version, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (cat, data["winner"], data["meta_score"], data["self_score"],
              _CACHE_VERSION, now))
        # 버전이 낮은 기존 캐시 강제 업데이트
        cur.execute("""
            UPDATE evaluation_cache
            SET winner=?, meta_score=?, self_score=?, cache_version=?, updated_at=?
            WHERE category=? AND (cache_version IS NULL OR cache_version < ?)
        """, (data["winner"], data["meta_score"], data["self_score"],
              _CACHE_VERSION, now, cat, _CACHE_VERSION))
    con.commit()
    con.close()


# ══════════════════════════════════════════════
#  모델 선택 — 캐시 우선
# ══════════════════════════════════════════════

def get_best_model(category: str) -> str:
    """캐시에서 최적 모델 반환. 없으면 기본값."""
    try:
        con = _get_db()
        cur = con.cursor()
        cur.execute("SELECT winner FROM evaluation_cache WHERE category = ?", (category,))
        row = cur.fetchone()
        con.close()
        if row:
            return row["winner"]
    except Exception:
        pass
    return _DEFAULT_CACHE.get(category, {}).get("winner", "gpt-4o-mini")


def check_reevaluation_needed(category: str) -> bool:
    """low_score_streak >= 3이면 재평가 필요"""
    try:
        con = _get_db()
        cur = con.cursor()
        cur.execute("SELECT low_score_streak FROM evaluation_cache WHERE category = ?", (category,))
        row = cur.fetchone()
        con.close()
        return bool(row and row["low_score_streak"] >= 3)
    except Exception:
        return False


def get_cache_summary() -> list:
    """현재 캐시 상태 반환 (UI 표시용)"""
    try:
        con = _get_db()
        cur = con.cursor()
        cur.execute("SELECT category, winner, meta_score, self_score, low_score_streak, updated_at FROM evaluation_cache ORDER BY category")
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return rows
    except Exception:
        return []


# ══════════════════════════════════════════════
#  자기평가 — 새 카테고리 or 재평가 필요 시
# ══════════════════════════════════════════════

def run_self_evaluation(category: str, meta_caller, self_callers: dict) -> str:
    """
    자기평가 실행 → 최적 모델 결정 → DB 저장 → 모델명 반환.

    Args:
        category:     평가할 카테고리 키
        meta_caller:  DeepSeek 호출 fn(prompt: str) -> str
        self_callers: {model_name: fn(prompt: str) -> str}
    """
    desc = CATEGORY_DESC.get(category, category)

    # 1단계: Meta LLM (DeepSeek) 점수 매기기
    meta_prompt = (
        f"다음 AI 작업을 수행할 모델을 평가합니다.\n"
        f"작업: {desc}\n\n"
        f"claude, gpt-4o, gpt-4o-mini, deepseek 각각의 적합도를 0~100으로 평가하세요.\n"
        f"JSON만 출력: "
        '{"claude": 점수, "gpt-4o": 점수, "gpt-4o-mini": 점수, "deepseek": 점수}'
    )
    meta_scores = {}
    try:
        raw = meta_caller(meta_prompt)
        m = re.search(r'\{[^{}]+\}', raw)
        if m:
            meta_scores = json.loads(m.group())
    except Exception:
        pass

    if not meta_scores:
        meta_scores = {"claude": 85, "gpt-4o": 80, "gpt-4o-mini": 60, "deepseek": 70}

    # 2단계: 각 모델 자기평가 (병렬)
    self_prompt = (
        f"다음 작업에 대한 당신의 적합도를 0~100 숫자 하나로만 답하세요.\n"
        f"작업: {desc}"
    )
    self_scores = {}

    def _ask_self(model_name, fn):
        try:
            raw = fn(self_prompt)
            nums = re.findall(r'\d+', raw)
            score = int(nums[0]) if nums else 50
            return model_name, min(100, max(0, score))
        except Exception:
            return model_name, 50

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_ask_self, mn, fn): mn for mn, fn in self_callers.items()}
        for fut in concurrent.futures.as_completed(futs):
            mn, score = fut.result()
            self_scores[mn] = score

    # 3단계: 겹치는 지점 탐색 (위에서부터 확장)
    meta_ranking = sorted(meta_scores, key=lambda m: meta_scores.get(m, 0), reverse=True)
    self_ranking  = sorted(self_scores,  key=lambda m: self_scores.get(m, 0),  reverse=True)

    winner = None
    for expand in range(1, len(meta_ranking) + 1):
        meta_top = set(meta_ranking[:expand])
        self_top  = set(self_ranking[:expand])
        overlap   = meta_top & self_top
        if overlap:
            winner = min(overlap,
                         key=lambda m: meta_ranking.index(m) + self_ranking.index(m))
            break

    if not winner:
        # combined_score fallback
        all_models = set(meta_ranking) & set(self_ranking)
        if all_models:
            winner = min(all_models,
                         key=lambda m: meta_ranking.index(m) + self_ranking.index(m))
        else:
            winner = meta_ranking[0] if meta_ranking else "gpt-4o-mini"

    # DB 저장
    try:
        con = _get_db()
        con.execute("""
            INSERT OR REPLACE INTO evaluation_cache
            (category, winner, meta_score, self_score, low_score_streak, updated_at)
            VALUES (?, ?, ?, ?, 0, ?)
        """, (category, winner,
              int(meta_scores.get(winner, 0)),
              int(self_scores.get(winner, 0)),
              datetime.now().isoformat()))
        con.commit()
        con.close()
    except Exception:
        pass

    return winner


# ══════════════════════════════════════════════
#  피드백 수집 → DB 저장
# ══════════════════════════════════════════════

def record_feedback(topic: str, plan: dict, analysis: dict,
                    score: int, useful_needs: list, bad_needs: list,
                    models_used: dict, comment: str = ""):
    """
    사용자 피드백을 DB에 저장.
    score <= 2이면 핵심 카테고리 low_score_streak 증가 → 3회면 재평가 트리거.

    ※ 이 데이터는 오케스트레이터 학습 DB 전용.
       조경일 뇌 에이전트 방향으로 절대 흐르지 않음.
    """
    per_url = analysis.get("per_url", [])
    try:
        con = _get_db()
        con.execute("""
            INSERT INTO feedback_records
            (topic, research_type, filter_mode, queries_json, needs_json,
             url_count, useful_count, score, useful_needs, bad_needs,
             models_used, comment, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            topic,
            plan.get("research_type", ""),
            plan.get("filter_mode", ""),
            json.dumps(plan.get("queries", []), ensure_ascii=False),
            json.dumps(plan.get("needs", []), ensure_ascii=False),
            analysis.get("source_count", 0),
            len(per_url),
            score,
            json.dumps(useful_needs, ensure_ascii=False),
            json.dumps(bad_needs, ensure_ascii=False),
            json.dumps(models_used, ensure_ascii=False),
            comment,
            datetime.now().isoformat()
        ))

        # 낮은 점수 streak 증가
        if score <= 2:
            for cat in ("market_analysis", "strategy_insight", "data_extraction"):
                con.execute("""
                    UPDATE evaluation_cache
                    SET low_score_streak = low_score_streak + 1
                    WHERE category = ?
                """, (cat,))

        con.commit()
        con.close()
    except Exception:
        pass


def reset_streak(category: str):
    """재평가 후 streak 초기화"""
    try:
        con = _get_db()
        con.execute("UPDATE evaluation_cache SET low_score_streak = 0 WHERE category = ?",
                    (category,))
        con.commit()
        con.close()
    except Exception:
        pass


# ══════════════════════════════════════════════
#  주기적 재평가 트리거
# ══════════════════════════════════════════════

def should_reevaluate(category: str, days: int = 7) -> bool:
    """마지막 업데이트가 days일 이상 지났으면 True"""
    try:
        con = _get_db()
        cur = con.cursor()
        cur.execute("SELECT updated_at FROM evaluation_cache WHERE category = ?", (category,))
        row = cur.fetchone()
        con.close()
        if not row or not row["updated_at"]:
            return True
        updated = datetime.fromisoformat(row["updated_at"])
        return datetime.now() - updated > timedelta(days=days)
    except Exception:
        return False


def get_stale_categories(days: int = 7) -> list:
    """재평가가 필요한 카테고리 목록 반환"""
    return [cat for cat in CATEGORY_DESC if should_reevaluate(cat, days)]


# DB 초기화 (임포트 시 자동 실행)
init_db()
