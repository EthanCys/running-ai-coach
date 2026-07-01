"""COROS MCP HTTP client — thin wrapper over the JSON-RPC tools/call transport.

IMPORTANT: COROS MCP returns tool results as *formatted plain text*, not JSON
objects, except for queryActivityLapData which returns JSON. This module handles
both formats and normalises them into plain Python dicts/lists.

The Accept header MUST include "text/event-stream" or the server returns 400.
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

COROS_MCP_BASE = "https://mcpcn.coros.com/mcp"


class CorosMcpError(Exception):
    """Raised when a COROS MCP call fails."""


async def call_tool(
    name: str, arguments: dict[str, Any], access_token: str | None, request_id: int = 1
) -> str | dict | list:
    """Call a single COROS MCP tool. Returns the raw text or parsed JSON payload."""
    headers = {
        "Content-Type": "application/json",
        # COROS MCP server returns 400 without text/event-stream in Accept.
        "Accept": "application/json, text/event-stream",
    }
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

    body = resp.json()
    if body.get("error"):
        raise CorosMcpError(f"{name}: {body['error']}")

    result = body.get("result", {})
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise CorosMcpError(f"{name}: empty content")

    raw = content[0].get("text", "")
    # The text is a JSON-encoded string — unwrap it
    if raw.startswith('"'):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            pass

    # Try to parse as JSON (queryActivityLapData returns JSON)
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

    return raw  # plain text (querySportRecords, getActivityDetail)


# ── typed helpers ──────────────────────────────────────────────────────────────

async def query_sport_records(
    access_token: str | None,
    start_date: str,
    end_date: str,
    sport_type_codes: list[int] | None = None,
    limit: int = 20,
) -> list[dict]:
    """List workout records. Returns a list of normalised record dicts."""
    args: dict[str, Any] = {
        "startDate": start_date,
        "endDate": end_date,
        "limit": limit,
        "minDistanceKm": None,
        "maxDistanceKm": None,
        "minDurationMinutes": None,
        "maxDurationMinutes": None,
        "maxAveragePace": None,
        "locationKeyword": None,
        "timezone": "Asia/Shanghai",
    }
    if sport_type_codes:
        args["sportTypeCodes"] = sport_type_codes
    raw = await call_tool("querySportRecords", args, access_token)

    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("records", "list", "items", "dataList"):
            if isinstance(raw.get(key), list):
                return raw[key]

    # Parse the formatted text response
    if isinstance(raw, str):
        return _parse_sport_records_text(raw)
    return []


async def get_activity_detail(
    access_token: str | None, label_id: str, sport_type: int
) -> dict:
    """Fetch activity detail and parse the formatted text into a dict."""
    raw = await call_tool(
        "getActivityDetail", {"labelId": label_id, "sportType": sport_type}, access_token
    )
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return _parse_activity_detail_text(raw, label_id, sport_type)
    return {}


async def query_activity_lap_data(
    access_token: str | None, label_id: str, sport_type: int
) -> list[dict]:
    """Fetch lap data. Returns a list of lap dicts."""
    try:
        raw = await call_tool(
            "queryActivityLapData", {"labelId": label_id, "sportType": sport_type}, access_token
        )
    except CorosMcpError:
        return []

    # queryActivityLapData returns JSON with columns + dataList
    if isinstance(raw, dict):
        columns = [c.get("name") for c in raw.get("columns", [])]
        rows = raw.get("dataList", [])
        if columns and rows:
            return [dict(zip(columns, row)) for row in rows]
        for key in ("laps", "list", "items"):
            if isinstance(raw.get(key), list):
                return raw[key]

    if isinstance(raw, list):
        return raw
    return []


# ── text parsers ───────────────────────────────────────────────────────────────

def _parse_sport_records_text(text: str) -> list[dict]:
    """Parse the querySportRecords formatted text into a list of record dicts.

    Example block:
        1. Outdoor Run — 2026-07-01
           Location: Threshold 6k
           Time Window: startTimestamp=1782864878 | endTimestamp=1782867015
           Duration: 35:37 | Distance: 7.77 km
           Average Pace: 4:35 /km | Avg HR: 152 bpm | Calories: 525 kcal
           LabelId: 478584446935662696 | SportType: 100
    """
    records = []
    # Split on numbered entries
    blocks = re.split(r"\n(?=\d+\.\s)", text.strip())
    for block in blocks:
        if not block.strip():
            continue
        r: dict[str, Any] = {}

        # LabelId and SportType (required for further calls)
        m = re.search(r"LabelId:\s*(\d+)", block)
        if m:
            r["labelId"] = m.group(1)
        m = re.search(r"SportType:\s*(\d+)", block)
        if m:
            r["sportType"] = int(m.group(1))

        # Title line: "1. Outdoor Run — 2026-07-01"
        m = re.match(r"\d+\.\s+(.+?)\s+[—–-]+\s+(\d{4}-\d{2}-\d{2})", block)
        if m:
            r["sportName"] = m.group(1).strip()
            r["date"] = m.group(2)

        m = re.search(r"Location:\s*(.+)", block)
        if m:
            r["location"] = m.group(1).strip()

        m = re.search(r"startTimestamp=(\d+)", block)
        if m:
            r["startTimestamp"] = int(m.group(1))
        m = re.search(r"endTimestamp=(\d+)", block)
        if m:
            r["endTimestamp"] = int(m.group(1))

        # Duration: "35:37" or "1:47:59"
        m = re.search(r"Duration:\s*([\d:]+)", block)
        if m:
            r["totalTime"] = _parse_duration_to_sec(m.group(1))

        # Distance: "7.77 km"
        m = re.search(r"Distance:\s*([\d.]+)\s*km", block)
        if m:
            r["totalDistance"] = int(float(m.group(1)) * 1000)

        # Average Pace: "4:35 /km"
        m = re.search(r"Average Pace:\s*([\d:]+)\s*/km", block)
        if m:
            r["avgPace"] = _parse_pace_to_sec(m.group(1))

        # Avg HR
        m = re.search(r"Avg HR:\s*(\d+)\s*bpm", block)
        if m:
            r["avgHeartRate"] = int(m.group(1))

        # Calories
        m = re.search(r"Calories:\s*(\d+)", block)
        if m:
            r["calories"] = int(m.group(1))

        if r.get("labelId"):
            records.append(r)

    return records


def _parse_activity_detail_text(text: str, label_id: str, sport_type: int) -> dict:
    """Parse the getActivityDetail formatted text into a dict."""
    d: dict[str, Any] = {"labelId": label_id, "sportType": sport_type}

    def get(pattern: str) -> str | None:
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    raw_dur = get(r"Workout Time:\s*([\d:]+)")
    if raw_dur:
        d["totalTime"] = _parse_duration_to_sec(raw_dur)

    dist = get(r"Distance:\s*([\d.]+)\s*km")
    if dist:
        d["totalDistance"] = int(float(dist) * 1000)

    pace = get(r"Average Pace:\s*([\d:]+)\s*/km")
    if pace:
        d["avgPace"] = _parse_pace_to_sec(pace)

    hr = get(r"Average Heart Rate:\s*(\d+)")
    if hr:
        d["avgHeartRate"] = int(hr)

    cadence = get(r"Average Cadence:\s*(\d+)")
    if cadence:
        d["avgCadence"] = int(cadence)

    stride = get(r"Average Stride Length:\s*([\d.]+)")
    if stride:
        d["avgStepLength"] = float(stride)  # metres

    calories = get(r"Calories:\s*(\d+)")
    if calories:
        d["calories"] = int(calories)

    load = get(r"Training Load:\s*(\d+)")
    if load:
        d["trainingLoad"] = int(load)

    return d


# ── unit conversion helpers ────────────────────────────────────────────────────

def _parse_duration_to_sec(s: str) -> float:
    """'35:37' → 2137.0   '1:47:59' → 6479.0"""
    parts = s.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return float(parts[0])
    except ValueError:
        return 0.0


def _parse_pace_to_sec(s: str) -> float:
    """'4:35' → 275.0  (seconds per km)"""
    parts = s.strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        return float(parts[0]) * 60
    except ValueError:
        return 0.0
