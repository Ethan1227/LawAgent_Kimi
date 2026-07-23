"""切块器单元测试：条文切块、front matter、指引类文件切块。"""
from __future__ import annotations

import pytest

from app.rag.chunker import chunk_text, parse_front_matter

LEGAL_TEXT = """---
category: 民事法律基础
description: 测试用条文
---

# 测试法律条文

## 中华人民共和国民法典（借款合同）

第六百六十七条 借款合同是借款人向贷款人借款，到期返还借款并支付利息的合同。

第六百七十九条 自然人之间的借款合同，自贷款人提供借款时成立。

## 中华人民共和国民法典（租赁合同）

第七百零三条 租赁合同是出租人将租赁物交付承租人使用、收益，承租人支付租金的合同。
"""

GUIDE_TEXT = """---
category: 立案流程指引
description: 测试用指引
---

# 立案流程说明

## 起诉状准备

起诉状应当按照被告人数准备正本一份、副本若干份。

## 证据材料准备

起诉时应提交支持诉讼请求的基础证据复印件。
"""


def test_parse_front_matter_extracts_meta():
    meta, body = parse_front_matter(LEGAL_TEXT)
    assert meta["category"] == "民事法律基础"
    assert "第六百六十七条" in body


def test_chunk_articles_keep_article_number_and_title():
    parsed = chunk_text(LEGAL_TEXT, "测试.md")
    assert len(parsed.chunks) == 3
    first = parsed.chunks[0]
    assert first.article_no == "第六百六十七条"
    assert "借款合同" in first.doc_title
    assert first.source_file == "测试.md"
    assert "到期返还借款" in first.content


def test_chunk_display_text_contains_source_and_location():
    parsed = chunk_text(LEGAL_TEXT, "测试.md")
    display = parsed.chunks[0].display_text
    assert "测试.md" in display
    assert "第六百六十七条" in display


def test_guide_file_chunked_by_section_without_article_no():
    parsed = chunk_text(GUIDE_TEXT, "指引.md")
    assert len(parsed.chunks) == 2
    assert parsed.chunks[0].article_no == ""
    assert parsed.chunks[0].doc_title == "起诉状准备"
    assert "正本一份" in parsed.chunks[0].content


def test_empty_file_raises_explicit_error():
    with pytest.raises(ValueError, match="有效切块"):
        chunk_text("# 只有标题\n", "空.md")
