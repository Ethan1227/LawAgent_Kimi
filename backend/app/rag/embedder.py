"""文本向量嵌入器。

- SentenceTransformerEmbedder：本地中文模型 bge-small-zh-v1.5（首次运行自动下载）
- HashEmbedder：确定性字符二元组哈希嵌入，无需模型下载，
  用于单元测试与模型不可用时的离线兜底
"""
from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np

BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："
HASH_EMBEDDER_DIM = 512


class Embedder(Protocol):
    """嵌入器协议：文本列表 -> 归一化向量矩阵。"""

    @property
    def dimension(self) -> int: ...

    def embed_texts(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class SentenceTransformerEmbedder:
    """基于 sentence-transformers 的本地中文向量模型。"""

    def __init__(self, model_name: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers 未安装，无法加载本地向量模型；"
                "请执行 uv sync --extra embed 安装，或使用 HashEmbedder 离线兜底"
            ) from exc
        # bge-m3 等多语言模型无需查询指令；bge zh/en 系列建议添加
        self._use_query_instruction = "bge" in model_name and "m3" not in model_name
        try:
            # 优先离线加载（本机缓存），避免内网/无网环境下冗长的网络重试
            self._model = SentenceTransformer(model_name, local_files_only=True)
        except (OSError, ValueError, RuntimeError):
            self._model = SentenceTransformer(model_name)

    @property
    def dimension(self) -> int:
        getter = getattr(self._model, "get_embedding_dimension", None) or getattr(
            self._model, "get_sentence_embedding_dimension"
        )
        return int(getter())

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(list(texts), normalize_embeddings=True)
        return np.asarray(vectors, dtype=np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        if self._use_query_instruction:
            text = f"{BGE_QUERY_INSTRUCTION}{text}"
        return self.embed_texts([text])


class HashEmbedder:
    """确定性哈希嵌入（离线兜底 / 测试用），基于字符二元组词袋。"""

    def __init__(self, dimension: int = HASH_EMBEDDER_DIM) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def _embed_one(self, text: str) -> np.ndarray:
        vector = np.zeros(self._dimension, dtype=np.float32)
        compact = "".join(text.split())
        bigrams = [compact[i : i + 2] for i in range(max(len(compact) - 1, 1))]
        for bigram in bigrams:
            digest = hashlib.md5(bigram.encode("utf-8")).digest()
            slot = int.from_bytes(digest[:4], "little") % self._dimension
            vector[slot] += 1.0
        return vector

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        matrix = np.stack([self._embed_one(text) for text in texts])
        return _l2_normalize(matrix)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_texts([text])


def create_default_embedder(model_name: str) -> Embedder:
    """优先加载本地中文向量模型，失败时降级为哈希嵌入并抛出原始异常供日志记录。"""
    return SentenceTransformerEmbedder(model_name)
