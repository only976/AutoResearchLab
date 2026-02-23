import json
import os

def test_list_experiments(client, mocker):
    mocker.patch("backend.api.experiments.list_experiments", return_value=[{"id": "exp1"}])
    response = client.get("/api/experiments")
    assert response.status_code == 200
    assert response.json() == [{"id": "exp1"}]

def test_create_experiment(client, mocker):
    # Mock file operations
    mocker.patch("backend.api.experiments.ensure_dir")
    mocker.patch("backend.api.experiments.write_json")
    
    response = client.post(
        "/api/experiments",
        json={"idea": {"title": "Test Idea"}, "topic": {"title": "Test Topic"}}
    )
    assert response.status_code == 200
    assert "id" in response.json()
    assert response.json()["id"].startswith("exp_")

def test_get_experiment_details(client, mocker):
    # Mock ensure_experiment_path and read_json
    mocker.patch("backend.api.experiments.ensure_experiment_path", return_value="/tmp/exp1")
    mocker.patch("backend.api.experiments.read_json", side_effect=lambda path: {"id": "exp1"} if "meta" in path else {})
    
    # Meta
    response = client.get("/api/experiments/exp1/meta")
    assert response.status_code == 200
    assert response.json() == {"id": "exp1"}
    
    # Plan
    mocker.patch("backend.api.experiments.read_json", side_effect=lambda path: {"steps": []} if "plan" in path else None)
    response = client.get("/api/experiments/exp1/plan")
    assert response.status_code == 200
    assert response.json() == {"steps": []}

def test_generate_plan(client, mock_design_agent, mocker):
    mocker.patch("backend.api.experiments.get_workspace_path", return_value="/tmp/exp1")
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch("backend.api.experiments.write_json")
    
    mock_design_agent.refine_plan.return_value = '{"steps": []}'
    
    response = client.post(
        "/api/experiments/exp1/plan",
        json={"idea": {"title": "Idea"}, "topic": {"title": "Topic"}}
    )
    
    assert response.status_code == 200
    assert response.json() == {"steps": []}

def test_run_experiment(client, mock_runner, mocker):
    mocker.patch("backend.api.experiments.get_workspace_path", return_value="/tmp/exp1")
    mocker.patch("backend.api.experiments.read_json", return_value={"steps": []}) # Mock plan exists
    mocker.patch("backend.api.experiments.write_json")
    
    response = client.post(
        "/api/experiments/exp1/run",
        json={"max_iterations": 10}
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "started"
    mock_runner.assert_called_once()
