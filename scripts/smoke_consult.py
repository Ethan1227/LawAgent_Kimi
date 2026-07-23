"""真实链路冒烟测试：uv run python scripts/smoke_consult.py

验证 检索 + deepseek 兜底大模型 的完整咨询链路（不在 pytest 中运行）。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.llm.client import LLMClient  # noqa: E402
from app.logging_config import setup_logging  # noqa: E402
from app.repositories.db import init_db  # noqa: E402
from app.services.consult_service import ConsultService  # noqa: E402
from app.services.knowledge_service import KnowledgeService  # noqa: E402


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_file)
    init_db(settings.database_path)
    ks = KnowledgeService(
        knowledge_dir=settings.retrieval.knowledge_dir,
        index_dir=settings.retrieval.index_dir,
        database_path=settings.database_path,
        embedding_model=settings.retrieval.embedding_model,
    )
    clients = [LLMClient(settings.llm), LLMClient(settings.fallback_llm)]
    print("LLM 可用性:", [(c.name, c.is_available()) for c in clients])
    service = ConsultService(
        knowledge_service=ks,
        llm_clients=clients,
        database_path=settings.database_path,
        top_k=settings.retrieval.top_k,
    )
    outcome = await service.consult("民间借贷纠纷", "朋友借了我五万块钱，约定月息2分，现在不还怎么办？")
    print("=" * 60)
    print("offline:", outcome.offline)
    print("follow_ups:", outcome.follow_ups)
    print("sources:", [(s["doc_title"], s["article_no"], s["score"]) for s in outcome.sources])
    print("-" * 60)
    print(outcome.answer)


if __name__ == "__main__":
    asyncio.run(main())
