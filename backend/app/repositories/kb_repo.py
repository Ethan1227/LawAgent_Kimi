"""知识库文件索引状态的数据访问层（参数化查询）。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_kb_file(
    connection: sqlite3.Connection,
    *,
    file_name: str,
    category: str,
    description: str,
    content_hash: str,
    chunk_count: int,
) -> None:
    """按文件名插入或更新知识文件的索引状态。"""
    connection.execute(
        """
        INSERT INTO kb_files (file_name, category, description, content_hash, chunk_count, indexed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_name) DO UPDATE SET
            category = excluded.category,
            description = excluded.description,
            content_hash = excluded.content_hash,
            chunk_count = excluded.chunk_count,
            indexed_at = excluded.indexed_at
        """,
        (file_name, category, description, content_hash, chunk_count, _utc_now_iso()),
    )
    connection.commit()


def list_kb_files(connection: sqlite3.Connection) -> list[dict]:
    """返回全部知识文件的索引状态，按文件名排序。"""
    rows = connection.execute(
        """
        SELECT id, file_name, category, description, content_hash, chunk_count, indexed_at
        FROM kb_files
        ORDER BY file_name
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_content_hash(connection: sqlite3.Connection, file_name: str) -> str | None:
    """查询指定知识文件已索引的内容哈希，未索引返回 None。"""
    row = connection.execute(
        "SELECT content_hash FROM kb_files WHERE file_name = ?",
        (file_name,),
    ).fetchone()
    return row["content_hash"] if row else None
