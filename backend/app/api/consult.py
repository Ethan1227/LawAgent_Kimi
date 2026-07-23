"""法律咨询接口（SSE 流式输出）。"""
from __future__ import annotations

import json
from functools import lru_cache
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.llm.client import LLMClient
from app.llm.offline import CONSULT_TYPES
from app.logging_config import get_logger
from app.services.consult_service import ConsultService
from app.services.knowledge_service import KnowledgeService

logger = get_logger(__name__)
router = APIRouter(tags=["法律咨询"])


class ConsultRequest(BaseModel):
    """咨询请求体。"""

    consult_type: str = Field(..., description="咨询类型")
    question: str = Field(..., min_length=1, description="咨询问题")
    session_id: str = Field(default="", description="会话 ID（可选）")


@lru_cache(maxsize=1)
def get_consult_service() -> ConsultService:
    """基于全局配置构建咨询服务单例。"""
    settings = get_settings()
    knowledge_service = KnowledgeService(
        knowledge_dir=settings.retrieval.knowledge_dir,
        index_dir=settings.retrieval.index_dir,
        database_path=settings.database_path,
        embedding_model=settings.retrieval.embedding_model,
    )
    llm_clients = [LLMClient(settings.llm), LLMClient(settings.fallback_llm)]
    return ConsultService(
        knowledge_service=knowledge_service,
        llm_clients=llm_clients,
        database_path=settings.database_path,
        top_k=settings.retrieval.top_k,
    )


@router.get("/consult/types", summary="咨询类型列表")
def list_consult_types() -> dict:
    return {"consult_types": list(CONSULT_TYPES)}


@router.post("/consult", summary="法律咨询（流式）", description="SSE 事件流：sources / token / done / error")
async def consult(
    request: ConsultRequest,
    service: ConsultService = Depends(get_consult_service),
) -> StreamingResponse:
    session_id = request.session_id or uuid4().hex

    async def event_stream():
        try:
            service.validate(request.consult_type, request.question)
            async for event, data in service.stream_consult(
                request.consult_type, request.question, session_id
            ):
                yield f"event: {event}\ndata: {data}\n\n"
        except ValueError as exc:
            yield f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"
        except Exception as exc:  # 兜底：显式汇报而非静默
            logger.exception("咨询接口异常")
            yield f"event: error\ndata: {json.dumps({'message': f'服务内部错误: {exc}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
