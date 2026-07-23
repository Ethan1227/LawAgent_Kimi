"""OpenAI 兼容的大模型客户端：流式输出、超时与重试（显式失败）。"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.config import LLMSettings
from app.logging_config import get_logger

logger = get_logger(__name__)


class LLMError(Exception):
    """大模型调用失败。"""


class LLMClient:
    """单个 LLM 提供方（qwen / deepseek 等 OpenAI 兼容接口）。"""

    def __init__(self, settings: LLMSettings) -> None:
        self._settings = settings

    @property
    def name(self) -> str:
        return f"{self._settings.provider}/{self._settings.model}"

    def is_available(self) -> bool:
        return self._settings.enabled and bool(self._settings.api_key)

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:
        """流式对话，逐段产出文本；失败抛出 LLMError。"""
        if not self.is_available():
            raise LLMError(f"{self.name} 未配置 API Key，不可用")
        payload = {
            "model": self._settings.model,
            "messages": messages,
            "temperature": self._settings.temperature,
            "top_p": self._settings.top_p,
            "max_tokens": self._settings.max_tokens,
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {self._settings.api_key}"}
        last_error: Exception | None = None
        for attempt in range(1, self._settings.max_retries + 2):
            try:
                async with httpx.AsyncClient(
                    base_url=self._settings.base_url,
                    timeout=self._settings.timeout_seconds,
                ) as client:
                    async with client.stream(
                        "POST", "/chat/completions", json=payload, headers=headers
                    ) as response:
                        if response.status_code != 200:
                            body = await response.aread()
                            raise LLMError(
                                f"{self.name} 返回 HTTP {response.status_code}: {body[:200]!r}"
                            )
                        async for text in self._iter_sse(response):
                            yield text
                        return
            except (httpx.HTTPError, LLMError) as exc:
                last_error = exc
                logger.warning(
                    "LLM 调用失败（%s，第 %d 次）: %s", self.name, attempt, exc
                )
        raise LLMError(f"{self.name} 重试 {self._settings.max_retries} 次后仍失败: {last_error}")

    @staticmethod
    async def _iter_sse(response: httpx.Response) -> AsyncIterator[str]:
        """解析 SSE 数据行，产出增量文本。"""
        async for line in response.aiter_lines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                return
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                yield content
