def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_detail(client):
    r = client.get("/api/health/detail")
    assert r.status_code == 200
    data = r.json()
    assert data["backend"]["ok"] is True
    assert "docker" in data
    assert "ok" in data["docker"]
    assert "message" in data["docker"]
