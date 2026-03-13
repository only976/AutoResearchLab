import json
from pathlib import Path
import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-live-agent",
        action="store_true",
        default=False,
        help="Run live LLM agent skill tests (consumes API tokens). Off by default.",
    )


@pytest.fixture(scope="session")
def run_live_agent(pytestconfig) -> bool:
    return pytestconfig.getoption("--run-live-agent")


@pytest.fixture(scope="session")
def live_llm_config(run_live_agent):
    """
    Reads settings.json to get the active live LLM configuration.
    Tests using this fixture are skipped unless --run-live-agent is passed.
    """
    if not run_live_agent:
        pytest.skip("Skipping live agent test. Pass --run-live-agent to enable (uses API tokens).")

    settings_path = Path(__file__).resolve().parents[3] / "db" / "settings.json"
    if not settings_path.exists():
        pytest.skip("settings.json not found, cannot run live agent tests.")

    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    current = settings.get("current", "")
    config = settings.get("presets", {}).get(current, {})

    if not config or not config.get("apiKey"):
        pytest.skip(
            f"No configured LLM API key for preset '{current}' in settings.json."
        )

    return config


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_llm: live LLM agent test (skipped by default; pass --run-live-agent to enable)",
    )
