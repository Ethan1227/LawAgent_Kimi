"""SQLite 连接管理与建表。

规范：所有 SQL 必须使用参数化查询，严禁拼接用户输入。
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from app.config import DB_CONNECT_TIMEOUT_SECONDS

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS consultations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL DEFAULT '',
    consult_type TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL DEFAULT '',
    sources TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_type TEXT NOT NULL,
    form_data TEXT NOT NULL,
    document TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kb_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    chunk_count INTEGER NOT NULL DEFAULT 0,
    indexed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_consultations_created_at ON consultations(created_at);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """获取数据库连接，调用方负责关闭（推荐配合 closing 使用）。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), timeout=DB_CONNECT_TIMEOUT_SECONDS)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: Path) -> None:
    """初始化数据库表结构（幂等）。"""
    with closing(get_connection(db_path)) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.commit()
