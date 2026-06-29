"""Map COROS MCP API responses to ParsedFitActivity.

COROS MCP returns data through tools like getActivityDetail, querySportRecords,
queryRecoveryStatus, etc. This adapter normalises those responses into the same
ParsedFitActivity / ParsedFitMetrics dataclasses used by the FIT parser so that
the rest of the pipeline (analysis_engine, report_builder, coach_commentary)
needs zero changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.services.fit_parser import (
    ParsedFitActivity,
    ParsedFitLap,
    ParsedFitMetrics,
    ParsedFitSegment,
)


@dataclass
class CorosContext:
    """Extra COROS-specific signals not present in a bare FIT file."""
    recovery_pct: int | None = None          # queryRecoveryStatus
    sleep_hrv: float | None = None           # querySleepHrv
    resting_hr_bpm: int | None = None        # queryRestingHeartRate
    training_load_atl: float | None = None   # queryTrainingLoadAssessment
    training_load_ctl: float | None = None
    hrv_drop_pct: float | None = None        # vs 7-day baseline, for Level 1 check
    rhr_spike_bpm: float | None = None       # vs baseline, for Level 1 check


def build_parsed_activity(
    detail: dict[str, Any],
    lap_data: list[dict[str, Any]] | None = None,
    context: CorosContext | None = None,
) -> tuple[ParsedFitActivity, CorosContext]:
    """Convert a COROS getActivityDetail response into ParsedFitActivity.

    Args:
        detail:   Raw dict from getActivityDetail MCP tool.
        lap_data: Optional list of lap dicts from queryActivityLapData.
        context:  Pre-populated CorosContext (recovery, HRV, etc.) from caller.

    Returns:
        (ParsedFitActivity, CorosContext) — the second element passes extra
        signals through to coach_commentary for Level 1/2/3 logic.
    """
    ctx = context or CorosContext()

    # ── top-level summary ────────────────────────────────────────────────────
    sport_type = detail.get("sportType")
    sport = _map_sport_type(sport_type)
    start_ts = detail.get("startTimestamp") or detail.get("startTime")
    start_time = _parse_ts(start_ts)

    total_distance_m = _safe_float(detail.get("totalDistance") or detail.get("distance"))
    total_timer_time_sec = _safe_float(detail.get("totalTime") or detail.get("duration"))
    total_calories = _safe_int(detail.get("totalCalories") or detail.get("calories"))

    # ── metrics ──────────────────────────────────────────────────────────────
    avg_pace_raw = detail.get("avgPace")  # COROS returns sec/km
    avg_pace = _safe_float(avg_pace_raw)

    avg_hr = _safe_float(detail.get("avgHeartRate") or detail.get("avgHr"))
    max_hr = _safe_int(detail.get("maxHeartRate") or detail.get("maxHr"))
    avg_cadence = _safe_float(detail.get("avgCadence") or detail.get("avgRunCadence"))
    # COROS cadence is steps/min for running
    if avg_cadence and avg_cadence < 100:
        avg_cadence = avg_cadence * 2  # convert from strides/min to steps/min

    avg_step_length = _safe_float(detail.get("avgStepLength"))
    if avg_step_length and avg_step_length > 10:
        avg_step_length = avg_step_length / 100.0  # cm → m

    avg_stance_time = _safe_float(detail.get("avgGroundContactTime") or detail.get("avgStanceTime"))

    # HR drift: COROS may provide aerobicDecoupling or we compute from laps
    hr_drift_pct = _safe_float(detail.get("aerobicDecoupling") or detail.get("hrDrift"))
    if hr_drift_pct is None and lap_data:
        hr_drift_pct = _estimate_hr_drift_from_laps(lap_data)

    # pace fade: compare first vs second half laps
    pace_fade_pct = _safe_float(detail.get("paceFade"))
    if pace_fade_pct is None and lap_data:
        pace_fade_pct = _estimate_pace_fade_from_laps(lap_data)

    # pace stability: COROS doesn't expose this directly — estimate from laps
    pace_stability = _safe_float(detail.get("paceStability"))
    if pace_stability is None and lap_data:
        pace_stability = _estimate_pace_stability(lap_data, avg_pace)

    metrics = ParsedFitMetrics(
        avg_pace_sec_per_km=avg_pace,
        pace_stability_score=pace_stability,
        avg_heart_rate_bpm=avg_hr,
        max_heart_rate_bpm=max_hr,
        avg_running_cadence_spm=avg_cadence,
        pace_fade_pct=pace_fade_pct,
        hr_drift_pct=hr_drift_pct,
        avg_step_length_m=avg_step_length,
        avg_stance_time_ms=avg_stance_time,
        hr_outlier_count=0,
        interval_count=_safe_int(detail.get("intervalCount")) or 0,
        recovery_count=0,
        rest_count=0,
    )

    # ── laps ─────────────────────────────────────────────────────────────────
    laps = _build_laps(lap_data or [])

    # ── segments ─────────────────────────────────────────────────────────────
    segments = _build_segments(lap_data or [], laps)
    metrics.interval_count = sum(1 for s in segments if s.segment_type in {"interval", "work"})
    metrics.recovery_count = sum(1 for s in segments if s.segment_type == "recovery")
    metrics.rest_count = sum(1 for s in segments if s.segment_type == "rest")

    activity = ParsedFitActivity(
        manufacturer="COROS",
        product_name=detail.get("deviceName") or detail.get("deviceType"),
        sport=sport,
        sub_sport=None,
        start_time=start_time,
        total_elapsed_time_sec=total_timer_time_sec,
        total_timer_time_sec=total_timer_time_sec,
        total_distance_m=total_distance_m,
        total_calories=total_calories,
        lap_count=len(laps),
        record_count=0,
        laps=laps,
        segments=segments,
        metrics=metrics,
    )

    return activity, ctx


# ── private helpers ───────────────────────────────────────────────────────────

def _map_sport_type(sport_type: Any) -> str:
    """Map COROS sportType code to a readable string."""
    mapping = {
        100: "running", 101: "indoor_running", 102: "trail_running",
        103: "track_running", 104: "hiking", 200: "cycling",
        300: "pool_swim", 301: "open_water_swim", 400: "gym_cardio",
        402: "strength",
    }
    if isinstance(sport_type, int):
        return mapping.get(sport_type, f"sport_{sport_type}")
    return str(sport_type) if sport_type else "unknown"


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value)
        except (OSError, OverflowError):
            return None
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def _safe_float(v: Any) -> float | None:
    try:
        f = float(v)
        return f if f == f else None  # reject NaN
    except (TypeError, ValueError):
        return None


def _safe_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _build_laps(lap_data: list[dict]) -> list[ParsedFitLap]:
    laps = []
    for i, lap in enumerate(lap_data):
        distance = _safe_float(lap.get("distance") or lap.get("totalDistance"))
        duration = _safe_float(lap.get("duration") or lap.get("totalTime"))
        avg_pace = _safe_float(lap.get("avgPace"))
        avg_speed = (1000.0 / avg_pace) if avg_pace and avg_pace > 0 else None

        laps.append(ParsedFitLap(
            lap_index=i,
            start_time=None,
            end_time=None,
            total_elapsed_time_sec=duration,
            total_timer_time_sec=duration,
            total_distance_m=distance,
            total_calories=_safe_int(lap.get("calories")),
            avg_speed_mps=avg_speed,
            avg_heart_rate_bpm=_safe_int(lap.get("avgHeartRate") or lap.get("avgHr")),
            max_heart_rate_bpm=_safe_int(lap.get("maxHeartRate") or lap.get("maxHr")),
            avg_running_cadence_spm=_safe_int(lap.get("avgCadence")),
        ))
    return laps


def _build_segments(lap_data: list[dict], laps: list[ParsedFitLap]) -> list[ParsedFitSegment]:
    """Classify laps into segment types based on pace/HR signals."""
    if not laps:
        return []

    valid_paces = [
        laps[i].avg_speed_mps
        for i in range(len(laps))
        if laps[i].avg_speed_mps is not None
    ]
    if not valid_paces:
        return []

    median_speed = sorted(valid_paces)[len(valid_paces) // 2]
    WORK_THRESHOLD = median_speed * 1.08  # 8% faster than median → work segment

    offset = 0.0
    segments = []
    for i, lap in enumerate(laps):
        duration = lap.total_timer_time_sec or 0
        speed = lap.avg_speed_mps
        avg_pace = (1000.0 / speed) if speed and speed > 0 else None

        if speed and speed >= WORK_THRESHOLD and (lap.total_distance_m or 0) >= 300:
            seg_type = "interval"
        elif speed and speed < median_speed * 0.92:
            seg_type = "recovery"
        elif i == 0 and len(laps) > 2:
            seg_type = "warmup"
        elif i == len(laps) - 1 and len(laps) > 2:
            seg_type = "cooldown"
        else:
            seg_type = "steady_run"

        segments.append(ParsedFitSegment(
            segment_type=seg_type,
            start_offset_sec=offset,
            end_offset_sec=offset + duration,
            duration_sec=duration,
            distance_m=lap.total_distance_m,
            avg_pace_sec_per_km=avg_pace,
            avg_heart_rate_bpm=float(lap.avg_heart_rate_bpm) if lap.avg_heart_rate_bpm else None,
        ))
        offset += duration

    return segments


def _estimate_hr_drift_from_laps(lap_data: list[dict]) -> float | None:
    """Estimate HR drift by comparing first half vs second half avg HR."""
    hrs = [_safe_float(lap.get("avgHeartRate") or lap.get("avgHr")) for lap in lap_data]
    hrs = [h for h in hrs if h is not None]
    if len(hrs) < 4:
        return None
    mid = len(hrs) // 2
    first_avg = sum(hrs[:mid]) / mid
    second_avg = sum(hrs[mid:]) / (len(hrs) - mid)
    if first_avg <= 0:
        return None
    return round((second_avg - first_avg) / first_avg * 100, 2)


def _estimate_pace_fade_from_laps(lap_data: list[dict]) -> float | None:
    """Estimate pace fade: positive = slowing down second half."""
    paces = [_safe_float(lap.get("avgPace")) for lap in lap_data]
    paces = [p for p in paces if p is not None and p > 0]
    if len(paces) < 4:
        return None
    mid = len(paces) // 2
    first_avg = sum(paces[:mid]) / mid
    second_avg = sum(paces[mid:]) / (len(paces) - mid)
    if first_avg <= 0:
        return None
    return round((second_avg - first_avg) / first_avg * 100, 2)


def _estimate_pace_stability(lap_data: list[dict], avg_pace: float | None) -> float | None:
    """Score 0-1: how consistent lap paces are relative to average."""
    if not avg_pace or avg_pace <= 0:
        return None
    paces = [_safe_float(lap.get("avgPace")) for lap in lap_data]
    paces = [p for p in paces if p is not None and p > 0]
    if len(paces) < 2:
        return None
    from statistics import pstdev
    std = pstdev(paces)
    cv = std / avg_pace  # coefficient of variation
    return round(max(0.0, min(1.0, 1.0 - cv * 5)), 3)
