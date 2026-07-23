"""起诉状生成与案件信息提取接口。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings
from app.logging_config import get_logger
from app.repositories.db import get_connection
from app.repositories.records_repo import save_generation
from app.services.complaint_templates import CASE_TYPES, render_complaint
from app.services.extract_service import extract_case_info

logger = get_logger(__name__)
router = APIRouter(tags=["起诉状生成"])

REVIEW_NOTICE = (
    "本起诉状由系统自动生成，仅供参考。起诉前请务必核对全部信息，"
    "建议由专业律师审核修改后再提交人民法院。"
)


class GenerateRequest(BaseModel):
    """起诉状生成请求。"""

    case_type: str
    plaintiff: dict[str, Any] = Field(default_factory=dict)
    defendant: dict[str, Any] = Field(default_factory=dict)
    claims: list[str] = Field(default_factory=list)
    facts: str = ""
    evidence: list[str] = Field(default_factory=list)
    court: str = ""
    date: str = ""

    def to_form(self) -> dict[str, Any]:
        return self.model_dump()


class ExtractRequest(BaseModel):
    """案件信息提取请求。"""

    description: str = Field(..., min_length=1)


def get_database_path() -> Path:
    """数据库路径依赖（测试中可通过 dependency_overrides 替换）。"""
    return get_settings().database_path


@router.get("/complaint/case-types", summary="支持的案件类型")
def list_case_types() -> dict:
    return {"case_types": list(CASE_TYPES)}


@router.post("/complaint/extract", summary="自然语言案件信息提取")
def extract(request: ExtractRequest) -> dict:
    try:
        return extract_case_info(request.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/complaint/generate", summary="生成民事起诉状")
def generate(
    request: GenerateRequest,
    database_path: Path = Depends(get_database_path),
) -> dict:
    form = request.to_form()
    try:
        document = render_complaint(form)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with get_connection(database_path) as connection:
        generation_id = save_generation(
            connection,
            case_type=request.case_type,
            form_data=form,
            document=document,
        )
    logger.info("生成起诉状 id=%d case_type=%s", generation_id, request.case_type)
    return {
        "generation_id": generation_id,
        "document": document,
        "review_notice": REVIEW_NOTICE,
    }
