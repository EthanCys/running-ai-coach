"""COROS MCP HTTP client — thin wrapper over the JSON-RPC tools/call transport.

Centralises every COROS MCP call so routes and the chat orchestrator share one
implementation. Each method returns the already-unwrapped payload (the COROS
`data` field), or raises CorosMcpError.
"""
from __future__ import annotations

import json
from typing import Any

import httpx

COROS_MCP_BASE = "https://mcpcn.coros.com/mcp"


class CorosMcpError(Exception):
    """Raised when a COROS MCP call fails."""


async def call_tool(
    name: str, arguments: dict[str, Any], access_token: str | None, request_id: int = 1
) -> Any:
    """Call a single COROS MCP tool and return its unwrapped payload."""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            COROS_MCP_BASE,
            json={
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            headers=headers,
        )
    if resp.status_code == 401:
        raise CorosMcpError("unauthorized")
    if resp.status_code != 200:
        raise CorosMcpError(f"{name} failed: HTTP {resp.status_code}")
    return _unwrap(resp.json(), name)


def _unwrap(body: dict, tool_name: str) -> Any:
    if body.get("error"):
        raise CorosMcpError(f"{tool_name}: {body['error']}")
    result = body.get("result", {})
    content = result.get("content")
    if isinstance(content, list) and content:
        text = content[0].get("text", "")
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {}
        if isinstance(parsed, dict) and "data" in parsed:
            return parsed["data"]
        return parsed
    return result


# ── typed helpers ──────────────────────────────────────────────────────────────

async def query_sport_records(
    access_token: str | None,
    start_date: str,
    end_date: str,
    sport_type_codes: list[int] | None = None,
    limit: int = 20,
) -> list[dict]:
    """List workout records. Dates are yyyyMMdd. Returns a list of record dicts."""
    args: dict[str, Any] = {
        "startDate": start_date,
        "endDate": end_date,
        "limit": limit,
    }
    if sport_type_codes:
        args["sportTypeCodes"] = sport_type_codes
    data = await call_tool("querySportRecords", args, access_token)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("records", "list", "items", "dataList"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


async def get_activity_detail(
    access_token: str | None, label_id: str, sport_type: int
) -> dict:
    data = await call_tool(
        "getActivityDetail", {"labelId": label_id, "sportType": sport_type}, access_token
    )
    return data if isinstance(data, dict) else {}


async def query_activity_lap_data(
    access_token: str | None, label_id: str, sport_type: int
) -> list[dict]:
    try:
        data = await call_tool(
            "queryActivityLapData", {"labelId": label_id, "sportType": sport_type}, access_token
        )
    except CorosMcpError:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("laps", "list", "items", "dataList"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data] if data else []
    return []
