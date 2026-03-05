import pytest


@pytest.mark.asyncio
async def test_idea_agent_llm_mock_extract_and_refine():
    from idea_agent.llm.executor import extract_keywords, refine_idea_from_papers

    api_config = {"ideaUseMock": True}

    keywords = await extract_keywords("A fuzzy research idea", api_config)
    assert isinstance(keywords, list)
    assert len(keywords) > 0

    refined = await refine_idea_from_papers(
        "A fuzzy research idea",
        papers=[{"title": "Example Paper", "abstract": "Example abstract"}],
        api_config=api_config,
    )
    assert isinstance(refined, str)
    assert refined.strip()


@pytest.mark.asyncio
async def test_plan_agent_llm_mock_core_calls():
    from plan_agent.llm.executor import assess_quality, check_atomicity, decompose_task, format_task

    def on_thinking(_chunk: str, **_kwargs):
        return None

    api_config = {"planUseMock": True}

    root = {"task_id": "0", "description": "Compare Python vs Node.js", "dependencies": []}

    atomicity = await check_atomicity(
        root,
        on_thinking,
        abort_event=None,
        atomicity_context={"depth": 0, "ancestor_path": "0", "idea": root["description"], "siblings": []},
        use_mock=True,
        api_config=api_config,
    )
    assert isinstance(atomicity, dict)
    assert atomicity.get("atomic") is False

    children = await decompose_task(
        root,
        on_thinking,
        abort_event=None,
        all_tasks=[root],
        idea=root["description"],
        depth=0,
        use_mock=True,
        api_config=api_config,
    )
    assert isinstance(children, list)
    assert any(t.get("task_id") == "1" for t in children)

    atomic_task = {"task_id": "3", "description": "Deployment and ops comparison", "dependencies": []}
    io_spec = await format_task(
        atomic_task,
        on_thinking,
        abort_event=None,
        use_mock=True,
        api_config=api_config,
    )
    assert isinstance(io_spec, dict)
    assert "input" in io_spec and "output" in io_spec

    plan = {"idea": root["description"], "tasks": [root, {**atomic_task, **io_spec}]}
    quality = await assess_quality(plan, on_thinking, abort_event=None, use_mock=True, api_config=api_config)
    assert isinstance(quality, dict)
    assert quality.get("score", 0) > 0


@pytest.mark.asyncio
async def test_task_agent_llm_mock_execute_json():
    from task_agent.llm.executor import execute_task

    api_config = {"taskUseMock": True}
    output = await execute_task(
        task_id="1",
        description="Execute something",
        input_spec={"description": "", "artifacts": [], "parameters": []},
        output_spec={"description": "", "artifact": "x", "format": "JSON"},
        resolved_inputs={},
        api_config=api_config,
    )
    assert isinstance(output, dict)
    assert output.get("_mock") is True


@pytest.mark.asyncio
async def test_paper_agent_mock_run():
    from paper_agent.runner import run_paper_agent

    api_config = {"paperUseMock": True}
    paper = await run_paper_agent(
        plan={"idea": "A test idea", "tasks": []},
        outputs={"1": "Example output"},
        api_config=api_config,
        format_type="markdown",
    )
    assert isinstance(paper, str)
    assert paper.strip()
