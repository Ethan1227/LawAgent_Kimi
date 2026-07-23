"""健康检查接口测试。"""


def test_health_check(client):
    """健康检查接口应返回 200 与服务状态信息。"""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "民事诉状生成与法律咨询系统"
    assert data["version"]
