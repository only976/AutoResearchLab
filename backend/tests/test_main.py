import json

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_health_detail(client, mocker):
    # Mock DockerSandbox to avoid actual docker calls
    mocker.patch("backend.main.DockerSandbox")
    response = client.get("/api/health/detail")
    assert response.status_code == 200
    assert "backend" in response.json()
    assert "docker" in response.json()

def test_get_config(client):
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "llm_model" in data
    assert "llm_api_base" in data
