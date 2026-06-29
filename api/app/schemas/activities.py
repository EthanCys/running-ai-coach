from pydantic import BaseModel


class ParsedActivitySummary(BaseModel):
    manufacturer: str | None = None
    product_name: str | None = None
    sport: str | None = None
    sub_sport: str | None = None
    start_time: str | None = None
    total_elapsed_time_sec: float | None = None
    total_timer_time_sec: float | None = None
    total_distance_m: float | None = None
    total_calories: int | None = None
    lap_count: int = 0
    record_count: int = 0


class ParsedActivityLap(BaseModel):
    lap_index: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    total_elapsed_time_sec: float | None = None
    total_timer_time_sec: float | None = None
    total_distance_m: float | None = None
    total_calories: int | None = None
    avg_speed_mps: float | None = None
    avg_heart_rate_bpm: int | None = None
    max_heart_rate_bpm: int | None = None
    avg_running_cadence_spm: int | None = None


class ParsedActivitySegment(BaseModel):
    segment_type: str
    start_offset_sec: float | None = None
    end_offset_sec: float | None = None
    duration_sec: float
    distance_m: float | None = None
    avg_pace_sec_per_km: float | None = None
    avg_heart_rate_bpm: float | None = None


class ParsedActivityMetrics(BaseModel):
    avg_pace_sec_per_km: float | None = None
    pace_stability_score: float | None = None
    avg_heart_rate_bpm: float | None = None
    max_heart_rate_bpm: int | None = None
    avg_running_cadence_spm: float | None = None
    pace_fade_pct: float | None = None
    hr_drift_pct: float | None = None
    avg_step_length_m: float | None = None
    avg_stance_time_ms: float | None = None
    hr_outlier_count: int = 0
    interval_count: int = 0
    recovery_count: int = 0
    rest_count: int = 0


class ActivityAnalysis(BaseModel):
    training_type: str
    intensity_level: str
    ef_ratio: float | None = None
    hr_drift_pct: float | None = None
    recovery_quality: str
    recovery_hr_drop_bpm: float | None = None
    fatigue_risk_level: str
    mechanics_stability_score: float | None = None


class CoachCommentary(BaseModel):
    source: str
    model: str | None = None
    prompt_context: dict[str, object]
    summary: str
    strengths: list[str]
    watchouts: list[str]
    next_steps: list[str]


class ActivityReportFinding(BaseModel):
    title: str
    detail: str
    evidence: dict[str, float | int | str | None]


class ActivityReportRisk(BaseModel):
    level: str
    title: str
    detail: str


class ActivityRecommendation(BaseModel):
    category: str
    detail: str
    reason: str


class ActivityReport(BaseModel):
    verdict: str
    run_type_guess: str
    findings: list[ActivityReportFinding]
    risks: list[ActivityReportRisk]
    recommendation: ActivityRecommendation


class ActivityUploadResponse(BaseModel):
    activity_id: str
    filename: str
    status: str
    message: str
    stored_path: str
    summary: ParsedActivitySummary
    laps: list[ParsedActivityLap]
    segments: list[ParsedActivitySegment]
    metrics: ParsedActivityMetrics
    analysis: ActivityAnalysis
    coach_commentary: CoachCommentary
    report: ActivityReport


# ── COROS MCP analysis endpoint ──────────────────────────────────────────────

class CorosAnalyzeRequest(BaseModel):
    label_id: str
    sport_type: int
    # Optional pre-fetched context signals (caller may supply from other MCP tools)
    recovery_pct: int | None = None
    sleep_hrv: float | None = None
    resting_hr_bpm: int | None = None
    training_load_atl: float | None = None
    training_load_ctl: float | None = None
    hrv_drop_pct: float | None = None
    rhr_spike_bpm: float | None = None


class CorosContext(BaseModel):
    recovery_pct: int | None = None
    sleep_hrv: float | None = None
    resting_hr_bpm: int | None = None
    training_load_atl: float | None = None
    training_load_ctl: float | None = None
    hrv_drop_pct: float | None = None
    rhr_spike_bpm: float | None = None


class AdjustmentAlert(BaseModel):
    level: str         # "L1_emergency" | "L2_weekly" | "L3_cycle"
    title: str
    detail: str


class CorosAnalyzeResponse(BaseModel):
    label_id: str
    sport_type: int
    status: str
    summary: ParsedActivitySummary
    laps: list[ParsedActivityLap]
    segments: list[ParsedActivitySegment]
    metrics: ParsedActivityMetrics
    analysis: ActivityAnalysis
    coach_commentary: CoachCommentary
    report: ActivityReport
    coros_context: CorosContext
    adjustment_alerts: list[AdjustmentAlert]