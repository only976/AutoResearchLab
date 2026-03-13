from task_agent import adk_runner
from shared.constants import TASK_AGENT_MAX_TURNS
import anyio


def test_task_agent_max_turns_is_100():
    assert TASK_AGENT_MAX_TURNS == 100


def test_build_user_message_includes_execution_context_retry_memory():
    msg, budget = adk_runner._build_user_message(
        task_id="1_1",
        description="prepare dataset",
        input_spec={"description": "deps"},
        resolved_inputs={"a": 1},
        output_spec={"description": "out", "format": "JSON"},
        output_format="JSON",
        validation_spec={"criteria": ["has artifact"]},
        idea_context="global idea",
        execution_context={
            "globalGoal": "global idea",
            "planContext": {"currentTaskId": "1_1"},
            "retryMemory": {
                "attempt": 2,
                "lastFailure": "Agent reached max turns",
                "doNext": ["finish faster"],
            },
        },
    )

    assert "Execution context (global + plan + task + retry memory)" in msg
    assert "Agent reached max turns" in msg
    assert '"attempt": 2' in msg
    assert "RunCommand" in msg
    assert isinstance(budget, dict)
    assert int(budget.get("finalTokensEst", 0)) > 0


def test_build_user_message_compresses_large_context():
    huge_text = "x" * 400000
    msg, budget = adk_runner._build_user_message(
        task_id="1_1",
        description="prepare dataset",
        input_spec={"description": "deps"},
        resolved_inputs={"blob": huge_text},
        output_spec={"description": "out", "format": "JSON"},
        output_format="JSON",
        validation_spec={"criteria": ["has artifact"]},
        idea_context="global idea",
        execution_context={"retryMemory": {"lastFailure": huge_text}},
    )

    assert len(msg) < 200000
    assert int(budget.get("finalTokensEst", 0)) <= int(budget.get("hardLimitTokens", 100000))
    assert "truncated" in str(budget.get("inputs", {})).lower() or "truncated" in msg


async def _run_llm_compression_path(monkeypatch):
    async def fake_chat_completion(*args, **kwargs):
        return '{"compressed": {"globalGoal": "g", "planContext": {"currentTaskId": "1_1"}, "taskContract": {"description": "d"}, "retryMemory": {"attempt": 2, "lastFailure": "f"}}, "notes": ["ok"]}'

    monkeypatch.setattr(adk_runner, "chat_completion", fake_chat_completion)

    value = {
        "globalGoal": "x" * 120000,
        "planContext": {"currentTaskId": "1_1", "history": ["a" * 10000] * 5},
        "taskContract": {"description": "task"},
        "retryMemory": {"attempt": 2, "lastFailure": "too long"},
    }
    compressed, meta = await adk_runner._compress_object_with_llm(
        value,
        label="execution_context",
        target_tokens=2000,
        api_config={"apiKey": "test", "model": "test-model"},
        abort_event=None,
    )

    assert isinstance(compressed, dict)
    assert compressed.get("retryMemory", {}).get("attempt") == 2
    assert meta.get("mode") == "llm"
    assert meta.get("valid") is True


def test_llm_compression_path(monkeypatch):
    anyio.run(_run_llm_compression_path, monkeypatch)
