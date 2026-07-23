"""自然语言案件信息提取（规则版）：从一段描述中提取表单字段。

输出部分表单 + 缺失字段列表，供前端自动填充后再人工补全。
"""
from __future__ import annotations

import re
from typing import Any

from app.services.complaint_templates import CASE_TYPES

# 案件类型关键词（优先级从上到下）
_CASE_TYPE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("民间借贷纠纷", ("借", "欠条", "借条", "还款", "利息")),
    ("房屋租赁合同纠纷", ("租", "押金", "房东", "租客", "承租", "出租")),
    ("买卖合同纠纷", ("买卖", "货款", "发货", "收货", "质量", "订单")),
)

_AMOUNT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(万)?\s*元")
_DATE_PATTERN = re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日")
_DEFENDANT_PATTERNS = (
    re.compile(r"被告[是为：:，,]?\s*([一-龥]{2,4})"),
    re.compile(r"([一-龥]{2,4})(?:向我|找我|跟我|向我方)借"),
)
_COURT_PATTERN = re.compile(r"([一-龥]{2,}(?:市|区|县|州|盟)?人民法院)")
_CLAIM_SENTENCE_PATTERN = re.compile(r"(?:要求|请求|判令|希望)([^。；;\n]{2,60})")
_EVIDENCE_KEYWORDS = (
    "借条", "欠条", "借款合同", "租赁合同", "买卖合同", "合同",
    "转账记录", "转账凭证", "收条", "收据", "发票", "订单",
    "聊天记录", "录音", "照片", "视频", "物流单", "签收单",
)


def _detect_case_type(text: str) -> str | None:
    for case_type, keywords in _CASE_TYPE_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return case_type
    return None


def _extract_defendant(text: str) -> str:
    for pattern in _DEFENDANT_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return ""


def _extract_claims(text: str) -> list[str]:
    claims = [match.strip() for match in _CLAIM_SENTENCE_PATTERN.findall(text)]
    return [f"{claim}。".replace("。。", "。") for claim in claims][:5]


def _extract_evidence(text: str) -> list[str]:
    found: list[str] = []
    for keyword in _EVIDENCE_KEYWORDS:
        if keyword in text and keyword not in found:
            # 归并：已包含"借款合同"时不再单列"合同"
            if any(keyword in existing for existing in found):
                continue
            found = [existing for existing in found if existing not in keyword]
            found.append(keyword)
    return found


def extract_case_info(description: str) -> dict[str, Any]:
    """从自然语言描述提取案件信息，返回 {form, missing_fields}。"""
    if not description.strip():
        raise ValueError("案件描述不能为空")
    case_type = _detect_case_type(description)
    defendant = _extract_defendant(description)
    court_match = _COURT_PATTERN.search(description)

    form: dict[str, Any] = {
        "case_type": case_type or "",
        "plaintiff": {"name": "", "gender": "", "id_number": "", "address": "", "phone": ""},
        "defendant": {
            "name": defendant,
            "gender": "",
            "id_number": "",
            "address": "",
            "phone": "",
        },
        "claims": _extract_claims(description),
        "facts": description.strip(),
        "evidence": _extract_evidence(description),
        "court": court_match.group(1) if court_match else "",
        "date": "",
    }
    extracted_notes = {
        "amounts": [match.group(0) for match in _AMOUNT_PATTERN.finditer(description)],
        "dates": _DATE_PATTERN.findall(description),
    }
    missing = []
    if not case_type:
        missing.append("案件类型")
    if not defendant:
        missing.append("被告姓名")
    missing.append("原告姓名")
    if not form["claims"]:
        missing.append("诉讼请求")
    if not form["court"]:
        missing.append("拟提交法院")
    return {"form": form, "extracted": extracted_notes, "missing_fields": missing}


__all__ = ["extract_case_info", "CASE_TYPES"]
