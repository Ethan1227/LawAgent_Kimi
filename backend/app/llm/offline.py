"""离线规则模板回答：未配置 API Key 时的兜底，标注"当前为离线演示结果"。

所有内容仅基于检索到的知识库条文组织，不编造条文与流程。
"""
from __future__ import annotations

from app.services.knowledge_service import SearchResult

OFFLINE_BANNER = "（当前为离线演示结果，未调用大模型，内容仅供参考）"
INSUFFICIENT_NOTICE = (
    "现有知识库依据不足：无法找到与您问题直接相关的法律条文依据。"
    "为避免误导，本系统不会编造条文、条号、流程或费用。"
)

CONSULT_TYPES: tuple[str, ...] = (
    "民间借贷纠纷",
    "房屋租赁合同纠纷",
    "买卖合同纠纷",
    "起诉流程咨询",
    "诉讼费用咨询",
    "其他民事问题",
)

# 各类型的规则化回答要点
_TYPE_GUIDANCE: dict[str, dict[str, object]] = {
    "民间借贷纠纷": {
        "conclusion": "民间借贷纠纷可先协商，协商不成可向人民法院起诉，要求返还本金并支付合法利息。",
        "steps": [
            "整理借条、欠条、转账记录、催款记录等证据",
            "确定管辖法院（被告住所地或合同履行地）",
            "撰写起诉状并准备副本",
            "到法院立案或网上立案，预交案件受理费",
            "等待开庭通知，参加庭审",
        ],
        "materials": ["起诉状", "身份证复印件", "借条/欠条/借款合同", "转账凭证", "催款记录"],
        "risk": "注意三年诉讼时效；约定利率超过一年期贷款市场报价利率四倍的部分法院不予支持；没有约定利息的视为没有利息。",
        "follow_ups": ["借款金额和约定的利息是多少？", "是否有借条或转账记录？", "是否约定还款期限，是否已过期？"],
    },
    "房屋租赁合同纠纷": {
        "conclusion": "房屋租赁合同纠纷应依据租赁合同约定处理，协商不成可向人民法院起诉。",
        "steps": [
            "整理租赁合同、租金支付凭证、押金收条、房屋交接记录等证据",
            "确定管辖法院（一般为房屋所在地法院）",
            "撰写起诉状并准备副本",
            "到法院立案或网上立案，预交案件受理费",
            "等待开庭通知，参加庭审",
        ],
        "materials": ["起诉状", "身份证复印件", "租赁合同", "租金/押金支付凭证", "房屋交接与沟通记录"],
        "risk": "租期六个月以上未采用书面形式的，可能被视为不定期租赁；承租人拖欠租金经催告仍不支付的，出租人可以解除合同。",
        "follow_ups": ["是否签订了书面租赁合同？", "纠纷是拖欠租金、退还押金还是提前解约？", "租赁期限和租金标准是多少？"],
    },
    "买卖合同纠纷": {
        "conclusion": "买卖合同纠纷可要求对方继续履行、支付价款或赔偿损失，协商不成可向人民法院起诉。",
        "steps": [
            "整理合同、订单、发货单、签收单、发票、付款凭证等证据",
            "确定管辖法院（被告住所地或合同履行地，有协议管辖从其约定）",
            "撰写起诉状并准备副本",
            "到法院立案或网上立案，预交案件受理费",
            "等待开庭通知，参加庭审",
        ],
        "materials": ["起诉状", "身份证复印件", "买卖合同/订单", "发货与签收凭证", "付款凭证与发票"],
        "risk": "买受人应在检验期限内提出质量异议，怠于通知可能视为质量符合约定；注意三年诉讼时效。",
        "follow_ups": ["是否签订了书面买卖合同？", "纠纷是拖欠货款还是货物质量问题？", "合同金额和履行情况如何？"],
    },
    "起诉流程咨询": {
        "conclusion": "民事起诉需满足法定起诉条件，向有管辖权的法院递交起诉状，符合条件法院应在七日内立案。",
        "steps": [
            "准备起诉状（记明原被告信息、诉讼请求、事实与理由、证据）",
            "准备身份证明材料与证据材料",
            "向有管辖权的法院提交立案（现场或网上立案）",
            "法院审查，符合条件七日内立案并通知",
            "接到交费通知后七日内交纳案件受理费",
            "等待法院送达、排期开庭",
        ],
        "materials": ["起诉状正本及副本", "身份证复印件", "证据材料复印件", "送达地址确认书"],
        "risk": "起诉必须有明确的被告和具体的诉讼请求；不属于法院主管或管辖的，法院不予受理。",
        "follow_ups": ["您的纠纷属于哪种类型（借款/租赁/买卖等）？", "被告的身份信息是否明确？", "涉案金额大约是多少？"],
    },
    "诉讼费用咨询": {
        "conclusion": "财产案件受理费按诉讼请求金额比例分段累计交纳，原告预交，最终由败诉方负担。",
        "steps": [
            "确定诉讼请求金额",
            "按照比例分段累计计算受理费（不超过1万元每件50元）",
            "立案后按法院通知七日内交纳",
            "适用简易程序审理的减半交纳",
        ],
        "materials": ["诉讼费用交纳通知", "缴费凭证"],
        "risk": "逾期未交纳受理费且未申请司法救助的，可能按撤诉处理。",
        "follow_ups": ["您的诉讼请求金额是多少？", "案件是否可能适用简易程序？"],
    },
    "其他民事问题": {
        "conclusion": "民事纠纷一般可先协商、调解，协商不成可向人民法院起诉。",
        "steps": [
            "梳理纠纷事实与现有证据",
            "明确诉求与法律依据",
            "咨询专业律师或向法院诉讼服务中心咨询",
        ],
        "materials": ["与纠纷相关的合同、凭证、沟通记录"],
        "risk": "注意诉讼时效一般为三年，证据应尽早固定保存。",
        "follow_ups": ["您的纠纷具体是什么类型？", "目前手上有哪些证据材料？"],
    },
}

