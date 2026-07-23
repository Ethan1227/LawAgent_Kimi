"""法律咨询服务层：检索增强 + 三级兜底（qwen -> deepseek -> 离线模板）。

输出事件流（供 SSE 接口使用）：
- sources：引用来源列表
- token：回答文本增量
- done：结束（含追问、离线标记、记录 ID）
- error：错误信息
"""
from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from app.config import MAX_FOLLOW_UP_QUESTIONS
from app.llm.client import LLMClient, LLMError
from app.llm.offline import (
    CONSULT_TYPES,
    build_insufficient_answer,
    build_offline_answer,
    get_follow_ups,
)
from app.logging_config import get_logger
from app.repositories.db import get_connection
from app.repositories.records_repo import save_consultation
from app.services.knowledge_service import KnowledgeService, SearchResult

logger = get_logger(__name__)

# 检索相关度阈值（bge-m3 余弦相似度经验值）；哈希兜底模式需注入更低阈值
DEFAULT_SCORE_THRESHOLD = 0.42
OFFLINE_TOKEN_CHUNK_SIZE = 8
FOLLOW_UP_PATTERN = re.compile(r"^追问[:：]\s*(.+)$", re.MULTILINE)

SYSTEM_PROMPT = """你是面向中国大陆小额民事纠纷的法律咨询助手。请严格遵守以下要求：
1. 优先依据提供的检索条文回答，不得编造法律条文、条号、流程或费用数字。
2. 检索内容不足以回答时，必须明确说明"现有知识库依据不足"，不得强行编造。
3. 使用简洁规范的中文，回答结构固定为：
【简要结论】
【适用条文】（引用时注明法律名称与条号）
【流程步骤】
【所需材料】
【风险提示】
【建议补充】
4. 结尾最多给出 3 个关键追问，每个追问单独一行，以"追问："开头。
5. 回答仅供参考，不作为正式法律意见。"""


@dataclass
class ConsultOutcome:
    """一次咨询的完整结果。"""

    answer: str
    sources: list[dict]
    follow_ups: list[str]
    offline: bool
    consult_id: int
    extra_events: list[tuple[str, str]] = field(default_factory=list)


def _build_user_prompt(
    question: str, consult_type: str, sources: list[SearchResult]
) -> str:
    context_lines = []
    for index, item in enumerate(sources, 1):
        location = f"{item.doc_title} {item.article_no}".strip()
        context_lines.append(f"[条文{index}] 《{item.source_file}》{location}\n{item.content}")
    context = "\n\n".join(context_lines) if context_lines else "（未检索到相关条文）"
    return (
        f"咨询类型：{consult_type}\n"
        f"用户问题：{question}\n\n"
        f"检索到的相关法律条文：\n{context}\n\n"
        f"请基于以上条文按要求结构回答。"
    )


def _parse_follow_ups(answer: str, consult_type: str) -> tuple[str, list[str]]:
    """从回答中提取"追问："行，返回（清理后的回答, 追问列表）。"""
    follow_ups = FOLLOW_UP_PATTERN.findall(answer)[:MAX_FOLLOW_UP_QUESTIONS]
    cleaned = FOLLOW_UP_PATTERN.sub("", answer).strip()
    if not follow_ups:
        follow_ups = get_follow_ups(consult_type)
    return cleaned, follow_ups


