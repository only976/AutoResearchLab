from __future__ import annotations

from pathlib import Path

from backend.experiments.agents.data_agent import docker_data_agent as dda


def test_parse_and_checks_metrics_csv() -> None:
    base_dir = Path(__file__).parent
    metrics_path = base_dir / "test_metrics.csv"

    parsed = dda.parse_input_files([str(metrics_path)], use_llm=False)
    assert parsed["series"], "series should not be empty"

    column_types = parsed.get("column_types", {})
    keys = list(column_types.keys())

    # Ensure key mappings exist
    assert any(k.endswith("::loss") for k in keys)
    assert any(k.endswith("::accuracy") for k in keys)
    assert any(k.endswith("::time_or_step") for k in keys)
    assert any(k.endswith("::energy") for k in keys)

    # Run checks and ensure no failures for clean test data
    checks = dda.run_checks(parsed)
    assert checks, "checks should not be empty"
    assert not any(c.get("status") == "fail" for c in checks)


def test_generate_visuals_from_metrics_csv() -> None:
    base_dir = Path(__file__).parent
    metrics_path = base_dir / "test_metrics.csv"

    parsed = dda.parse_input_files([str(metrics_path)], use_llm=False)
    visuals = dda.generate_visuals(parsed)
    assert isinstance(visuals, list)
    assert len(visuals) >= 1


def test_parse_summary_csv() -> None:
    base_dir = Path(__file__).parent
    summary_path = base_dir / "test_summary.csv"

    parsed = dda.parse_input_files([str(summary_path)], use_llm=False)
    assert parsed["series"], "summary series should not be empty"
