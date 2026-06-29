"""COROS MCP OAuth 2.0 client (Dynamic Client Registration + PKCE).

The COROS MCP server (https://mcpcn.coros.com/mcp) is an OAuth 2.0 protected
resource. Unlike the SKILL.md / Claude Desktop flow — where the MCP *host*
performs the browser OAuth handshake automatically — a standalone web app must
act as its own OAuth client.

Discovered metadata (GET /.well-known/oauth-authorization-server):
  authorization_endpoint : https://mcpcn.coros.com/oauth2/authorize
  token_endpoint         : https://mcpcn.coros.com/oauth2/token
  registration_endpoint  : https://mcpcn.coros.com/connect/register   (DCR)
  code_challenge_methods : ["S256"]                                   (PKCE)
  scopes_supported       : ["openid", "mcp.tools", "offline_access"]
  token auth methods     : includes "none"  → public client, no secret

Flow implemented here:
  1. register_client()      — DCR, returns a public client_id (cached on disk).
  2. build_authorize_url()  — PKCE S256, returns (url, code_verifier, state).
  3. exchange_code()        — authorization_code → access_token + refresh_token.
  4. refresh_access_token() — refresh_token → new access_token.

Token *storage* is intentionally out of scope here; see auth route + the
persistence design doc. This module only speaks the OAuth protocol.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlencode

import httpx

# ── discovered endpoints (could be fetched dynamically; pinned for clarity) ────
ISSUER = "https://mcpcn.coros.com"
AUTHORIZE_ENDPOINT = f"{ISSUER}/oauth2/authorize"
TOKEN_ENDPOINT = f"{ISSUER}/oauth2/token"
REGISTRATION_ENDPOINT = f"{ISSUER}/connect/register"
SCOPES = "openid mcp.tools offline_access"

_CLIENT_CACHE = Path(__file__).resolve().parents[2] / "data" / "coros_client.json"


class CorosOAuthError(Exception):
    """Raised when an OAuth step fails."""


# ── 1. Dynamic Client Registration ────────────────────────────────────────────

def register_client(redirect_uri: str, client_name: str = "Running AI Coach") -> str:
    """Register (or reuse a cached) public OAuth client. Returns client_id.

    The client_id is cached on disk keyed by redirect_uri so we don't register a
    fresh client on every server start.
    """
    cached = _load_cached_client(redirect_uri)
    if cached:
        return cached

    payload = {
        "client_name": client_name,
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "scope": SCOPES,
        "token_endpoint_auth_method": "none",
    }
    try:
        resp = httpx.post(REGISTRATION_ENDPOINT, json=payload, timeout=20)
    except httpx.HTTPError as exc:
        raise CorosOAuthError(f"DCR request failed: {exc}") from exc
    if resp.status_code not in (200, 201):
        raise CorosOAuthError(f"DCR failed: {resp.status_code} {resp.text}")

    client_id = resp.json().get("client_id")
    if not client_id:
        raise CorosOAuthError("DCR response missing client_id")

    _save_cached_client(redirect_uri, client_id)
    return client_id


# ── 2. Authorization URL (PKCE S256) ──────────────────────────────────────────

def build_authorize_url(client_id: str, redirect_uri: str) -> tuple[str, str, str]:
    """Build the COROS authorize URL. Returns (url, code_verifier, state).

    Caller must persist code_verifier + state until the callback to complete the
    PKCE exchange.
    """
    code_verifier = _gen_code_verifier()
    code_challenge = _code_challenge_s256(code_verifier)
    state = secrets.token_urlsafe(24)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    url = f"{AUTHORIZE_ENDPOINT}?{urlencode(params)}"
    return url, code_verifier, state


# ── 3. Token exchange ─────────────────────────────────────────────────────────

def exchange_code(
    client_id: str, redirect_uri: str, code: str, code_verifier: str
) -> dict:
    """Exchange an authorization code for tokens. Returns the token response dict
    (access_token, refresh_token, expires_in, ...)."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    return _token_request(data)


def refresh_access_token(client_id: str, refresh_token: str) -> dict:
    """Use a refresh_token to obtain a new access_token."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    return _token_request(data)


def _token_request(data: dict) -> dict:
    try:
        resp = httpx.post(
            TOKEN_ENDPOINT,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
    except httpx.HTTPError as exc:
        raise CorosOAuthError(f"token request failed: {exc}") from exc
    if resp.status_code != 200:
        raise CorosOAuthError(f"token endpoint error: {resp.status_code} {resp.text}")
    token = resp.json()
    if "access_token" not in token:
        raise CorosOAuthError(f"token response missing access_token: {token}")
    return token


# ── PKCE helpers ───────────────────────────────────────────────────────────────

def _gen_code_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode("ascii")


def _code_challenge_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ── client_id disk cache ───────────────────────────────────────────────────────

def _load_cached_client(redirect_uri: str) -> str | None:
    if not _CLIENT_CACHE.exists():
        return None
    try:
        data = json.loads(_CLIENT_CACHE.read_text())
        return data.get(redirect_uri)
    except (json.JSONDecodeError, OSError):
        return None


def _save_cached_client(redirect_uri: str, client_id: str) -> None:
    data = {}
    if _CLIENT_CACHE.exists():
        try:
            data = json.loads(_CLIENT_CACHE.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    data[redirect_uri] = client_id
    _CLIENT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CLIENT_CACHE.write_text(json.dumps(data, indent=2))
