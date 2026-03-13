def test_session_init_and_verify(client):
    r = client.post('/api/session/init')
    assert r.status_code == 200
    data = r.json()
    assert 'sessionId' in data and 'sessionToken' in data

    headers = {
        'X-MAARS-SESSION-ID': data['sessionId'],
        'X-MAARS-SESSION-TOKEN': data['sessionToken'],
    }
    v = client.get('/api/session/verify', headers=headers)
    assert v.status_code == 200
    vd = v.json()
    assert vd.get('ok') is True
    assert vd.get('sessionId') == data['sessionId']


def test_status_endpoint(client):
    r = client.get('/api/status')
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {'hasIdea', 'hasPlan'}
    assert data['hasIdea'] in (True, False)
    assert data['hasPlan'] in (True, False)
