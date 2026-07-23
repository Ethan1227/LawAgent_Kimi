"""法律知识文本切块器：按"条"切分，保留来源文件/标题/条文号元数据。

文件格式约定：
- 可选 YAML front matter（--- 包围），含 category/description
- # 一级标题为文档名，## 二级标题为法律/章节名称
- 条文以"第X条"开头，连续段落归属于最近一条
- 无"第X条"的指引类文件，按 ## 章节切块（条文号为空）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

FRONT_MATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
ARTICLE_START_PATTERN = re.compile(r"^(第[0-9零一二三四五六七八九十百千]+条)\s*(.*)")
HEADING_PATTERN = re.compile(r"^(#{1,3})\s+(.*)$")
MAX_GUIDE_CHUNK_CHARS = 600


@dataclass(frozen=True)
class ArticleChunk:
    """一个知识切块，携带元数据。"""

    chunk_id: str
    source_file: str
    doc_title: str
    article_no: str
    content: str

    @property
    def display_text(self) -> str:
        """用于嵌入与展示的完整文本（含来源标注）。"""
        location = f"{self.doc_title} {self.article_no}".strip()
        return f"【{self.source_file}｜{location}】\n{self.content}"


@dataclass(frozen=True)
class ParsedDocument:
    """解析后的知识文件。"""

    meta: dict = field(default_factory=dict)
    chunks: list[ArticleChunk] = field(default_factory=list)


def parse_front_matter(text: str) -> tuple[dict, str]:
    """分离 front matter 与正文；无 front matter 时返回空字典。"""
    match = FRONT_MATTER_PATTERN.match(text)
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("front matter 必须是键值对格式")
    return meta, text[match.end():]


def _flush_chunk(
    chunks: list[ArticleChunk],
    source_file: str,
    doc_title: str,
    article_no: str,
    buffer: list[str],
) -> None:
    content = "\n".join(line for line in buffer if line.strip()).strip()
    if not content:
        buffer.clear()
        return
    chunk_id = f"{source_file}#{len(chunks)}"
    chunks.append(
        ArticleChunk(
            chunk_id=chunk_id,
            source_file=source_file,
            doc_title=doc_title,
            article_no=article_no,
            content=content,
        )
    )
    buffer.clear()


def chunk_text(text: str, source_file: str) -> ParsedDocument:
    """将知识文件文本解析为带元数据的切块列表。"""
    meta, body = parse_front_matter(text)
    chunks: list[ArticleChunk] = []
    buffer: list[str] = []
    current_title = ""
    current_article = ""

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = HEADING_PATTERN.match(line)
        if heading:
            _flush_chunk(chunks, source_file, current_title, current_article, buffer)
            current_article = ""
            level, title = heading.group(1), heading.group(2).strip()
            if level in ("#", "##"):
                current_title = title
            continue
        article = ARTICLE_START_PATTERN.match(line)
        if article:
            _flush_chunk(chunks, source_file, current_title, current_article, buffer)
            current_article = article.group(1)
            remainder = article.group(2).strip()
            buffer = [remainder] if remainder else []
            continue
        buffer.append(line)
        # 指引类内容按长度兜底切分，避免单块过长
        if not current_article and sum(len(item) for item in buffer) >= MAX_GUIDE_CHUNK_CHARS:
            _flush_chunk(chunks, source_file, current_title, current_article, buffer)

    _flush_chunk(chunks, source_file, current_title, current_article, buffer)
    if not chunks:
        raise ValueError(f"知识文件未解析出任何有效切块: {source_file}")
    return ParsedDocument(meta=meta, chunks=chunks)
