"""知识库服务层：索引构建、语义检索、来源列表。

职责：
- 扫描 knowledge_dir 下的 .md 知识文件，按内容哈希判断是否需要重建
- 切块 -> 嵌入 -> FAISS 索引 -> 持久化，索引状态写入 kb_files 表
- 对外提供 search / list_sources / get_file_snippets
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.logging_config import get_logger
from app.rag.chunker import ArticleChunk, chunk_text
from app.rag.embedder import Embedder, HashEmbedder, SentenceTransformerEmbedder
from app.rag.vector_store import FaissVectorStore
from app.repositories import kb_repo
from app.repositories.db import get_connection

logger = get_logger(__name__)

KNOWLEDGE_FILE_SUFFIX = ".md"


@dataclass(frozen=True)
class SearchResult:
    """单条检索结果。"""

    source_file: str
    doc_title: str
    article_no: str
    content: str
    score: float

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "doc_title": self.doc_title,
            "article_no": self.article_no,
            "content": self.content,
            "score": round(self.score, 4),
        }


@dataclass(frozen=True)
class BuildReport:
    """索引构建结果。"""

    rebuilt: bool
    file_count: int
    chunk_count: int
    embedder: str


def _file_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class KnowledgeService:
    """知识库检索服务。embedder 可注入（测试用 HashEmbedder）。"""

    def __init__(
        self,
        *,
        knowledge_dir: Path,
        index_dir: Path,
        database_path: Path,
        embedding_model: str,
        embedder: Embedder | None = None,
    ) -> None:
        self._knowledge_dir = knowledge_dir
        self._index_dir = index_dir
        self._database_path = database_path
        self._embedding_model = embedding_model
        self._embedder = embedder
        self._store: FaissVectorStore | None = None

    def _get_embedder(self) -> Embedder:
        """惰性创建嵌入器：优先本地中文模型，不可用时降级哈希嵌入。"""
        if self._embedder is None:
            try:
                self._embedder = SentenceTransformerEmbedder(self._embedding_model)
                logger.info("已加载本地向量模型: %s", self._embedding_model)
            except (ImportError, RuntimeError, OSError) as exc:
                logger.warning("向量模型不可用（%s），降级为哈希嵌入离线模式", exc)
                self._embedder = HashEmbedder()
        return self._embedder

    def _read_knowledge_files(self) -> list[tuple[Path, str]]:
        if not self._knowledge_dir.exists():
            raise FileNotFoundError(f"知识库目录不存在: {self._knowledge_dir}")
        files = sorted(self._knowledge_dir.glob(f"*{KNOWLEDGE_FILE_SUFFIX}"))
        if not files:
            raise FileNotFoundError(f"知识库目录中没有 {KNOWLEDGE_FILE_SUFFIX} 文件: {self._knowledge_dir}")
        return [(path, path.read_text(encoding="utf-8")) for path in files]

    def _needs_rebuild(self, entries: list[tuple[Path, str]]) -> bool:
        """索引文件缺失或任一知识文件哈希变化时重建。"""
        if not FaissVectorStore.exists(self._index_dir):
            return True
        with get_connection(self._database_path) as connection:
            for path, text in entries:
                stored = kb_repo.get_content_hash(connection, path.name)
                if stored != _file_hash(text):
                    return True
        return False

    def build_index(self, *, force: bool = False) -> BuildReport:
        """构建/重建索引。内容未变化且索引存在时跳过。"""
        entries = self._read_knowledge_files()
        if not force and not self._needs_rebuild(entries):
            store = FaissVectorStore.load(self._index_dir)
            self._store = store
            logger.info("知识库内容未变化，直接加载已有索引（%d 块）", store.size)
            return BuildReport(
                rebuilt=False,
                file_count=len(entries),
                chunk_count=store.size,
                embedder=type(self._get_embedder()).__name__,
            )

        embedder = self._get_embedder()
        all_chunks: list[ArticleChunk] = []
        file_metas: list[tuple[str, dict, str, int]] = []
        for path, text in entries:
            parsed = chunk_text(text, path.name)
            all_chunks.extend(parsed.chunks)
            file_metas.append((path.name, parsed.meta, _file_hash(text), len(parsed.chunks)))

        vectors = embedder.embed_texts([chunk.display_text for chunk in all_chunks])
        store = FaissVectorStore(embedder.dimension)
        store.add(vectors, [self._chunk_to_meta(chunk) for chunk in all_chunks])
        store.save(self._index_dir)
        self._store = store

        with get_connection(self._database_path) as connection:
            for file_name, meta, digest, count in file_metas:
                kb_repo.upsert_kb_file(
                    connection,
                    file_name=file_name,
                    category=str(meta.get("category", "")),
                    description=str(meta.get("description", "")),
                    content_hash=digest,
                    chunk_count=count,
                )
        logger.info(
            "知识库索引构建完成：%d 个文件，%d 个切块，嵌入器 %s",
            len(entries), len(all_chunks), type(embedder).__name__,
        )
        return BuildReport(
            rebuilt=True,
            file_count=len(entries),
            chunk_count=len(all_chunks),
            embedder=type(embedder).__name__,
        )

    def _ensure_store(self) -> FaissVectorStore:
        if self._store is None:
            if not FaissVectorStore.exists(self._index_dir):
                self.build_index()
            else:
                self._store = FaissVectorStore.load(self._index_dir)
        if self._store is None:
            raise RuntimeError("知识库索引初始化失败")
        return self._store

    @staticmethod
    def _chunk_to_meta(chunk: ArticleChunk) -> dict:
        return {
            "chunk_id": chunk.chunk_id,
            "source_file": chunk.source_file,
            "doc_title": chunk.doc_title,
            "article_no": chunk.article_no,
            "content": chunk.content,
        }

    def search(self, query: str, top_k: int) -> list[SearchResult]:
        """语义检索，返回带元数据的结果列表。"""
        if not query.strip():
            raise ValueError("检索问题不能为空")
        store = self._ensure_store()
        query_vector = self._get_embedder().embed_query(query)
        hits = store.search(query_vector, top_k)
        results = [
            SearchResult(
                source_file=meta["source_file"],
                doc_title=meta["doc_title"],
                article_no=meta["article_no"],
                content=meta["content"],
                score=score,
            )
            for meta, score in hits
        ]
        logger.info("检索 query=%r top_k=%d 命中=%d", query, top_k, len(results))
        return results

    def list_sources(self) -> list[dict]:
        """知识来源列表（文件名/类别/适用说明/索引状态）。"""
        with get_connection(self._database_path) as connection:
            rows = kb_repo.list_kb_files(connection)
        return [
            {
                "file_name": row["file_name"],
                "category": row["category"],
                "description": row["description"],
                "chunk_count": row["chunk_count"],
                "indexed_at": row["indexed_at"],
                "index_status": "已索引",
            }
            for row in rows
        ]

    def get_file_snippets(self, file_name: str) -> list[dict]:
        """查看指定知识文件的条文片段。"""
        if not file_name.endswith(KNOWLEDGE_FILE_SUFFIX) or "/" in file_name or "\\" in file_name:
            raise ValueError(f"非法的知识文件名: {file_name}")
        path = self._knowledge_dir / file_name
        if not path.exists():
            raise FileNotFoundError(f"知识文件不存在: {file_name}")
        parsed = chunk_text(path.read_text(encoding="utf-8"), file_name)
        return [
            {
                "doc_title": chunk.doc_title,
                "article_no": chunk.article_no,
                "content": chunk.content,
            }
            for chunk in parsed.chunks
        ]
