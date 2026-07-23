"""健康检查接口。"""
from __future__ import annotations

from fastapi import APIRouter

from app.config import APP_NAME, APP_VERSION

router = APIRouter(tags=["健康检查"])


@router.get("/health", summary="健康检查", description="返回服务运行状态")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": APP_NAME, "version": APP_VERSION}
