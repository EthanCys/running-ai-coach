"""Chat orchestrator — turns a natural-language message into MCP calls + analysis.

This is the "agent" layer: it understands intent, orchestrates COROS MCP tools
(querySportRecords → getActivityDetail → queryActivityLapData), runs the
deterministic analysis pipeline, and returns a text reply plus an optional
structured report card to embed in the chat bubble.

Principle unchanged (ADR 0001): the rule layer computes facts; the LLM only
phrases them. Intent detection here is deterministic keyword routing so the
agent's behaviour is predictable.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.services import coros_client
from app.services.coros_adapter import build_parsed_activity, CorosContext
from app.services.analysis_engine import build_activity_analysis
from app.services.report_builder import build_activity_report
from app.services.coach_commentary import build_coach_commentary
from app.services import history_store

RUNNING_CODES = [100, 101, 102, 103]

# preset entry actions surfaced in the UI
PRESETS = [
    {"id": "analyze_latest", "label": "分析我最近一次跑步"},
    {"id": "list_recent", "label": "看看我最近的训练"},
    {"id": "review_week", "label": "复盘这周训练"},
]


def detect_intent(message: str) -> str:
    m = message.strip().lower()
    # explicit preset ids
    if m in {p["id"] for p in PRESETS}:
        return m
    has = lambda *ks: any(k in message for k in ks)
    if has("复盘", "这周", "本周", "一周", "review_week"):
        return "review_week"
    if has("最近的训练", "最近跑", "哪些", "列表", "记录", "几次", "list_recent"):
        return "list_recent"
    if has("分析", "这次", "今天", "上次", "最近一次", "怎么样", "表现", "复盘"):
        return "analyze_latest"
    return "general"


async def handle_chat(message: str, access_token: str | None) -> dict:
    """Return {reply, intent, report_card?, records?}."""
    intent = detect_intent(message)

    if intent in ("analyze_latest", "review_week"):
        return await _analyze_latest(access_token, intent)
    if intent == "list_recent":
        return await _list_recent(access_token)
    return _general_reply(message)


# ── intent handlers ────────────────────────────────────────────────────────────

async def _analyze_latest(access_token: str | None, intent: str) -> dict:
    if not access_token:
        return {"intent": intent, "reply": "请先连接你的高驰账号，我才能读取你的训练数据。"}

    start, end = _date_range(days=14)
    try:
        records = await coros_client.query_sport_records(
            access_token, start, end, RUNNING_CODES, limit=20
        )
    except coros_client.CorosMcpError as exc:
        return {"intent": intent, "reply": _mcp_error_text(exc)}

    if not records:
        return {"intent": intent, "reply": "最近两周我没有找到你的跑步记录。先去跑一次，或换个时间范围试试？"}

    latest = records[0]
    label_id = _field(latest, "labelId", "label_id", "id")
    sport_type = _field(latest, "sportType", "sport_type") or 100
    if not label_id:
        return {"intent": intent, "reply": "读取到的活动缺少标识，暂时无法分析这一次。"}

    try:
        detail = await coros_client.get_activity_detail(access_token, str(label_id), int(sport_type))
        laps = await coros_client.query_activity_lap_data(access_token, str(label_id), int(sport_type))
    except coros_client.CorosMcpError as exc:
        return {"intent": intent, "reply": _mcp_error_text(exc)}

    parsed, ctx = build_parsed_activity(detail, laps, CorosContext())
    analysis = build_activity_analysis(parsed)
    report = build_activity_report(parsed, analysis)

    # Longitudinal history: read prior same-type sessions, then record this one.
    training_type = analysis.get("training_type", "unknown")
    history = history_store.recent_same_type(
        user_id="default",
        training_type=training_type,
        exclude_activity_id=str(label_id),
        limit=5,
    )
    commentary = build_coach_commentary(parsed, analysis, report, ctx, history)

    history_store.record_activity(
        user_id="default",
        activity_id=str(label_id),
        training_type=training_type,
        date=str(_field(latest, "date", "startDate", "startTime") or ""),
        metrics={
            "avg_pace_sec": parsed.metrics.avg_pace_sec_per_km,
            "avg_hr_bpm": parsed.metrics.avg_heart_rate_bpm,
            "hr_drift_pct": parsed.metrics.hr_drift_pct,
            "stance_ms": parsed.metrics.avg_stance_time_ms,
            "ef_ratio": analysis.get("ef_ratio"),
        },
    )

    reply = commentary["summary"]
    card = _build_report_card(parsed, analysis, report, commentary, label_id, int(sport_type))
    return {"intent": intent, "reply": reply, "report_card": card}


async def _list_recent(access_token: str | None) -> dict:
    if not access_token:
        return {"intent": "list_recent", "reply": "请先连接你的高驰账号，我才能看到你的训练。"}
    start, end = _date_range(days=14)
    try:
        records = await coros_client.query_sport_records(
            access_token, start, end, RUNNING_CODES, limit=10
        )
    except coros_client.CorosMcpError as exc:
        return {"intent": "list_recent", "reply": _mcp_error_text(exc)}

    if not records:
        return {"intent": "list_recent", "reply": "最近两周没有找到跑步记录。"}

    brief = []
    for r in records[:8]:
        brief.append({
            "label_id": str(_field(r, "labelId", "label_id", "id") or ""),
            "sport_type": int(_field(r, "sportType", "sport_type") or 100),
            "date": str(_field(r, "date", "startDate", "startTime") or ""),
            "distance_m": _num(_field(r, "totalDistance", "distance")),
            "duration_sec": _num(_field(r, "totalTime", "duration")),
            "avg_pace_sec_per_km": _num(_field(r, "avgPace")),
        })
    reply = f"最近两周你跑了 {len(records)} 次。点任意一条我可以帮你深入分析。"
    return {"intent": "list_recent", "reply": reply, "records": brief}


def _general_reply(message: str) -> dict:
    return {
        "intent": "general",
        "reply": (
            "我是你的跑步 AI 教练。我可以分析你最近一次跑步、复盘本周训练，"
            "或解释训练里的概念。试试问我「分析我最近一次跑步」。"
        ),
    }


# ── helpers ────────────────────────────────────────────────────────────────────

def _build_report_card(parsed, analysis, report, commentary, label_id, sport_type) -> dict:
    return {
        "label_id": str(label_id),
        "sport_type": sport_type,
        "summary": {
            "sport": parsed.sport,
            "total_distance_m": parsed.total_distance_m,
            "total_timer_time_sec": parsed.total_timer_time_sec,
        },
        "metrics": {
            "avg_pace_sec_per_km": parsed.metrics.avg_pace_sec_per_km,
            "avg_heart_rate_bpm": parsed.metrics.avg_heart_rate_bpm,
            "hr_drift_pct": parsed.metrics.hr_drift_pct,
            "pace_stability_score": parsed.metrics.pace_stability_score,
        },
        "analysis": analysis,
        "coach_commentary": {
            "source": commentary["source"],
            "model": commentary["model"],
            "summary": commentary["summary"],
            "key_findings": commentary.get("key_findings", []),
            "strengths": commentary["strengths"],
            "watchouts": commentary["watchouts"],
            "next_steps": commentary["next_steps"],
        },
        "report": {
            "verdict": report["verdict"],
            "recommendation": report["recommendation"],
            "risks": report["risks"],
        },
    }


def _date_range(days: int) -> tuple[str, str]:
    today = datetime.now()
    start = today - timedelta(days=days)
    return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")


def _field(d: dict, *keys: str) -> Any:
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return None


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _mcp_error_text(exc: coros_client.CorosMcpError) -> str:
    if "unauthorized" in str(exc).lower():
        return "高驰授权已过期，请重新连接高驰账号。"
    return "读取高驰数据时出错了，请稍后再试。"
