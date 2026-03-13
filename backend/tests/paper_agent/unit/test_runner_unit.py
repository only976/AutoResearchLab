from paper_agent import runner as paper_runner


def test_maars_plan_to_paper_format_shapes_steps():
    plan = {
        "idea": "My Idea",
        "tasks": [
            {"task_id": "0", "description": "Root", "dependencies": []},
            {"task_id": "1", "description": "Step 1", "dependencies": []},
        ],
    }
    fmt = paper_runner._maars_plan_to_paper_format(plan)
    assert fmt["title"] == "My Idea"
    assert fmt["goal"] == "My Idea"
    assert any(s.get("description") == "Step 1" for s in fmt["steps"])


def test_synthesize_conclusion_from_outputs_handles_dict_and_str():
    outputs = {
        "1": {"content": "Hello"},
        "2": "Plain text",
    }
    conclusion = paper_runner._synthesize_conclusion_from_outputs(outputs)
    assert conclusion["summary"]
    assert isinstance(conclusion.get("key_findings"), list)
    assert any("Task 1" in x for x in conclusion["key_findings"])
    assert any("Task 2" in x for x in conclusion["key_findings"])
