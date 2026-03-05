def test_frontend_log_endpoint_writes_file(client, session_headers, logs_dir):
    payload = {
        "entries": [
            {
                "level": "error",
                "message": "frontend test error",
                "ts": 123.0,
                "url": "http://example.local/",
                "context": {"k": "v"},
            }
        ]
    }

    r = client.post("/api/log/frontend", headers=session_headers, json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("count") == 1

    log_file = logs_dir / "frontend.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "frontend test error" in content
