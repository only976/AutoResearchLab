def test_config_roundtrip(client):
    # defaults
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "llm_model" in data
    assert "frontend_port" in data

    # overwrite
    payload = {
        "llm_model": "gemini-3-flash-preview",
        "llm_api_base": "https://example.invalid",
        "llm_api_key": "test_key",
        "frontend_port": 4040,
        "backend_port": 9999,  # should be ignored
    }
    r2 = client.post("/api/config", json=payload)
    assert r2.status_code == 200
    assert r2.json()["success"] is True

    # read back
    r3 = client.get("/api/config")
    assert r3.status_code == 200
    out = r3.json()
    assert out["llm_model"] == "gemini-3-flash-preview"
    assert out["llm_api_base"] == "https://example.invalid"
    assert out["llm_api_key"] == "test_key"
    assert out["llm_api_key_configured"] is True
    assert out["frontend_port"] == 4040
