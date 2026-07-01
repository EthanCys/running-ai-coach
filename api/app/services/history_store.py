"""Lightweight training history store (addresses Known gap #1: no persistence).

Appends one compact record per analyzed activity to a JSONL file, and reads
back recent same-type sessions so the LLM can make longitudinal comparisons
(e.g. "触地从上次 205ms 降到今天 198ms").

Design notes:
- JSONL (one JSON object per line) keeps appends atomic and cheap; no DB needed.
- Keyed by a caller-supplied user id (defaults to "default" for single-user).
- Dedupe by activity_id so re-analyzing the same activity does not double-count.
- Pure file I/O isolated here; services stay stateless per ADR 0001.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_HISTORY_DIR = Path(__file__).resolve().parents[2] / "data" / "history"


def _history_path(user_id: str) -> Path:
    safe = "".join(c for c in user_id if c.isalnum() or c in ("-", "_")) or "default"
    return _HISTORY_DIR / f"{safe}.jsonl"


def record_activity(
    *,
    user_id: str,
    activity_id: str,
    training_type: str,
    date: str | None,
    metrics: dict,
) -> None:
    """Append one activity summary. Silently no-ops on I/O errors so a history
    write can never break the analysis response."""
    entry = {
        "activity_id": str(activity_id),
        "date": date or datetime.now().strftime("%Y-%m-%d"),
        "training_type": training_type,
        **metrics,
    }
    try:
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        path = _history_path(user_id)
        # Dedupe: skip if this activity_id is already recorded.
        existing_ids = {e.get("activity_id") for e in _read_all(path)}
        if entry["activity_id"] in existing_ids:
            return
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        return


def recent_same_type(
    *,
    user_id: str,
    training_type: str,
    exclude_activity_id: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Return up to `limit` most-recent prior sessions of the same training type,
    newest first, for longitudinal comparison."""
    path = _history_path(user_id)
    entries = _read_all(path)
    matched = [
        e for e in entries
        if e.get("training_type") == training_type
        and (exclude_activity_id is None or e.get("activity_id") != str(exclude_activity_id))
    ]
    # entries are appended chronologically; newest last -> reverse for newest-first
    matched.reverse()
    return matched[:limit]


def _read_all(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out
