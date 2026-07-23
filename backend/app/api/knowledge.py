"""法律依据（知识库来源）接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.consult import get_knowledge_service
from app.services.knowledge_service import KnowledgeService

router = APIRouter(tags=["法律依据"])


@router.get("/knowledge/sources", summary="知识来源列表")
def list_sources(service: KnowledgeService = Depends(get_knowledge_service)) -> dict:
    """返回知识文件列表：文件名/类别/适用说明/索引状态。"""
    return {"sources": service.list_sources()}


@router.get("/knowledge/sources/{file_name}", summary="查看知识文件条文片段")
def get_snippets(
    file_name: str,
    service: KnowledgeService = Depends(get_knowledge_service),
) -> dict:
    try:
        return {"file_name": file_name, "snippets": service.get_file_snippets(file_name)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
