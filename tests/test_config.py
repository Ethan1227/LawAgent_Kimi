"""配置加载模块测试。"""
from pathlib import Path

import yaml

from app.config import (
    DEFAULT_LLM_MAX_RETRIES,
    DEFAULT_LLM_TIMEOUT_SECONDS,
    DEFAULT_RETRIEVAL_TOP_K,
    load_settings,
)


def test_load_example_config_defaults():
    """示例配置应包含任务要求的默认值。"""
    settings = load_settings(local_path=None)
    assert settings.llm.provider == "qwen"
    assert settings.llm.model == "qwen-max"
    assert settings.llm.api_key == ""
    assert settings.llm.timeout_seconds == DEFAULT_LLM_TIMEOUT_SECONDS
    assert settings.llm.max_retries == DEFAULT_LLM_MAX_RETRIES
    assert settings.retrieval.top_k == DEFAULT_RETRIEVAL_TOP_K
    assert settings.fallback_llm.provider == "deepseek"
    assert settings.fallback_llm.enabled is True


def test_local_config_overrides_example(tmp_path: Path):
    """本地配置应覆盖示例配置的同名项。"""
    local_config = tmp_path / "settings.local.yaml"
    local_config.write_text(
        yaml.safe_dump({"llm": {"api_key": "test-key", "model": "qwen-plus"}}),
        encoding="utf-8",
    )
    settings = load_settings(local_path=local_config)
    assert settings.llm.api_key == "test-key"
    assert settings.llm.model == "qwen-plus"
    # 未覆盖字段保持示例配置
    assert settings.fallback_llm.provider == "deepseek"
    assert settings.retrieval.top_k == DEFAULT_RETRIEVAL_TOP_K


def test_missing_local_config_is_allowed(tmp_path: Path):
    """缺少本地配置时不应报错，回退到示例配置。"""
    settings = load_settings(local_path=tmp_path / "not-exist.yaml")
    assert settings.llm.model == "qwen-max"


def test_relative_paths_resolve_to_project_root():
    """相对路径应解析为项目根目录下的绝对路径。"""
    settings = load_settings(local_path=None)
    assert settings.retrieval.knowledge_dir.is_absolute()
    assert settings.retrieval.knowledge_dir.name == "legal"
    assert settings.database_path.is_absolute()
