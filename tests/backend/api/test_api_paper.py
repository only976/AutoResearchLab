import json

def test_generate_draft(client, mock_writing_agent, mocker):
    mocker.patch("backend.api.paper.ensure_experiment_path", return_value="/tmp/exp1")
    mocker.patch("backend.api.paper.read_json", side_effect=lambda path: {"steps": []} if "plan" in path else {"content": "conclusion"})
    mocker.patch("os.listdir", return_value=["chart.png"])
    
    mock_writing_agent.generate_paper.return_value = "# Draft Paper"
    
    response = client.post(
        "/api/experiments/exp1/draft",
        json={"format": "markdown"}
    )
    
    assert response.status_code == 200
    assert response.json() == {"format": "markdown", "content": "# Draft Paper"}
    mock_writing_agent.generate_paper.assert_called_once()
