"""COROS OAuth authorization routes for the standalone web app.

Flow (browser):
  1. GET  /api/v1/auth/coros/login
       → registers a client (DCR, cached), builds a PKCE authorize URL,
         stores {state: code_verifier}, 302-redirects the browser to COROS.
  2. user logs in on COROS's hosted page and approves.
  3. GET  /api/v1/auth/coros/callback?code=&state=
       → exchanges the code for tokens, creates a session, then 302-redirects
         back to the frontend with ?coros=connected&session=<id>.
  4. GET  /api/v1/auth/coros/status?session=<id>
       → reports whether that session holds a valid COROS connection.

Token storage here is an in-memory dict for the MVP. Production should persist
encrypted refresh tokens per user — see docs/PERSISTENCE-DESIGN.md. The store is
exposed via get_session_token() so the /analyze route can use it.
"""
from __future__ import annotations

import os
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.services import coros_oauth


router = APIRouter()

# ── config ─────────────────────────────────────────────────────────────────────
def _backend_base() -> str:
    return os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8010")


def _web_base() -> str:
    return os.getenv("WEB_BASE_URL", "http://localhost:3000")


def _redirect_uri() -> str:
    return f"{_backend_base()}/api/v1/auth/coros/callback"


# ── session stores ─────────────────────────────────────────────────────────────
# pending PKCE handshakes (in-memory, short-lived): state -> {code_verifier, created_at}
_PENDING: dict[str, dict] = {}
# active sessions: session_id -> {access_token, refresh_token, expires_at, client_id}
# Persisted to disk so a server restart does not drop authenticated users.
# NOTE: MVP-grade. Production should use an encrypted per-user store — see
# docs/PERSISTENCE-DESIGN.md.
from pathlib import Path as _Path
import json as _json

_SESSIONS_FILE = _Path(__file__).resolve().parents[3] / "data" / "coros_sessions.json"
_PENDING_TTL_SEC = 600


def _load_sessions() -> dict[str, dict]:
    if _SESSIONS_FILE.exists():
        try:
            return _json.loads(_SESSIONS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_sessions() -> None:
    try:
        _SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SESSIONS_FILE.write_text(_json.dumps(_SESSIONS))
    except OSError:
        pass


_SESSIONS: dict[str, dict] = _load_sessions()


def _prune_pending() -> None:
    now = time.time()
    for state in [s for s, v in _PENDING.items() if now - v["created_at"] > _PENDING_TTL_SEC]:
        _PENDING.pop(state, None)


# ── public accessor for other routes ───────────────────────────────────────────

def get_session_token(session_id: str | None) -> str | None:
    """Return a valid access_token for a session, refreshing if near expiry."""
    if not session_id:
        return None
    sess = _SESSIONS.get(session_id)
    if not sess:
        return None
    # refresh if expired (or within 60s of expiry) and we have a refresh token
    if sess.get("expires_at", 0) - 60 < time.time() and sess.get("refresh_token"):
        try:
            token = coros_oauth.refresh_access_token(sess["client_id"], sess["refresh_token"])
            sess["access_token"] = token["access_token"]
            sess["refresh_token"] = token.get("refresh_token", sess["refresh_token"])
            sess["expires_at"] = time.time() + int(token.get("expires_in", 3600))
            _save_sessions()
        except coros_oauth.CorosOAuthError:
            return sess.get("access_token")
    return sess.get("access_token")


# ── routes ──────────────────────────────────────────────────────────────────────

@router.get("/coros/login")
def coros_login() -> RedirectResponse:
    """Start the COROS OAuth flow — 302 to COROS's hosted login/consent page."""
    redirect_uri = _redirect_uri()
    try:
        client_id = coros_oauth.register_client(redirect_uri)
        url, code_verifier, state = coros_oauth.build_authorize_url(client_id, redirect_uri)
    except coros_oauth.CorosOAuthError as exc:
        raise HTTPException(status_code=502, detail=f"无法发起高驰授权: {exc}") from exc

    _prune_pending()
    _PENDING[state] = {"code_verifier": code_verifier, "client_id": client_id, "created_at": time.time()}
    return RedirectResponse(url, status_code=302)


@router.get("/coros/callback")
def coros_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """OAuth redirect target. Exchanges code→tokens, creates a session, then
    bounces the browser back to the frontend."""
    web = _web_base()
    if error:
        return RedirectResponse(f"{web}/?coros=error&reason={error}", status_code=302)
    if not code or not state or state not in _PENDING:
        return RedirectResponse(f"{web}/?coros=error&reason=invalid_state", status_code=302)

    pending = _PENDING.pop(state)
    try:
        token = coros_oauth.exchange_code(
            client_id=pending["client_id"],
            redirect_uri=_redirect_uri(),
            code=code,
            code_verifier=pending["code_verifier"],
        )
    except coros_oauth.CorosOAuthError:
        return RedirectResponse(f"{web}/?coros=error&reason=token_exchange", status_code=302)

    session_id = uuid4().hex
    _SESSIONS[session_id] = {
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token"),
        "expires_at": time.time() + int(token.get("expires_in", 3600)),
        "client_id": pending["client_id"],
    }
    _save_sessions()
    return RedirectResponse(f"{web}/?coros=connected&session={session_id}", status_code=302)


@router.get("/coros/status")
def coros_status(session: str | None = Query(default=None)) -> dict:
    """Report whether a session is connected to COROS."""
    token = get_session_token(session)
    return {"connected": bool(token)}


@router.post("/coros/logout")
def coros_logout(session: str | None = Query(default=None)) -> dict:
    if session:
        _SESSIONS.pop(session, None)
        _save_sessions()
    return {"connected": False}
