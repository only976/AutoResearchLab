def test_generate_draft_stubbed(client, monkeypatch):
    import backend.api.paper as paper_api

    async def _get_maars_plan_and_outputs(_exp_id: str):
        return (
            {"idea": "Test", "tasks": [{"description": "step1"}]},
            {"0": {"content": "out"}},
        )

    class DummyWritingAgent:
        def generate_paper(self, *args, **kwargs):
            return "DRAFT"

    monkeypatch.setattr(paper_api, "_get_maars_plan_and_outputs", _get_maars_plan_and_outputs, raising=True)
    monkeypatch.setattr(paper_api, "WritingAgent", DummyWritingAgent, raising=True)

    r = client.post("/api/experiments/exp1/draft", json={"format": "markdown"})
    assert r.status_code == 200
    data = r.json()
    assert data["format"] == "markdown"
    assert data["content"] == "DRAFT"
