from __future__ import annotations

from app.services.fit_parser import ParsedFitActivity


WORK_SEGMENT_SPEED_THRESHOLD_MPS = 3.70
WORK_SEGMENT_DISTANCE_THRESHOLD_M = 500
SHORT_INTERVAL_DISTANCE_THRESHOLD_M = 300


def build_activity_analysis(activity: ParsedFitActivity) -> dict:
    training_type = _classify_training_type(activity)
    ef_ratio = _compute_ef_ratio(activity)
    recovery_quality, recovery_hr_drop_bpm = _compute_recovery_quality(activity)
    fatigue_risk_level = _compute_fatigue_risk_level(activity)
    mechanics_stability_score = _compute_mechanics_stability_score(activity)
    intensity_level = _compute_intensity_level(activity)

    return {
        "training_type": training_type,
        "intensity_level": intensity_level,
        "ef_ratio": ef_ratio,
        "hr_drift_pct": activity.metrics.hr_drift_pct,
        "recovery_quality": recovery_quality,
        "recovery_hr_drop_bpm": recovery_hr_drop_bpm,
        "fatigue_risk_level": fatigue_risk_level,
        "mechanics_stability_score": mechanics_stability_score,
    }


def _classify_training_type(activity: ParsedFitActivity) -> str:
    metrics = activity.metrics
    distance_m = activity.total_distance_m or 0
    avg_hr = metrics.avg_heart_rate_bpm or 0
    work_segments = _qualified_work_segments(activity)

    if len(work_segments) >= 2:
        return "interval_session"
    if distance_m >= 18000 and (metrics.hr_drift_pct or 0) < 6:
        return "long_aerobic"
    if distance_m <= 9000 and avg_hr <= 135 and metrics.interval_count == 0:
        return "recovery_run"
    if metrics.pace_fade_pct is not None and metrics.pace_fade_pct <= -1 and (metrics.pace_stability_score or 0) >= 0.75:
        return "progression_run"
    has_steady_run = any(s.segment_type == "steady_run" for s in activity.segments)
    if has_steady_run or (metrics.pace_stability_score or 0) >= 0.72:
        return "steady_aerobic"
    return "mixed_run"


def _compute_ef_ratio(activity: ParsedFitActivity) -> float | None:
    """Efficiency Factor: speed (m/s) / avg HR.  Meaningful only as a trend across
    comparable sessions — not a standalone quality score for a single run."""
    m = activity.metrics
    if m.avg_pace_sec_per_km and m.avg_heart_rate_bpm and m.avg_heart_rate_bpm > 0:
        return round((1000.0 / m.avg_pace_sec_per_km) / m.avg_heart_rate_bpm, 4)
    return None


def _compute_intensity_level(activity: ParsedFitActivity) -> str:
    """Classify session intensity without requiring the user's personal HRmax.

    Uses avg_hr / session_max_hr as a self-normalising proxy.  Since session
    max_hr is the ceiling the runner actually reached this run, the ratio
    reflects how close to their personal limit they were operating on average.

    Thresholds (empirically consistent across fitness levels):
      >= 0.88  → hard   (threshold / race effort, needs recovery before next hard day)
      >= 0.78  → moderate (tempo / steady-state, can repeat in 24-48 h)
      <  0.78  → easy   (aerobic base, can run again same day or next day)

    Interval sessions are always classified as hard regardless of the ratio,
    because the peak efforts drive adaptation even if the average looks moderate.
    """
    metrics = activity.metrics
    avg_hr = metrics.avg_heart_rate_bpm
    max_hr = metrics.max_heart_rate_bpm

    # Interval sessions are structurally hard.
    if metrics.interval_count >= 2:
        return "hard"

    if avg_hr is None or max_hr is None or max_hr <= 0:
        # Fall back to hr_drift as a proxy: high drift implies sub-threshold or above.
        hr_drift = metrics.hr_drift_pct or 0
        if hr_drift >= 8:
            return "hard"
        if hr_drift >= 4:
            return "moderate"
        return "easy"

    ratio = avg_hr / max_hr
    if ratio >= 0.88:
        return "hard"
    if ratio >= 0.78:
        return "moderate"
    return "easy"


def _compute_recovery_quality(activity: ParsedFitActivity) -> tuple[str, float | None]:
    work_segments = _qualified_work_segments(activity)
    interval_hr = [
        segment.avg_heart_rate_bpm
        for segment in work_segments
        if segment.avg_heart_rate_bpm is not None
    ]
    recovery_hr = [
        segment.avg_heart_rate_bpm
        for segment in activity.segments
        if segment.segment_type in {"recovery", "rest", "cooldown"}
        and segment.avg_heart_rate_bpm is not None
    ]
    if not interval_hr or not recovery_hr:
        return "unknown", None

    hr_drop = sum(interval_hr) / len(interval_hr) - (sum(recovery_hr) / len(recovery_hr))
    if hr_drop >= 18:
        return "good", round(hr_drop, 1)
    if hr_drop >= 10:
        return "moderate", round(hr_drop, 1)
    return "limited", round(hr_drop, 1)


