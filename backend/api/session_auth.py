"""Session credential helpers shared by API runtime state."""

import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException


def _load_or_create_session_secret() -> str:
    """Load a stable session signing secret."""

    env = os.getenv("MAARS_SESSION_SECRET")
    if env and env.strip():
        return env.strip()
    try:
        secret_file = Path(__file__).resolve().parent.parent / "db" / "session_secret.txt"
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        if secret_file.exists():
            secret_text = secret_file.read_text(encoding="utf-8").strip()
            if secret_text:
                return secret_text
        secret_text = secrets.token_hex(32)
        secret_file.write_text(secret_text, encoding="utf-8")
        return secret_text
    except Exception:
        return secrets.token_hex(32)


_SESSION_SECRET = _load_or_create_session_secret()
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def normalize_session_id(raw_session_id: Optional[str]) -> str:
    """Normalize and validate session id."""

    sid = str(raw_session_id or "").strip()
    if not sid:
        raise ValueError("sessionId is required")
    sid = sid.replace("/", "_").replace("\\", "_")
    sid = sid[:128]
    if not _SESSION_ID_RE.match(sid):
        raise ValueError("Invalid sessionId format")
    return sid


def _sign_session_id(session_id: str) -> str:
    return hmac.new(
        _SESSION_SECRET.encode("utf-8"),
        session_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_session_token(session_id: str, session_token: Optional[str]) -> bool:
    token = str(session_token or "").strip()
    if not token:
        return False
    expected = _sign_session_id(session_id)
    return hmac.compare_digest(expected, token)


def issue_session_credentials() -> dict[str, str]:
    """Create a new signed session credential pair."""

    session_id = normalize_session_id(f"sess_{secrets.token_urlsafe(18)}")
    session_token = _sign_session_id(session_id)
    return {"sessionId": session_id, "sessionToken": session_token}


def resolve_session_id(request: Any) -> str:
    """Resolve and verify session id/token from HTTP request."""

    header_sid = request.headers.get("X-MAARS-SESSION-ID")
    header_token = request.headers.get("X-MAARS-SESSION-TOKEN")
    query_sid = request.query_params.get("sessionId")
    query_token = request.query_params.get("sessionToken")
    cookies = getattr(request, "cookies", None) or {}
    cookie_sid = cookies.get("maars_sid")
    cookie_token = cookies.get("maars_stoken")
    raw_sid = header_sid or query_sid or cookie_sid
    raw_token = header_token or query_token or cookie_token
    if not raw_sid or not raw_token:
        raise HTTPException(status_code=401, detail="Missing session credentials")
    try:
        session_id = normalize_session_id(raw_sid)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    if not verify_session_token(session_id, raw_token):
        raise HTTPException(status_code=401, detail="Invalid session credentials")
    return session_id


def resolve_socket_session_id(auth: Any) -> str:
    """Resolve and verify session id/token from websocket auth payload."""

    if not isinstance(auth, dict):
        raise ValueError("Missing socket auth")
    raw_sid = auth.get("sessionId")
    raw_token = auth.get("sessionToken")
    session_id = normalize_session_id(raw_sid)
    if not verify_session_token(session_id, raw_token):
        raise ValueError("Invalid session credentials")
    return session_id
