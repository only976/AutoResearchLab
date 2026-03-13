from idea_agent.llm import executor as idea_exec


def test_parse_keywords_response_from_json_block():
    text = "Reasoning...\n```json\n{\"keywords\": [\"a\", \"b\"]}\n```"
    assert idea_exec._parse_keywords_response(text) == ["a", "b"]


def test_parse_keywords_response_invalid_returns_empty():
    assert idea_exec._parse_keywords_response("not json") == []


def test_build_papers_context_truncates_and_formats():
    papers = [
        {"title": "T1", "abstract": "A" * 600},
        {"title": "T2", "abstract": "B" * 600},
    ]
    ctx = idea_exec._build_papers_context(papers, max_chars=800)
    assert "[1] T1" in ctx
    # Should not exceed max_chars by much (it may break exactly at boundary)
    assert len(ctx) <= 900


def test_build_papers_context_empty():
    assert idea_exec._build_papers_context([]).startswith("(")