def _compute_fatigue_risk_level(activity: ParsedFitActivity) -> str:
    """Score fatigue risk from within-session signals only.  Absolute HR is not a
    fatigue signal — it reflects training intensity, not accumulated tiredness.
    Instead we weight HR drift (cardiovascular decoupling) and pace fade (mechanical
    breakdown) as the two primary within-session fatigue proxies."""
    metrics = activity.metrics
    risk_points = 0

    # HR drift: primary signal for cardiovascular fatigue within the session.
    hr_drift = metrics.hr_drift_pct or 0
    if hr_drift >= 8:
        risk_points += 3
    elif hr_drift >= 5:
        risk_points += 2
    elif hr_drift >= 3:
        risk_points += 1

    # Pace fade: mechanical breakdown in the second half.
    pace_fade = metrics.pace_fade_pct or 0
    if pace_fade >= 4:
        risk_points += 3
    elif pace_fade >= 2:
        risk_points += 2
    elif pace_fade >= 1:
        risk_points += 1

    # High volume adds load even without the above signals.
    if (activity.total_distance_m or 0) >= 18000:
        risk_points += 1

    # Interval session with many hard efforts.
    if len(_qualified_work_segments(activity)) >= 5:
        risk_points += 1

    if risk_points >= 5:
        return "high"
    if risk_points >= 3:
        return "moderate"
    return "low"


def _compute_mechanics_stability_score(activity: ParsedFitActivity) -> float | None:
    """Mechanics stability score.

    Cadence ideal is pace-dependent (faster pace → higher natural cadence).
    Stance time = 0 is treated as missing data, not a valid measurement.
    """
    metrics = activity.metrics
    if metrics.pace_stability_score is None:
        return None

    # Pace-dependent cadence ideal: empirical linear fit across recreational runners.
    # At 6:00/km (360 s/km) → ~168 spm; at 4:00/km (240 s/km) → ~180 spm.
    cadence_score = 0.65  # default when no cadence data
    if metrics.avg_running_cadence_spm is not None:
        pace = metrics.avg_pace_sec_per_km or 300
        ideal_cadence = _clamp(192 - pace / 20.0, 160.0, 188.0)
        cadence_delta = abs(metrics.avg_running_cadence_spm - ideal_cadence)
        cadence_score = 1.0 - _clamp(cadence_delta / 20.0, 0.0, 1.0)

    step_length_score = 0.65
    if metrics.avg_step_length_m is not None:
        if 0.85 <= metrics.avg_step_length_m <= 1.45:
            step_length_score = 1.0
        elif 0.75 <= metrics.avg_step_length_m <= 1.6:
            step_length_score = 0.78
        else:
            step_length_score = 0.55

    # stance_time == 0 means the device did not record it — treat as missing.
    stance_score: float | None = None
    if metrics.avg_stance_time_ms is not None and metrics.avg_stance_time_ms > 0:
        if 180 <= metrics.avg_stance_time_ms <= 290:
            stance_score = 1.0
        elif 160 <= metrics.avg_stance_time_ms <= 320:
            stance_score = 0.8
        else:
            stance_score = 0.55

    if stance_score is not None:
        score = 100.0 * (
            0.40 * metrics.pace_stability_score
            + 0.25 * cadence_score
            + 0.20 * step_length_score
            + 0.15 * stance_score
        )
    else:
        # Redistribute stance weight to the other three components.
        score = 100.0 * (
            0.45 * metrics.pace_stability_score
            + 0.30 * cadence_score
            + 0.25 * step_length_score
        )

    return round(_clamp(score, 25.0, 96.0), 1)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _qualified_work_segments(activity: ParsedFitActivity) -> list:
    qualified_segments = []
    for segment in activity.segments:
        if segment.segment_type not in {"interval", "work"}:
            continue
        avg_pace = segment.avg_pace_sec_per_km
        avg_speed = 1000 / avg_pace if avg_pace and avg_pace > 0 else None
        distance_m = segment.distance_m or 0
        if avg_speed is None:
            continue
        if avg_speed > WORK_SEGMENT_SPEED_THRESHOLD_MPS and distance_m >= WORK_SEGMENT_DISTANCE_THRESHOLD_M:
            qualified_segments.append(segment)
            continue
        if avg_speed > WORK_SEGMENT_SPEED_THRESHOLD_MPS and distance_m >= SHORT_INTERVAL_DISTANCE_THRESHOLD_M:
            qualified_segments.append(segment)
    return qualified_segments