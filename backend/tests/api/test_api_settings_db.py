def test_settings_roundtrip(client):
    r = client.get('/api/settings')
    assert r.status_code == 200
    assert 'settings' in r.json()

    payload = {
        'theme': 'light',
        'agentMode': {'ideaAgent': 'mock', 'planAgent': 'mock', 'taskAgent': 'mock', 'paperAgent': 'mock', 'ideaRAG': False},
        'reflection': {'enabled': False, 'maxIterations': 1, 'qualityThreshold': 70},
        'current': 'test',
        'presets': {'test': {'label': 'test', 'baseUrl': '', 'apiKey': '', 'model': 'mock'}},
    }
    s = client.post('/api/settings', json=payload)
    assert s.status_code == 200
    assert s.json().get('success') is True

    r2 = client.get('/api/settings')
    assert r2.status_code == 200
    assert r2.json().get('settings', {}).get('current') == 'test'


def test_db_clear(client):
    r = client.post('/api/db/clear')
    assert r.status_code == 200
    assert r.json().get('success') is True