class ConsultService:
    """咨询业务编排。llm_clients 按优先级排列，依次兜底。"""

    def __init__(
        self,
        *,
        knowledge_service: KnowledgeService,
        llm_clients: list[LLMClient],
        database_path: Path,
        top_k: int,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    ) -> None:
        self._ks = knowledge_service
        self._llm_clients = llm_clients
        self._db_path = database_path
        self._top_k = top_k
        self._score_threshold = score_threshold

    @staticmethod
    def validate(consult_type: str, question: str) -> None:
        if consult_type not in CONSULT_TYPES:
            raise ValueError(
                f"不支持的咨询类型: {consult_type}（可选：{'、'.join(CONSULT_TYPES)}）"
            )
        if not question.strip():
            raise ValueError("咨询问题不能为空")

    def _retrieve(self, consult_type: str, question: str) -> tuple[list[SearchResult], bool]:
        results = self._ks.search(f"{consult_type} {question}", self._top_k)
        sufficient = any(item.score >= self._score_threshold for item in results)
        return results, sufficient

    async def stream_consult(
        self, consult_type: str, question: str, session_id: str
    ) -> AsyncIterator[tuple[str, str]]:
        """产出 SSE 事件流：(event_name, json_data)。"""
        results, sufficient = self._retrieve(consult_type, question)
        sources_payload = json.dumps(
            [item.to_dict() for item in results], ensure_ascii=False
        )
        yield "sources", sources_payload

        offline = True
        answer = ""
        if not sufficient:
            answer = build_insufficient_answer(consult_type)
            logger.info("检索相关度不足，返回依据不足回答: %r", question)
            async for chunk in self._stream_text(answer):
                yield "token", json.dumps({"text": chunk}, ensure_ascii=False)
        else:
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(question, consult_type, results)},
            ]
            produced = False
            for client in self._llm_clients:
                if not client.is_available():
                    logger.info("%s 不可用，跳过", client.name)
                    continue
                try:
                    async for chunk in client.stream_chat(messages):
                        answer += chunk
                        produced = True
                        yield "token", json.dumps({"text": chunk}, ensure_ascii=False)
                    offline = False
                    logger.info("咨询回答由 %s 生成", client.name)
                    break
                except LLMError as exc:
                    logger.warning("%s 调用失败，尝试下一兜底: %s", client.name, exc)
                    answer = ""
                    continue
            if not produced or offline:
                answer = build_offline_answer(consult_type, results, sufficient=True)
                logger.info("所有 LLM 不可用，使用离线规则模板回答")
                async for chunk in self._stream_text(answer):
                    yield "token", json.dumps({"text": chunk}, ensure_ascii=False)

        cleaned_answer, follow_ups = _parse_follow_ups(answer, consult_type)
        with get_connection(self._db_path) as connection:
            consult_id = save_consultation(
                connection,
                session_id=session_id,
                consult_type=consult_type,
                question=question,
                answer=cleaned_answer,
                sources=[item.to_dict() for item in results],
            )
        yield "done", json.dumps(
            {
                "consult_id": consult_id,
                "follow_ups": follow_ups,
                "offline": offline,
            },
            ensure_ascii=False,
        )

    @staticmethod
    async def _stream_text(text: str) -> AsyncIterator[str]:
        """将完整文本切为小段模拟流式输出。"""
        for start in range(0, len(text), OFFLINE_TOKEN_CHUNK_SIZE):
            yield text[start : start + OFFLINE_TOKEN_CHUNK_SIZE]
            await asyncio.sleep(0)

    async def consult(self, consult_type: str, question: str, session_id: str = "") -> ConsultOutcome:
        """非流式便捷入口（收集完整结果，供测试与内部调用）。"""
        self.validate(consult_type, question)
        answer_parts: list[str] = []
        sources: list[dict] = []
        follow_ups: list[str] = []
        offline = True
        consult_id = 0
        async for event, data in self.stream_consult(consult_type, question, session_id):
            payload = json.loads(data)
            if event == "sources":
                sources = payload
            elif event == "token":
                answer_parts.append(payload["text"])
            elif event == "done":
                follow_ups = payload["follow_ups"]
                offline = payload["offline"]
                consult_id = payload["consult_id"]
        answer, _ = _parse_follow_ups("".join(answer_parts), consult_type)
        return ConsultOutcome(
            answer=answer,
            sources=sources,
            follow_ups=follow_ups,
            offline=offline,
            consult_id=consult_id,
        )
