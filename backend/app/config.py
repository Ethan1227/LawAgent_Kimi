"""配置加载模块：合并示例配置与本地配置（本地配置优先）。

配置项来源：
- config/settings.example.yaml：无密钥模板，提交到仓库
- config/settings.local.yaml：本地真实密钥，已被 .gitignore 排除
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

APP_NAME = "民事诉状生成与法律咨询系统"
APP_VERSION = "0.1.0"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
EXAMPLE_CONFIG_PATH = CONFIG_DIR / "settings.example.yaml"
LOCAL_CONFIG_PATH = CONFIG_DIR / "settings.local.yaml"

# 显式常量（开发规范：超时、重试次数、分页大小必须写为常量）
DEFAULT_LLM_TIMEOUT_SECONDS = 60
DEFAULT_LLM_MAX_RETRIES = 2
DEFAULT_RETRIEVAL_TOP_K = 5
DB_CONNECT_TIMEOUT_SECONDS = 10
MAX_FOLLOW_UP_QUESTIONS = 3


@dataclass(frozen=True)
class LLMSettings:
    """单个 LLM 提供方配置。"""

    provider: str
    api_key: str
    base_url: str
    model: str
    temperature: float
    top_p: float
    max_tokens: int
    timeout_seconds: int
    max_retries: int
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LLMSettings":
        return cls(
            provider=str(data.get("provider", "")),
            api_key=str(data.get("api_key", "")),
            base_url=str(data.get("base_url", "")),
            model=str(data.get("model", "")),
            temperature=float(data.get("temperature", 0.3)),
            top_p=float(data.get("top_p", 0.8)),
            max_tokens=int(data.get("max_tokens", 2048)),
            timeout_seconds=int(data.get("timeout_seconds", DEFAULT_LLM_TIMEOUT_SECONDS)),
            max_retries=int(data.get("max_retries", DEFAULT_LLM_MAX_RETRIES)),
            enabled=bool(data.get("enabled", True)),
        )


@dataclass(frozen=True)
class RetrievalSettings:
    """检索配置。"""

    top_k: int
    knowledge_dir: Path
    index_dir: Path
    embedding_model: str


@dataclass(frozen=True)
class Settings:
    """应用全局配置。"""

    llm: LLMSettings
    fallback_llm: LLMSettings
    retrieval: RetrievalSettings
    database_path: Path
    server_host: str
    server_port: int
    cors_origins: tuple[str, ...]
    log_level: str
    log_file: Path


def _load_yaml(path: Path) -> dict[str, Any]:
    """读取 YAML 文件；文件不存在时返回空字典（允许缺少本地配置）。"""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误，顶层必须是字典: {path}")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """递归合并两个字典，override 优先。"""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_path(raw_path: str) -> Path:
    """相对路径一律相对于项目根目录解析。"""
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def load_settings(
    example_path: Path = EXAMPLE_CONFIG_PATH,
    local_path: Path | None = LOCAL_CONFIG_PATH,
) -> Settings:
    """加载配置：示例配置为底，本地配置覆盖。"""
    config = _load_yaml(example_path)
    if local_path is not None:
        config = _deep_merge(config, _load_yaml(local_path))

    retrieval = config.get("retrieval", {})
    database = config.get("database", {})
    server = config.get("server", {})
    logging_config = config.get("logging", {})

    return Settings(
        llm=LLMSettings.from_dict(config.get("llm", {})),
        fallback_llm=LLMSettings.from_dict(config.get("fallback_llm", {})),
        retrieval=RetrievalSettings(
            top_k=int(retrieval.get("top_k", DEFAULT_RETRIEVAL_TOP_K)),
            knowledge_dir=_resolve_path(str(retrieval.get("knowledge_dir", "data/legal"))),
            index_dir=_resolve_path(str(retrieval.get("index_dir", "data/index"))),
            embedding_model=str(retrieval.get("embedding_model", "BAAI/bge-small-zh-v1.5")),
        ),
        database_path=_resolve_path(str(database.get("path", "data/app.db"))),
        server_host=str(server.get("host", "0.0.0.0")),
        server_port=int(server.get("port", 8000)),
        cors_origins=tuple(str(origin) for origin in server.get("cors_origins", [])),
        log_level=str(logging_config.get("level", "INFO")),
        log_file=_resolve_path(str(logging_config.get("file", "logs/app.log"))),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取全局配置（带缓存）。"""
    return load_settings()


def reset_settings_cache() -> None:
    """清空配置缓存（测试用）。"""
    get_settings.cache_clear()
