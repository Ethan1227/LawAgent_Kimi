"""FastAPI 应用入口：中间件、路由注册、启动初始化。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import consult, health
from app.config import APP_NAME, APP_VERSION, get_settings
from app.logging_config import get_logger, setup_logging
from app.repositories.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动时初始化日志与数据库。"""
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_file)
    logger = get_logger(__name__)
    init_db(settings.database_path)
    logger.info("%s v%s 启动完成，数据库：%s", APP_NAME, APP_VERSION, settings.database_path)
    yield


def create_app() -> FastAPI:
    """应用工厂，便于测试隔离。"""
    settings = get_settings()
    app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins) or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api")
    app.include_router(consult.router, prefix="/api")
    return app


app = create_app()
