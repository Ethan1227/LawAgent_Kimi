"""知识库索引状态仓储测试。"""
from app.repositories.kb_repo import get_content_hash, list_kb_files, upsert_kb_file


def test_upsert_and_list_kb_files(db_conn):
    """插入知识文件索引状态后应能查询。"""
    upsert_kb_file(
        db_conn,
        file_name="民法典基础条文摘录.md",
        category="民事法律基础",
        description="民法典常用条文摘录",
        content_hash="hash-v1",
        chunk_count=10,
    )
    files = list_kb_files(db_conn)
    assert len(files) == 1
    assert files[0]["file_name"] == "民法典基础条文摘录.md"
    assert files[0]["chunk_count"] == 10
    assert files[0]["indexed_at"]
    assert get_content_hash(db_conn, "民法典基础条文摘录.md") == "hash-v1"


def test_upsert_same_file_updates_instead_of_duplicating(db_conn):
    """同名文件再次 upsert 应更新而非重复插入。"""
    upsert_kb_file(
        db_conn,
        file_name="诉讼费用说明.md",
        category="诉讼费用",
        description="诉讼费用基础说明",
        content_hash="hash-v1",
        chunk_count=5,
    )
    upsert_kb_file(
        db_conn,
        file_name="诉讼费用说明.md",
        category="诉讼费用",
        description="诉讼费用基础说明",
        content_hash="hash-v2",
        chunk_count=8,
    )
    files = list_kb_files(db_conn)
    assert len(files) == 1
    assert files[0]["content_hash"] == "hash-v2"
    assert files[0]["chunk_count"] == 8


def test_get_content_hash_returns_none_for_unknown_file(db_conn):
    """未索引的文件应返回 None。"""
    assert get_content_hash(db_conn, "不存在的文件.md") is None
