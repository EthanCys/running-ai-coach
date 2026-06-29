# ADR 0006: Standalone web app does its own COROS OAuth (DCR + PKCE)

**Status:** Accepted
**Date:** 2026-06-29

## Context

The sibling `ai-running-coach` project has **no auth page**. It runs inside an
MCP *host* (Claude Desktop / Claude Code): the user types `/mcp`, installs the
COROS MCP, and the host performs the OAuth browser handshake automatically
(USER_GUIDE.md step 5 — "a browser login page pops up"). The COROS server hosts
that login page; the project writes zero auth code.

Running AI Coach is a **standalone web app**, not an MCP host. It therefore gets
no automatic OAuth and must act as its own OAuth client.

We probed the COROS MCP server and confirmed it is a standard OAuth 2.0
protected resource:

- `GET /.well-known/oauth-authorization-server` exposes the endpoints.
- Supports **Dynamic Client Registration** at `/connect/register` — no
  pre-provisioned client_id needed.
- Requires **PKCE (S256)** and supports **public clients** (`auth_method: none`).
- Scopes: `openid mcp.tools offline_access` (the last gives refresh tokens).

## Decision

Implement the OAuth `authorization_code` + PKCE flow in the backend:

- `services/coros_oauth.py` — DCR (cached client_id), PKCE generation, authorize
  URL building, code→token exchange, refresh.
- `api/routes/auth.py` — `/auth/coros/login` (302 → COROS), `/auth/coros/callback`
  (token exchange → session), `/status`, `/logout`.
- The frontend has a **"连接高驰" button** that hits `/login`; after consent the
  callback bounces back to the SPA with `?coros=connected&session=<id>`, which
  the SPA stores in `localStorage` and sends as `X-Coros-Session` on `/analyze`.

## Consequences

**Good**
- Real, self-contained "first-time authorize" UX — the missing piece vs the
  Claude-hosted reference flow.
- DCR means no manual client registration / no secret to manage (public client).
- `offline_access` → refresh tokens → sessions survive access-token expiry.

**Bad / cost**
- Token storage is an **in-memory dict** in `auth.py` for the MVP. Restarting the
  server drops sessions. Real persistence (encrypted refresh tokens per user) is
  specified in [PERSISTENCE-DESIGN.md](../PERSISTENCE-DESIGN.md) §2–3.
- Session is passed via `localStorage` + header rather than a cookie, to avoid
  cross-site cookie issues between `localhost:3000` and `127.0.0.1:8010` on http.

**Risks**
- In-memory sessions are not safe for multi-instance deployment. Mitigation:
  move to the persistent store before any real multi-user use.
- Tokens in `localStorage` are readable by JS (XSS surface). Acceptable for an
  MVP demo; production should use a secure, same-site cookie over HTTPS or a
  backend session store keyed by an httpOnly cookie.
