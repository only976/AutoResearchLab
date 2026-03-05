import pytest

from plan_agent.llm import executor as plan_exec


def test_parse_json_response_from_codeblock():
    out = plan_exec._parse_json_response("```json\n{\"a\": 1}\n```")
    assert out == {"a": 1}


def test_validate_atomicity_response():
    assert plan_exec._validate_atomicity_response({"atomic": True}) is True
    assert plan_exec._validate_atomicity_response({"atomic": 1}) is True
    assert plan_exec._validate_atomicity_response({}) is False


def test_validate_decompose_response_happy_path():
    parent_id = "1"
    result = {
        "tasks": [
            {"task_id": "1_1", "description": "Child 1", "dependencies": []},
            {"task_id": "1_2", "description": "Child 2", "dependencies": ["1_1"]},
        ]
    }
    ok, err = plan_exec._validate_decompose_response(result, parent_id)
    assert ok is True
    assert err == ""


def test_validate_decompose_response_rejects_bad_dependency_order():
    parent_id = "1"
    result = {
        "tasks": [
            {"task_id": "1_1", "description": "Child 1", "dependencies": ["1_2"]},
            {"task_id": "1_2", "description": "Child 2", "dependencies": []},
        ]
    }
    ok, err = plan_exec._validate_decompose_response(result, parent_id)
    assert ok is False
    assert "must be an earlier sibling" in err


def test_build_user_message_atomicity_includes_context():
    msg = plan_exec._build_user_message(
        "atomicity",
        {"task_id": "1", "description": "Test"},
        {"depth": 1, "ancestor_path": "0>1", "idea": "Idea", "siblings": []},
    )
    assert "ancestor path" in msg
    assert "Context - idea" in msg


def test_parse_json_response_invalid_raises():
    out = plan_exec._parse_json_response("not json")
    assert not isinstance(out, dict)
