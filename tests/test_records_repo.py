"""咨询/生成记录仓储测试。"""
from app.repositories.records_repo import (
    list_recent_consultations,
    save_consultation,
    save_generation,
)


def test_save_and_list_consultation(db_conn):
    """保存咨询记录后应能查询，sources 字段正确序列化。"""
    record_id = save_consultation(
        db_conn,
        session_id="session-1",
        consult_type="legal_article",
        question="起诉条件是什么？",
        answer="根据《中华人民共和国民事诉讼法》第一百二十二条……",
        sources=[{"file": "民诉法起诉条件与程序摘录.md", "article_no": "第一百二十二条"}],
    )
    assert record_id > 0

    records = list_recent_consultations(db_conn)
    assert len(records) == 1
    assert records[0]["question"] == "起诉条件是什么？"
    assert records[0]["sources"][0]["article_no"] == "第一百二十二条"


def test_list_recent_consultations_limit(db_conn):
    """最近记录应按时间倒序并遵守数量上限。"""
    for index in range(5):
        save_consultation(
            db_conn,
            session_id="s",
            consult_type="fee",
            question=f"问题{index}",
            answer="",
            sources=[],
        )
    records = list_recent_consultations(db_conn, limit=3)
    assert len(records) == 3
    assert records[0]["question"] == "问题4"


def test_save_generation(db_conn):
    """保存生成记录后应能按 ID 查回。"""
    generation_id = save_generation(
        db_conn,
        case_type="loan",
        form_data={"plaintiff": "张三", "defendant": "李四"},
        document="# 民事起诉状\n……",
    )
    assert generation_id > 0
    row = db_conn.execute(
        "SELECT case_type, document FROM generations WHERE id = ?",
        (generation_id,),
    ).fetchone()
    assert row["case_type"] == "loan"
    assert "民事起诉状" in row["document"]
