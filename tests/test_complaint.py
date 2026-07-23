"""起诉状生成与信息提取单元测试。

覆盖任务书要求：
- 起诉状缺必填字段返回明确错误
- 未知信息标【待补充】
- 三类案件正常生成
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.repositories.db import get_connection
from app.services.complaint_templates import render_complaint
from app.services.extract_service import extract_case_info


def _base_form(case_type: str = "民间借贷纠纷") -> dict:
    return {
        "case_type": case_type,
        "plaintiff": {
            "name": "李四",
            "gender": "男",
            "id_number": "110101199001011234",
            "address": "北京市东城区某小区1号楼",
            "phone": "13800001111",
        },
        "defendant": {
            "name": "张三",
            "gender": "",
            "id_number": "",
            "address": "北京市西城区某街道2号",
            "phone": "",
        },
        "claims": [
            "请求判令被告偿还借款本金人民币50000元",
            "请求判令被告支付逾期利息（按一年期贷款市场报价利率计算）",
            "请求判令被告承担本案诉讼费用",
        ],
        "facts": "2023年5月1日，被告因资金周转向原告借款50000元，约定2023年12月31日前归还。到期后原告多次催要，被告至今未还。",
        "evidence": ["借条一张", "银行转账记录", "微信催款聊天记录"],
        "court": "北京市西城区人民法院",
        "date": "2026年7月23日",
    }


def test_render_complaint_contains_standard_structure():
    document = render_complaint(_base_form())
    assert "民事起诉状" in document
    assert "原告：李四" in document
    assert "被告：张三" in document
    assert "诉讼请求" in document
    assert "事实与理由" in document
    assert "证据和证据来源" in document
    assert "此致\n北京市西城区人民法院" in document
    assert "起诉人（签名）：李四" in document


@pytest.mark.parametrize("case_type", ["民间借贷纠纷", "房屋租赁合同纠纷", "买卖合同纠纷"])
def test_three_case_types_generate(case_type: str):
    form = _base_form(case_type)
    document = render_complaint(form)
    assert f"案由：{case_type}" in document
    assert "民事起诉状" in document


def test_missing_required_fields_raise_explicit_error():
    form = _base_form()
    form["defendant"] = {"name": ""}
    form["claims"] = []
    form["court"] = ""
    with pytest.raises(ValueError, match="缺少必填字段") as exc_info:
        render_complaint(form)
    message = str(exc_info.value)
    assert "被告姓名" in message
    assert "诉讼请求" in message
    assert "拟提交法院" in message


def test_unknown_optional_info_marked_placeholder():
    document = render_complaint(_base_form())
    # 被告性别/身份证号/电话未知
    assert document.count("【待补充】") >= 3


def test_invalid_case_type_rejected():
    form = _base_form("刑事纠纷")
    with pytest.raises(ValueError, match="案件类型"):
        render_complaint(form)


def test_extract_case_info_from_natural_language():
    result = extract_case_info(
        "2023年5月1日我借给被告张三5万元，约定月息2分，有借条和转账记录，他一直不还，要求他还钱。"
    )
    form = result["form"]
    assert form["case_type"] == "民间借贷纠纷"
    assert form["defendant"]["name"] == "张三"
    assert "借条" in form["evidence"]
    assert "转账记录" in form["evidence"]
    assert "5万元" in result["extracted"]["amounts"]
    assert "2023年5月1日" in result["extracted"]["dates"]
    assert "原告姓名" in result["missing_fields"]


def test_extract_rejects_empty_description():
    with pytest.raises(ValueError, match="不能为空"):
        extract_case_info("   ")


def _make_client_with_tmp_db(settings, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """构建数据库指向临时目录的测试客户端。"""
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    from app.api.complaint import get_database_path
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_database_path] = lambda: settings.database_path
    return TestClient(app)


def test_generate_endpoint_success_and_record(settings, monkeypatch: pytest.MonkeyPatch):
    with _make_client_with_tmp_db(settings, monkeypatch) as client:
        response = client.post("/api/complaint/generate", json=_base_form())
        assert response.status_code == 200
        payload = response.json()
        assert "民事起诉状" in payload["document"]
        assert "律师" in payload["review_notice"]
    with get_connection(settings.database_path) as connection:
        row = connection.execute("SELECT case_type, document FROM generations").fetchone()
    assert row is not None
    assert row["case_type"] == "民间借贷纠纷"


def test_generate_endpoint_missing_fields_returns_400(client: TestClient):
    form = _base_form()
    form["facts"] = ""
    form["plaintiff"]["name"] = ""
    response = client.post("/api/complaint/generate", json=form)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "缺少必填字段" in detail
    assert "原告姓名" in detail
    assert "事实与理由" in detail


def test_extract_endpoint(client: TestClient):
    response = client.post(
        "/api/complaint/extract",
        json={"description": "房东不退我押金5000元，有租赁合同和转账记录。"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["form"]["case_type"] == "房屋租赁合同纠纷"
    assert "租赁合同" in payload["form"]["evidence"]
