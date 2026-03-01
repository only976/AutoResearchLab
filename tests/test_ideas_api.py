import json


def test_ideas_refine_stubbed(client, monkeypatch):
    # Patch IdeaAgent used by the route module, so we don't call LLM.
    import backend.api.ideas as ideas_api

    class DummyIdeaAgent:
        def refine_topic(self, scope: str) -> str:
            return json.dumps({"is_broad": True, "analysis": "ok", "topics": [{"title": "t", "scope": scope}]})

    monkeypatch.setattr(ideas_api, "IdeaAgent", DummyIdeaAgent, raising=True)

    r = client.post("/api/ideas/refine", json={"scope": "AI for science"})
    assert r.status_code == 200
    data = r.json()
    assert data["is_broad"] is True
    assert data["topics"][0]["scope"] == "AI for science"


def test_ideas_generate_saves_snapshot_stubbed(client, monkeypatch, tmp_path):
    import backend.api.ideas as ideas_api
    import backend.ideas.snapshots as snapshots

    # redirect snapshot dir to temp
    monkeypatch.setattr(snapshots, "SNAPSHOT_DIR", str(tmp_path / "snapshots"), raising=True)

    class DummyIdeaAgent:
        def generate_ideas(self, scope: str) -> str:
            return json.dumps({"ideas": [{"title": "Idea1"}], "reasoning": {}})

        def generate_snapshot_title(self, refined_topic, snapshot_results) -> str:
            return "dummy_title"

    monkeypatch.setattr(ideas_api, "IdeaAgent", DummyIdeaAgent, raising=True)

    r = client.post("/api/ideas/generate", json={"scope": "{\"title\": \"X\"}"})
    assert r.status_code == 200
    data = r.json()
    assert "ideas" in data

    # list should show snapshot file created
    r2 = client.get("/api/ideas/snapshots")
    assert r2.status_code == 200
    files = r2.json()["files"]
    assert isinstance(files, list)
    assert len(files) >= 1
