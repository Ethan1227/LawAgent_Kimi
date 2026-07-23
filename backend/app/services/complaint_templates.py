"""民事起诉状模板：三类案件的结构化渲染。

- 必填字段缺失时显式报错（列出全部缺失字段）
- 选填字段未知时标注【待补充】
"""
from __future__ import annotations

from datetime import date
from typing import Any

PLACEHOLDER = "【待补充】"

CASE_TYPES: tuple[str, ...] = (
    "民间借贷纠纷",
    "房屋租赁合同纠纷",
    "买卖合同纠纷",
)

# 各类型的案由说明段落（写入事实与理由开头，帮助法官快速定位案由）
CASE_TYPE_INTRO: dict[str, str] = {
    "民间借贷纠纷": "原告与被告之间系民间借贷关系。",
    "房屋租赁合同纠纷": "原告与被告之间系房屋租赁合同关系。",
    "买卖合同纠纷": "原告与被告之间系买卖合同关系。",
}

REQUIRED_FIELDS: tuple[str, ...] = (
    "case_type",
    "plaintiff_name",
    "defendant_name",
    "claims",
    "facts",
    "court",
)

FIELD_LABELS: dict[str, str] = {
    "case_type": "案件类型",
    "plaintiff_name": "原告姓名",
    "defendant_name": "被告姓名",
    "claims": "诉讼请求",
    "facts": "事实与理由",
    "court": "拟提交法院",
}


def _party_line(role: str, party: dict[str, Any]) -> str:
    """渲染一方当事人信息行，未知项标【待补充】。"""
    name = (party.get("name") or "").strip() or PLACEHOLDER
    gender = (party.get("gender") or "").strip() or PLACEHOLDER
    id_number = (party.get("id_number") or "").strip() or PLACEHOLDER
    address = (party.get("address") or "").strip() or PLACEHOLDER
    phone = (party.get("phone") or "").strip() or PLACEHOLDER
    return (
        f"{role}：{name}，性别：{gender}，公民身份号码：{id_number}，"
        f"住所：{address}，联系方式：{phone}。"
    )


def validate_form(form: dict[str, Any]) -> list[str]:
    """校验必填字段，返回缺失字段标签列表（空列表表示通过）。"""
    missing: list[str] = []
    case_type = str(form.get("case_type") or "").strip()
    if case_type not in CASE_TYPES:
        missing.append(f"{FIELD_LABELS['case_type']}（可选：{'、'.join(CASE_TYPES)}）")
    plaintiff = form.get("plaintiff") or {}
    defendant = form.get("defendant") or {}
    if not str(plaintiff.get("name") or "").strip():
        missing.append(FIELD_LABELS["plaintiff_name"])
    if not str(defendant.get("name") or "").strip():
        missing.append(FIELD_LABELS["defendant_name"])
    claims = form.get("claims") or []
    if not [item for item in claims if str(item).strip()]:
        missing.append(FIELD_LABELS["claims"])
    if not str(form.get("facts") or "").strip():
        missing.append(FIELD_LABELS["facts"])
    if not str(form.get("court") or "").strip():
        missing.append(FIELD_LABELS["court"])
    return missing


def render_complaint(form: dict[str, Any]) -> str:
    """渲染民事起诉状。必填缺失时抛出 ValueError（显式失败）。"""
    missing = validate_form(form)
    if missing:
        raise ValueError(f"缺少必填字段：{'、'.join(missing)}")

    case_type = str(form["case_type"]).strip()
    plaintiff = form["plaintiff"]
    defendant = form["defendant"]
    claims = [str(item).strip() for item in form["claims"] if str(item).strip()]
    evidence = [str(item).strip() for item in (form.get("evidence") or []) if str(item).strip()]
    facts = str(form["facts"]).strip()
    court = str(form["court"]).strip()
    suit_date = str(form.get("date") or "").strip() or date.today().isoformat()

    lines: list[str] = [
        "# 民事起诉状",
        "",
        _party_line("原告", plaintiff),
        "",
        _party_line("被告", defendant),
        "",
        f"案由：{case_type}",
        "",
        "## 诉讼请求",
    ]
    lines.extend(f"{index}. {claim}" for index, claim in enumerate(claims, 1))
    lines.extend(
        [
            "",
            "## 事实与理由",
            "",
            f"{CASE_TYPE_INTRO[case_type]}{facts}",
            "",
            "## 证据和证据来源，证人姓名和住所",
        ]
    )
    if evidence:
        lines.extend(f"{index}. {item}" for index, item in enumerate(evidence, 1))
    else:
        lines.append(PLACEHOLDER)
    lines.extend(
        [
            "",
            f"此致",
            f"{court}",
            "",
            f"起诉人（签名）：{str(plaintiff['name']).strip()}",
            f"{suit_date}",
        ]
    )
    return "\n".join(lines)
