"""手动构建/验证知识库索引脚本：uv run python scripts/build_index.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.logging_config import setup_logging  # noqa: E402
from app.repositories.db import init_db  # noqa: E402
from app.services.knowledge_service import KnowledgeService  # noqa: E402


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_file)
    init_db(settings.database_path)
    service = KnowledgeService(
        knowledge_dir=settings.retrieval.knowledge_dir,
        index_dir=settings.retrieval.index_dir,
        database_path=settings.database_path,
        embedding_model=settings.retrieval.embedding_model,
    )
    report = service.build_index(force="--force" in sys.argv)
    print(f"构建结果: rebuilt={report.rebuilt} files={report.file_count} "
          f"chunks={report.chunk_count} embedder={report.embedder}")
    for item in service.search("借款利息上限是多少", settings.retrieval.top_k):
        print(f"  [{item.score:.3f}] {item.doc_title} {item.article_no} ({item.source_file})")


if __name__ == "__main__":
    main()
