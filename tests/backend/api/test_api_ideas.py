import json

def test_refine_ideas(client, mock_idea_agent):
    mock_idea_agent.refine_topic.return_value = '{"title": "Test Topic", "tldr": "Test TLDR"}'
    
    response = client.post(
        "/api/ideas/refine",
        json={"scope": "test scope"}
    )
    
    assert response.status_code == 200
    assert response.json() == {"title": "Test Topic", "tldr": "Test TLDR"}
    mock_idea_agent.refine_topic.assert_called_once_with("test scope")

def test_generate_ideas(client, mock_idea_agent):
    mock_idea_agent.generate_ideas.return_value = '{"ideas": [{"title": "Idea 1"}]}'
    
    response = client.post(
        "/api/ideas/generate",
        json={"scope": "test scope"}
    )
    
    assert response.status_code == 200
    assert response.json() == {"ideas": [{"title": "Idea 1"}]}
    mock_idea_agent.generate_ideas.assert_called_once_with("test scope")

def test_snapshots(client, mocker):
    # Mock snapshot manager functions
    mocker.patch("backend.api.ideas.list_snapshots", return_value=["test.json"])
    mocker.patch("backend.api.ideas.save_snapshot", return_value="test.json")
    mocker.patch("backend.api.ideas.load_snapshot", return_value={"data": "test"})
    
    # List
    response = client.get("/api/ideas/snapshots")
    assert response.status_code == 200
    assert response.json() == {"files": ["test.json"]}
    
    # Save
    response = client.post(
        "/api/ideas/snapshots",
        json={"refinement_data": {}, "results": []}
    )
    assert response.status_code == 200
    assert response.json() == {"file": "test.json"}
    
    # Load
    response = client.get("/api/ideas/snapshots/test.json")
    assert response.status_code == 200
    assert response.json() == {"data": "test"}
