import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from backend.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def mock_idea_agent(mocker):
    mock = mocker.patch("backend.api.ideas.IdeaAgent")
    return mock.return_value

@pytest.fixture
def mock_design_agent(mocker):
    mock = mocker.patch("backend.api.experiments.ExperimentDesignAgent")
    return mock.return_value

@pytest.fixture
def mock_writing_agent(mocker):
    mock = mocker.patch("backend.api.paper.WritingAgent")
    return mock.return_value

@pytest.fixture
def mock_runner(mocker):
    return mocker.patch("backend.api.experiments.start_experiment_background")
