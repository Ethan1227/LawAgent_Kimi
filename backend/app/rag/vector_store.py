"""FAISS 本地向量索引：构建、检索、持久化。

向量需先 L2 归一化，IndexFlatIP 内积即余弦相似度。
索引文件与切块元数据 JSON 一一对应存放。
"""
from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np

INDEX_FILE_NAME = "legal.faiss"
CHUNKS_FILE_NAME = "legal_chunks.json"


class FaissVectorStore:
    """基于 IndexFlatIP 的精确向量检索。"""

    def __init__(self, dimension: int) -> None:
        self._index = faiss.IndexFlatIP(dimension)
        self._chunks: list[dict] = []

    @property
    def size(self) -> int:
        return int(self._index.ntotal)

    def add(self, vectors: np.ndarray, chunks: list[dict]) -> None:
        """追加向量与对应元数据，二者数量必须一致。"""
        if vectors.shape[0] != len(chunks):
            raise ValueError(
                f"向量数量({vectors.shape[0]})与元数据数量({len(chunks)})不一致"
            )
        self._index.add(vectors.astype(np.float32))
        self._chunks.extend(chunks)

    def search(self, query_vector: np.ndarray, top_k: int) -> list[tuple[dict, float]]:
        """检索最相似的 top_k 个切块，返回 (元数据, 相似度) 列表。"""
        if self.size == 0:
            return []
        top_k = min(top_k, self.size)
        scores, indices = self._index.search(query_vector.astype(np.float32), top_k)
        results: list[tuple[dict, float]] = []
        for score, index in zip(scores[0], indices[0], strict=True):
            if index < 0:
                continue
            results.append((self._chunks[int(index)], float(score)))
        return results

    def save(self, index_dir: Path) -> None:
        """持久化索引与元数据。"""
        index_dir.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(index_dir / INDEX_FILE_NAME))
        with (index_dir / CHUNKS_FILE_NAME).open("w", encoding="utf-8") as file:
            json.dump(self._chunks, file, ensure_ascii=False, indent=1)

    @classmethod
    def load(cls, index_dir: Path) -> "FaissVectorStore":
        """从磁盘加载索引；文件缺失时抛出异常（显式失败）。"""
        index_path = index_dir / INDEX_FILE_NAME
        chunks_path = index_dir / CHUNKS_FILE_NAME
        if not index_path.exists() or not chunks_path.exists():
            raise FileNotFoundError(f"索引文件不存在，请先构建索引: {index_dir}")
        index = faiss.read_index(str(index_path))
        store = cls(index.d)
        store._index = index
        with chunks_path.open("r", encoding="utf-8") as file:
            store._chunks = json.load(file)
        if store.size != len(store._chunks):
            raise ValueError(
                f"索引向量数({store.size})与元数据数({len(store._chunks)})不一致，索引已损坏"
            )
        return store

    @staticmethod
    def exists(index_dir: Path) -> bool:
        return (index_dir / INDEX_FILE_NAME).exists() and (index_dir / CHUNKS_FILE_NAME).exists()
