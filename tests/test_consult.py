"""法律咨询接口与服务单元测试。

覆盖任务书要求：
- 咨询接口正常返回
- 条文咨询含条文名称/条号/引用来源
- 流程咨询含明确步骤
- 依据不足时明确提示不编造
另覆盖：LLM 兜底链、记录落库、非法类型校验。
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.llm.client import LLMError
from app.rag.embedder import HashEmbedder
from app.repositories.db import get_connection, init_db
from app.repositories.records_repo import list_recent_consultations
from app.services.consult_service import ConsultService
from app.services.knowledge_service import KnowledgeService

KB_LOAN = """---
category: 民事法律基础
description: 借款合同条文
---

# 基础条文

## 中华人民共和国民法典（借款合同）

第六百八十条 禁止高利放贷，借款的利率不得违反国家有关规定。借款合同对支付利息没有约定的，视为没有利息。

第六百七十六条 借款人未按照约定的期限返还借款的，应当按照约定或者国家有关规定支付逾期利息。
"""

KB_PROCESS = """---
category: 立案流程指引
description: 立案流程
---

# 立案流程说明

## 立案方式与流程

当事人可以选择到受诉人民法院诉讼服务中心现场立案，也可以通过人民法院在线服务平台进行网上立案。

## 诉讼费交纳

