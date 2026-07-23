"""知识库服务单元测试：索引构建、语义检索、来源列表、片段查看。

使用 HashEmbedder 避免下载模型，临时目录隔离索引与数据库。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.rag.embedder import HashEmbedder
from app.repositories.db import init_db
from app.services.knowledge_service import KnowledgeService

KB_FILE_A = """---
category: 民事法律基础
description: 借款合同条文
---

# 基础条文

## 中华人民共和国民法典（借款合同）

第六百六十七条 借款合同是借款人向贷款人借款，到期返还借款并支付利息的合同。

第六百七十六条 借款人未按照约定的期限返还借款的，应当按照约定或者国家有关规定支付逾期利息。
"""

KB_FILE_B = """---
category: 诉讼费用
description: 诉讼费标准
---

# 诉讼费说明

## 诉讼费用交纳办法

第十三条 财产案件根据诉讼请求的金额或者价额，按照比例分段累计交纳，不超过1万元的每件交纳50元。
"""


@pytest.fixture()
def kb_service(tmp_path: Path) -> KnowledgeService:
    knowledge_dir = tmp_path / "legal"
    knowledge_dir.mkdir()
    (knowledge_dir / "借款条文.md").write_text(KB_FILE_A, encoding="utf-8")
    (knowledge_dir / "诉讼费.md").write_text(KB_FILE_B, encoding="utf-8")
    database_path = tmp_path / "test.db"
    init_db(database_path)
    return KnowledgeService(
        knowledge_dir=knowledge_dir,
        index_dir=tmp_path / "index",
        database_path=database_path,
        embedding_model="unused-in-test",
        embedder=HashEmbedder(),
    )


def test_build_index_creates_index_and_records(kb_service: KnowledgeService):
    report = kb_service.build_index()
    assert report.rebuilt is True
    assert report.file_count == 2
    assert report.chunk_count == 3

    sources = kb_service.list_sources()
    assert len(sources) == 2
    by_name = {item["file_name"]: item for item in sources}
    assert by_name["借款条文.md"]["category"] == "民事法律基础"
    assert by_name["借款条文.md"]["index_status"] == "已索引"
    assert by_name["借款条文.md"]["chunk_count"] == 2


def test_search_returns_relevant_chunk_with_metadata(kb_service: KnowledgeService):
    kb_service.build_index()
    results = kb_service.search("借款人逾期还款利息怎么算", top_k=2)
    assert len(results) >= 1
    # 哈希嵌入为离线兜底，验证目标条文被召回且元数据完整
    article_numbers = {item.article_no for item in results}
    assert "第六百七十六条" in article_numbers
    for item in results:
        assert item.source_file
        assert item.content
        assert item.score > 0


def test_search_empty_query_raises(kb_service: KnowledgeService):
    with pytest.raises(ValueError, match="不能为空"):
        kb_service.search("   ", top_k=5)


def test_rebuild_skipped_when_content_unchanged(kb_service: KnowledgeService):
    first = kb_service.build_index()
    second = kb_service.build_index()
    assert first.rebuilt is True
    assert second.rebuilt is False
    assert second.chunk_count == first.chunk_count


def test_get_file_snippets_returns_articles(kb_service: KnowledgeService):
    snippets = kb_service.get_file_snippets("诉讼费.md")
    assert len(snippets) == 1
    assert snippets[0]["article_no"] == "第十三条"
    assert "50元" in snippets[0]["content"]


def test_get_file_snippets_rejects_illegal_name(kb_service: KnowledgeService):
    with pytest.raises(ValueError, match="非法"):
        kb_service.get_file_snippets("../secret.md")
