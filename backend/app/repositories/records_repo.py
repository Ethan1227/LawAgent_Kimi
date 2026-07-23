"""咨询记录与生成记录的数据访问层（全部参数化查询）。"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

RECENT_CONSULTATIONS_LIMIT = 20  # 最近咨询记录默认返回条数


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_consultation(
    connection: sqlite3.Connection,
    *,
    session_id: str,
    consult_type: str,
    question: str,
    answer: str,
    sources: list[dict],
) -> int:
    """保存一条咨询记录，返回记录 ID。"""
    cursor = connection.execute(
        """
        INSERT INTO consultations (session_id, consult_type, question, answer, sources, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            consult_type,
            question,
            answer,
            json.dumps(sources, ensure_ascii=False),
            _utc_now_iso(),
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def list_recent_consultations(
    connection: sqlite3.Connection,
    limit: int = RECENT_CONSULTATIONS_LIMIT,
) -> list[dict]:
    """按时间倒序返回最近咨询记录。"""
    rows = connection.execute(
        """
        SELECT id, session_id, consult_type, question, answer, sources, created_at
        FROM consultations
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "session_id": row["session_id"],
            "consult_type": row["consult_type"],
            "question": row["question"],
            "answer": row["answer"],
            "sources": json.loads(row["sources"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def save_generation(
    connection: sqlite3.Connection,
    *,
    case_type: str,
    form_data: dict,
    document: str,
) -> int:
    """保存一条起诉状生成记录，返回记录 ID。"""
    cursor = connection.execute(
        """
        INSERT INTO generations (case_type, form_data, document, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (case_type, json.dumps(form_data, ensure_ascii=False), document, _utc_now_iso()),
    )
    connection.commit()
    return int(cursor.lastrowid)
