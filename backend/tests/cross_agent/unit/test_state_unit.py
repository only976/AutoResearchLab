import pytest


class _DummyRequest:
    def __init__(self, *, headers=None, query_params=None):
        self.headers = headers or {}
        self.query_params = query_params or {}


def test_create_session_credentials_and_resolve_via_headers():
    from api import state

    creds = state.issue_session_credentials()
    assert "sessionId" in creds and "sessionToken" in creds

    req = _DummyRequest(
        headers={
            "X-MAARS-SESSION-ID": creds["sessionId"],
            "X-MAARS-SESSION-TOKEN": creds["sessionToken"],
        }
    )
    resolved = state.resolve_session_id(req)
    assert resolved == creds["sessionId"]


def test_resolve_session_id_missing_credentials_401():
    from api import state

    req = _DummyRequest(headers={}, query_params={})
    with pytest.raises(state.HTTPException) as e:
        state.resolve_session_id(req)
    assert e.value.status_code == 401


def test_resolve_session_id_rejects_bad_token():
    from api import state

    creds = state.issue_session_credentials()
    req = _DummyRequest(
        headers={
            "X-MAARS-SESSION-ID": creds["sessionId"],
            "X-MAARS-SESSION-TOKEN": "not-a-valid-token",
        }
    )
    with pytest.raises(state.HTTPException) as e:
        state.resolve_session_id(req)
    assert e.value.status_code == 401


def test_normalize_session_id_validation():
    from api import state

    ok = state.normalize_session_id("sess_Abcdefgh_1234")
    assert ok.startswith("sess_")

    with pytest.raises(ValueError):
        state.normalize_session_id("bad space")

    # Long input is truncated to 128 chars (and may still be valid).
    out = state.normalize_session_id("sess_" + ("x" * 200))
    assert len(out) == 128
