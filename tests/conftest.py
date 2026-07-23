"""pytest 全局 fixture：配置隔离、临时数据库、测试客户端。"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, load_settings
from app.repositories.db import get_connection, init_db


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    """基于示例配置生成测试配置，数据库与日志指向临时目录。"""
    base = load_settings(local_path=None)
    return replace(
        base,
        database_path=tmp_path / "test.db",
        log_file=tmp_path / "logs" / "test.log",
    )


@pytest.fixture()
def db_conn(settings: Settings) -> Iterator:
    """提供已建表的临时数据库连接。"""
    init_db(settings.database_path)
    connection = get_connection(settings.database_path)
    yield connection
    connection.close()


@pytest.fixture()
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """提供隔离配置的测试客户端。"""
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