立案后原告会收到交纳诉讼费用通知，应当自接到通知次日起七日内交纳案件受理费。
"""

# 哈希嵌入得分整体偏低，测试阈值相应调低；完全不相关查询得分为 0
TEST_SCORE_THRESHOLD = 0.01


@pytest.fixture()
def knowledge_service(tmp_path: Path) -> KnowledgeService:
    knowledge_dir = tmp_path / "legal"
    knowledge_dir.mkdir()
    (knowledge_dir / "借款条文.md").write_text(KB_LOAN, encoding="utf-8")
    (knowledge_dir / "立案流程.md").write_text(KB_PROCESS, encoding="utf-8")
    database_path = tmp_path / "test.db"
    init_db(database_path)
    service = KnowledgeService(
        knowledge_dir=knowledge_dir,
        index_dir=tmp_path / "index",
        database_path=database_path,
        embedding_model="unused-in-test",
        embedder=HashEmbedder(),
    )
    service.build_index()
    return service


@pytest.fixture()
def consult_service(knowledge_service: KnowledgeService, tmp_path: Path) -> ConsultService:
    return ConsultService(
        knowledge_service=knowledge_service,
        llm_clients=[],
        database_path=tmp_path / "test.db",
        top_k=3,
        score_threshold=TEST_SCORE_THRESHOLD,
    )


class _FakeLLMClient:
    """可控的假 LLM 客户端。"""

    def __init__(self, tokens: list[str] | None = None, *, should_fail: bool = False) -> None:
        self._tokens = tokens or []
        self._should_fail = should_fail

    @property
    def name(self) -> str:
        return "fake/test-model"

    def is_available(self) -> bool:
        return True

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:
        if self._should_fail:
            raise LLMError("模拟调用失败")
        for token in self._tokens:
            yield token


@pytest.mark.anyio
async def test_offline_consult_returns_structured_answer(consult_service: ConsultService):
    outcome = await consult_service.consult("民间借贷纠纷", "朋友借钱不还怎么办")
    assert outcome.offline is True
    assert "离线演示结果" in outcome.answer
    assert "【简要结论】" in outcome.answer
    assert "【适用条文】" in outcome.answer
    assert "【风险提示】" in outcome.answer
    assert 1 <= len(outcome.follow_ups) <= 3


@pytest.mark.anyio
async def test_article_consult_cites_article_number_and_source(consult_service: ConsultService):
    outcome = await consult_service.consult("民间借贷纠纷", "借款利息上限是怎么规定的")
    assert len(outcome.sources) >= 1
    source = outcome.sources[0]
    assert source["source_file"]
    assert source["article_no"]
    # 回答中引用条文名称与条号
    assert "条" in outcome.answer
    assert "借款条文.md" in outcome.answer or "民法典" in outcome.answer


@pytest.mark.anyio
async def test_process_consult_contains_clear_steps(consult_service: ConsultService):
    outcome = await consult_service.consult("起诉流程咨询", "想起诉应该怎么立案")
    assert "【流程步骤】" in outcome.answer
    assert "1." in outcome.answer and "2." in outcome.answer
    assert "立案" in outcome.answer


@pytest.mark.anyio
async def test_insufficient_evidence_no_fabrication(tmp_path: Path):
    """检索得分全部低于阈值时，必须明确提示依据不足、不编造。"""
    from app.services.knowledge_service import SearchResult

    class _StubKnowledgeService:
        """固定返回低分结果的桩检索服务（哈希嵌入有碰撞，不便直接用）。"""

        def search(self, query: str, top_k: int) -> list[SearchResult]:
            return [
                SearchResult(
                    source_file="借款条文.md",
                    doc_title="中华人民共和国民法典（借款合同）",
                    article_no="第六百七十六条",
                    content="借款人未按照约定的期限返还借款的……",
                    score=0.0,
                )
            ]

    init_db(tmp_path / "test.db")
    service = ConsultService(
        knowledge_service=_StubKnowledgeService(),  # type: ignore[arg-type]
        llm_clients=[],
        database_path=tmp_path / "test.db",
        top_k=3,
        score_threshold=TEST_SCORE_THRESHOLD,
    )
    outcome = await service.consult("其他民事问题", "如何挖比特币需要什么设备")
    assert "依据不足" in outcome.answer
    assert "不会编造" in outcome.answer


@pytest.mark.anyio
async def test_llm_fallback_chain_success(
    knowledge_service: KnowledgeService, tmp_path: Path
):
    service = ConsultService(
        knowledge_service=knowledge_service,
        llm_clients=[
            _FakeLLMClient(should_fail=True),
            _FakeLLMClient(["【简要结论】可以起诉要求还款。\n追问：借款金额是多少？"]),
        ],
        database_path=tmp_path / "test.db",
        top_k=3,
        score_threshold=TEST_SCORE_THRESHOLD,
    )
    outcome = await service.consult("民间借贷纠纷", "朋友借钱不还怎么办")
    assert outcome.offline is False
    assert "可以起诉要求还款" in outcome.answer
    assert "追问" not in outcome.answer
    assert outcome.follow_ups == ["借款金额是多少？"]


@pytest.mark.anyio
async def test_llm_all_failed_uses_offline_template(
    knowledge_service: KnowledgeService, tmp_path: Path
):
    service = ConsultService(
        knowledge_service=knowledge_service,
        llm_clients=[_FakeLLMClient(should_fail=True)],
        database_path=tmp_path / "test.db",
        top_k=3,
        score_threshold=TEST_SCORE_THRESHOLD,
    )
    outcome = await service.consult("民间借贷纠纷", "朋友借钱不还怎么办")
    assert outcome.offline is True
    assert "离线演示结果" in outcome.answer


@pytest.mark.anyio
async def test_consult_record_saved(consult_service: ConsultService, tmp_path: Path):
    outcome = await consult_service.consult("民间借贷纠纷", "朋友借钱不还怎么办", "session-1")
    with get_connection(tmp_path / "test.db") as connection:
        records = list_recent_consultations(connection)
    assert len(records) == 1
    assert records[0]["id"] == outcome.consult_id
    assert records[0]["question"] == "朋友借钱不还怎么办"
    assert records[0]["session_id"] == "session-1"


def test_invalid_consult_type_raises(consult_service: ConsultService):
    with pytest.raises(ValueError, match="不支持的咨询类型"):
        consult_service.validate("刑事辩护", "问题")
    with pytest.raises(ValueError, match="不能为空"):
        consult_service.validate("民间借贷纠纷", "  ")


def test_consult_endpoint_streams_sse(
    consult_service: ConsultService, settings, monkeypatch: pytest.MonkeyPatch
):
    """API 层：SSE 事件流包含 sources/token/done。"""
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    from app.api.consult import get_consult_service
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_consult_service] = lambda: consult_service

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/api/consult",
            json={"consult_type": "民间借贷纠纷", "question": "朋友借钱不还怎么办"},
        ) as response:
            assert response.status_code == 200
            events: dict[str, list[str]] = {}
            current_event = ""
            for line in response.iter_lines():
                if line.startswith("event: "):
                    current_event = line[len("event: "):]
                    events.setdefault(current_event, [])
                elif line.startswith("data: ") and current_event:
                    events[current_event].append(line[len("data: "):])

    assert "sources" in events
    assert "token" in events
    assert "done" in events
    sources = json.loads(events["sources"][0])
    assert isinstance(sources, list)
    done = json.loads(events["done"][0])
    assert done["offline"] is True
    assert 1 <= len(done["follow_ups"]) <= 3
    full_answer = "".join(json.loads(item)["text"] for item in events["token"])
    assert "离线演示结果" in full_answer


def test_consult_types_endpoint(client: TestClient):
    response = client.get("/api/consult/types")
    assert response.status_code == 200
    types = response.json()["consult_types"]
    assert len(types) == 6
    assert "民间借贷纠纷" in types