MAX_FOLLOW_UPS = 3


def build_offline_answer(
    consult_type: str,
    sources: list[SearchResult],
    *,
    sufficient: bool,
) -> str:
    """基于规则模板与检索条文组织离线回答。"""
    guidance = _TYPE_GUIDANCE.get(consult_type, _TYPE_GUIDANCE["其他民事问题"])
    sections: list[str] = [OFFLINE_BANNER, ""]
    sections.append(f"【简要结论】\n{guidance['conclusion']}")

    if not sufficient:
        sections.append(f"\n【依据说明】\n{INSUFFICIENT_NOTICE}")

    if sources:
        lines = []
        for item in sources:
            location = f"{item.doc_title} {item.article_no}".strip()
            snippet = item.content[:80] + ("..." if len(item.content) > 80 else "")
            lines.append(f"- 《{item.source_file}》{location}：{snippet}")
        sections.append("\n【适用条文】\n" + "\n".join(lines))
    else:
        sections.append("\n【适用条文】\n知识库中未检索到直接相关条文。")

    steps = guidance["steps"]
    assert isinstance(steps, list)
    sections.append(
        "\n【流程步骤】\n" + "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))
    )

    materials = guidance["materials"]
    assert isinstance(materials, list)
    sections.append("\n【所需材料】\n" + "、".join(str(m) for m in materials))

    sections.append(f"\n【风险提示】\n{guidance['risk']}")
    sections.append("\n【建议补充】\n为给出更准确的分析，请补充回答下方追问。")
    return "\n".join(sections)


def build_insufficient_answer(consult_type: str) -> str:
    """依据不足时的回答：明确提示不编造，仅给出通用指引。"""
    guidance = _TYPE_GUIDANCE.get(consult_type, _TYPE_GUIDANCE["其他民事问题"])
    return "\n".join(
        [
            OFFLINE_BANNER,
            "",
            f"【依据说明】\n{INSUFFICIENT_NOTICE}",
            f"\n【通用建议】\n{guidance['conclusion']}",
            f"\n【风险提示】\n{guidance['risk']}",
        ]
    )


def get_follow_ups(consult_type: str) -> list[str]:
    """返回该咨询类型的关键追问（最多 3 个）。"""
    guidance = _TYPE_GUIDANCE.get(consult_type, _TYPE_GUIDANCE["其他民事问题"])
    follow_ups = guidance["follow_ups"]
    assert isinstance(follow_ups, list)
    return [str(item) for item in follow_ups[:MAX_FOLLOW_UPS]]
