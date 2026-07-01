from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import APIRouter, File, Header, HTTPException, UploadFile

from app.schemas.activities import (
    ActivityAnalysis,
    CoachCommentary,
    ActivityReport,
    ActivityReportRisk,
    ActivityRecommendation,
    ActivityUploadResponse,
    ActivityReportFinding,
    ParsedActivityLap,
    ParsedActivitySegment,
    ParsedActivityMetrics,
    ParsedActivitySummary,
    CorosAnalyzeRequest,
    CorosAnalyzeResponse,
    CorosContext as CorosContextSchema,
    AdjustmentAlert,
)
from app.services.fit_parser import FitParserError, parse_fit_activity
from app.services.coros_adapter import build_parsed_activity, CorosContext
from app.services.analysis_engine import build_activity_analysis
from app.services.coach_commentary import build_coach_commentary
from app.services import history_store
from app.services.report_builder import build_activity_report
from app.api.routes.auth import get_session_token


router = APIRouter()
UPLOAD_DIR = Path(__file__).resolve().parents[3] / "data" / "uploads"

# ── COROS MCP base URL (same origin that the MCP server proxies) ──────────────
COROS_MCP_BASE = "https://mcpcn.coros.com/mcp"


@router.post("/upload", response_model=ActivityUploadResponse)
async def upload_activity(file: UploadFile = File(...)) -> ActivityUploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    filename = file.filename.lower()
    if not filename.endswith(".fit"):
        raise HTTPException(status_code=400, detail="Only FIT uploads are supported in the MVP")

    activity_id = str(uuid4())
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = UPLOAD_DIR / f"{activity_id}.fit"

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded FIT file is empty")

    stored_path.write_bytes(file_bytes)

    try:
        parsed_activity = parse_fit_activity(stored_path)
    except FitParserError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    analysis = build_activity_analysis(parsed_activity)
    report = build_activity_report(parsed_activity, analysis)

    training_type = analysis.get("training_type", "unknown")
    history = history_store.recent_same_type(
        user_id="default",
        training_type=training_type,
        exclude_activity_id=activity_id,
        limit=5,
    )
    coach_commentary = build_coach_commentary(
        parsed_activity, analysis, report, None, history
    )

    history_store.record_activity(
        user_id="default",
        activity_id=activity_id,
        training_type=training_type,
        date=parsed_activity.start_time.strftime("%Y-%m-%d") if parsed_activity.start_time else None,
        metrics={
            "avg_pace_sec": parsed_activity.metrics.avg_pace_sec_per_km,
            "avg_hr_bpm": parsed_activity.metrics.avg_heart_rate_bpm,
            "hr_drift_pct": parsed_activity.metrics.hr_drift_pct,
            "stance_ms": parsed_activity.metrics.avg_stance_time_ms,
            "ef_ratio": analysis.get("ef_ratio"),
        },
    )

    return ActivityUploadResponse(
        activity_id=activity_id,
        filename=file.filename,
        status="accepted",
        message="FIT upload stored and parsed successfully.",
        stored_path=str(stored_path),
        summary=ParsedActivitySummary(
            manufacturer=parsed_activity.manufacturer,
            product_name=parsed_activity.product_name,
            sport=parsed_activity.sport,
            sub_sport=parsed_activity.sub_sport,
            start_time=parsed_activity.start_time.isoformat() if parsed_activity.start_time else None,
            total_elapsed_time_sec=parsed_activity.total_elapsed_time_sec,
            total_timer_time_sec=parsed_activity.total_timer_time_sec,
            total_distance_m=parsed_activity.total_distance_m,
            total_calories=parsed_activity.total_calories,
            lap_count=parsed_activity.lap_count,
            record_count=parsed_activity.record_count,
        ),
        laps=[
            ParsedActivityLap(
                lap_index=lap.lap_index,
                start_time=lap.start_time.isoformat() if lap.start_time else None,
                end_time=lap.end_time.isoformat() if lap.end_time else None,
                total_elapsed_time_sec=lap.total_elapsed_time_sec,
                total_timer_time_sec=lap.total_timer_time_sec,
                total_distance_m=lap.total_distance_m,
                total_calories=lap.total_calories,
                avg_speed_mps=lap.avg_speed_mps,
                avg_heart_rate_bpm=lap.avg_heart_rate_bpm,
                max_heart_rate_bpm=lap.max_heart_rate_bpm,
                avg_running_cadence_spm=lap.avg_running_cadence_spm,
            )
            for lap in parsed_activity.laps
        ],
        segments=[
            ParsedActivitySegment(
                segment_type=segment.segment_type,
                start_offset_sec=segment.start_offset_sec,
                end_offset_sec=segment.end_offset_sec,
                duration_sec=segment.duration_sec,
                distance_m=segment.distance_m,
                avg_pace_sec_per_km=segment.avg_pace_sec_per_km,
                avg_heart_rate_bpm=segment.avg_heart_rate_bpm,
            )
            for segment in parsed_activity.segments
        ],
        metrics=ParsedActivityMetrics(
            avg_pace_sec_per_km=parsed_activity.metrics.avg_pace_sec_per_km,
            pace_stability_score=parsed_activity.metrics.pace_stability_score,
            avg_heart_rate_bpm=parsed_activity.metrics.avg_heart_rate_bpm,
            max_heart_rate_bpm=parsed_activity.metrics.max_heart_rate_bpm,
            avg_running_cadence_spm=parsed_activity.metrics.avg_running_cadence_spm,
            pace_fade_pct=parsed_activity.metrics.pace_fade_pct,
            hr_drift_pct=parsed_activity.metrics.hr_drift_pct,
            avg_step_length_m=parsed_activity.metrics.avg_step_length_m,
            avg_stance_time_ms=parsed_activity.metrics.avg_stance_time_ms,
            hr_outlier_count=parsed_activity.metrics.hr_outlier_count,
            interval_count=parsed_activity.metrics.interval_count,
            recovery_count=parsed_activity.metrics.recovery_count,
            rest_count=parsed_activity.metrics.rest_count,
        ),
        analysis=ActivityAnalysis(
            training_type=analysis["training_type"],
            intensity_level=analysis["intensity_level"],
            ef_ratio=analysis["ef_ratio"],
            hr_drift_pct=analysis["hr_drift_pct"],
            recovery_quality=analysis["recovery_quality"],
            recovery_hr_drop_bpm=analysis["recovery_hr_drop_bpm"],
            fatigue_risk_level=analysis["fatigue_risk_level"],
            mechanics_stability_score=analysis["mechanics_stability_score"],
        ),
        coach_commentary=CoachCommentary(
            source=coach_commentary["source"],
            model=coach_commentary["model"],
            prompt_context=coach_commentary["prompt_context"],
            summary=coach_commentary["summary"],
            strengths=coach_commentary["strengths"],
            watchouts=coach_commentary["watchouts"],
            next_steps=coach_commentary["next_steps"],
        ),
        report=ActivityReport(
            verdict=report["verdict"],
            run_type_guess=report["run_type_guess"],
            findings=[
                ActivityReportFinding(
                    title=finding["title"],
                    detail=finding["detail"],
                    evidence=finding["evidence"],
                )
                for finding in report["findings"]
            ],
            risks=[
                ActivityReportRisk(
                    level=risk["level"],
                    title=risk["title"],
                    detail=risk["detail"],
                )
                for risk in report["risks"]
            ],
            recommendation=ActivityRecommendation(
                category=report["recommendation"]["category"],
                detail=report["recommendation"]["detail"],
                reason=report["recommendation"]["reason"],
            ),
        ),
    )


# ── COROS MCP analyse endpoint ────────────────────────────────────────────────

@router.post("/analyze", response_model=CorosAnalyzeResponse)
async def analyze_coros_activity(
    req: CorosAnalyzeRequest,
    x_coros_session: str | None = Header(default=None),
) -> CorosAnalyzeResponse:
    """Fetch activity from COROS MCP and return a full analysis report.

    The caller passes labelId + sportType (obtained from querySportRecords) plus
    any pre-fetched context signals (recovery, HRV, training load).  The endpoint
    calls getActivityDetail and queryActivityLapData via the COROS MCP HTTP
    transport, then runs the same analysis pipeline as the FIT upload flow.

    Auth: if an X-Coros-Session header is present and maps to a connected OAuth
    session, that session's access token is used. Otherwise it falls back to the
    COROS_ACCESS_TOKEN env var.
    """
    access_token = get_session_token(x_coros_session)
    detail, lap_data = await _fetch_coros_activity(req.label_id, req.sport_type, access_token)

    ctx = CorosContext(
        recovery_pct=req.recovery_pct,
        sleep_hrv=req.sleep_hrv,
        resting_hr_bpm=req.resting_hr_bpm,
        training_load_atl=req.training_load_atl,
        training_load_ctl=req.training_load_ctl,
        hrv_drop_pct=req.hrv_drop_pct,
        rhr_spike_bpm=req.rhr_spike_bpm,
    )

    parsed_activity, ctx = build_parsed_activity(detail, lap_data, ctx)
    analysis = build_activity_analysis(parsed_activity)
    report = build_activity_report(parsed_activity, analysis)
    coach_commentary = build_coach_commentary(parsed_activity, analysis, report, ctx)
    alerts = _build_adjustment_alerts(ctx, analysis)

    return CorosAnalyzeResponse(
        label_id=req.label_id,
        sport_type=req.sport_type,
        status="ok",
        summary=ParsedActivitySummary(
            manufacturer=parsed_activity.manufacturer,
            product_name=parsed_activity.product_name,
            sport=parsed_activity.sport,
            sub_sport=parsed_activity.sub_sport,
            start_time=parsed_activity.start_time.isoformat() if parsed_activity.start_time else None,
            total_elapsed_time_sec=parsed_activity.total_elapsed_time_sec,
            total_timer_time_sec=parsed_activity.total_timer_time_sec,
            total_distance_m=parsed_activity.total_distance_m,
            total_calories=parsed_activity.total_calories,
            lap_count=parsed_activity.lap_count,
            record_count=parsed_activity.record_count,
        ),
        laps=[
            ParsedActivityLap(
                lap_index=lap.lap_index,
                start_time=lap.start_time.isoformat() if lap.start_time else None,
                end_time=lap.end_time.isoformat() if lap.end_time else None,
                total_elapsed_time_sec=lap.total_elapsed_time_sec,
                total_timer_time_sec=lap.total_timer_time_sec,
                total_distance_m=lap.total_distance_m,
                total_calories=lap.total_calories,
                avg_speed_mps=lap.avg_speed_mps,
                avg_heart_rate_bpm=lap.avg_heart_rate_bpm,
                max_heart_rate_bpm=lap.max_heart_rate_bpm,
                avg_running_cadence_spm=lap.avg_running_cadence_spm,
            )
            for lap in parsed_activity.laps
        ],
        segments=[
            ParsedActivitySegment(
                segment_type=seg.segment_type,
                start_offset_sec=seg.start_offset_sec,
                end_offset_sec=seg.end_offset_sec,
                duration_sec=seg.duration_sec,
                distance_m=seg.distance_m,
                avg_pace_sec_per_km=seg.avg_pace_sec_per_km,
                avg_heart_rate_bpm=seg.avg_heart_rate_bpm,
            )
            for seg in parsed_activity.segments
        ],
        metrics=ParsedActivityMetrics(
            avg_pace_sec_per_km=parsed_activity.metrics.avg_pace_sec_per_km,
            pace_stability_score=parsed_activity.metrics.pace_stability_score,
            avg_heart_rate_bpm=parsed_activity.metrics.avg_heart_rate_bpm,
            max_heart_rate_bpm=parsed_activity.metrics.max_heart_rate_bpm,
            avg_running_cadence_spm=parsed_activity.metrics.avg_running_cadence_spm,
            pace_fade_pct=parsed_activity.metrics.pace_fade_pct,
            hr_drift_pct=parsed_activity.metrics.hr_drift_pct,
            avg_step_length_m=parsed_activity.metrics.avg_step_length_m,
            avg_stance_time_ms=parsed_activity.metrics.avg_stance_time_ms,
            hr_outlier_count=parsed_activity.metrics.hr_outlier_count,
            interval_count=parsed_activity.metrics.interval_count,
            recovery_count=parsed_activity.metrics.recovery_count,
            rest_count=parsed_activity.metrics.rest_count,
        ),
        analysis=ActivityAnalysis(
            training_type=analysis["training_type"],
            intensity_level=analysis["intensity_level"],
            ef_ratio=analysis["ef_ratio"],
            hr_drift_pct=analysis["hr_drift_pct"],
            recovery_quality=analysis["recovery_quality"],
            recovery_hr_drop_bpm=analysis["recovery_hr_drop_bpm"],
            fatigue_risk_level=analysis["fatigue_risk_level"],
            mechanics_stability_score=analysis["mechanics_stability_score"],
        ),
        coach_commentary=CoachCommentary(
            source=coach_commentary["source"],
            model=coach_commentary["model"],
            prompt_context=coach_commentary["prompt_context"],
            summary=coach_commentary["summary"],
            strengths=coach_commentary["strengths"],
            watchouts=coach_commentary["watchouts"],
            next_steps=coach_commentary["next_steps"],
        ),
        report=ActivityReport(
            verdict=report["verdict"],
            run_type_guess=report["run_type_guess"],
            findings=[
                ActivityReportFinding(title=f["title"], detail=f["detail"], evidence=f["evidence"])
                for f in report["findings"]
            ],
            risks=[
                ActivityReportRisk(level=r["level"], title=r["title"], detail=r["detail"])
                for r in report["risks"]
            ],
            recommendation=ActivityRecommendation(
                category=report["recommendation"]["category"],
                detail=report["recommendation"]["detail"],
                reason=report["recommendation"]["reason"],
            ),
        ),
        coros_context=CorosContextSchema(
            recovery_pct=ctx.recovery_pct,
            sleep_hrv=ctx.sleep_hrv,
            resting_hr_bpm=ctx.resting_hr_bpm,
            training_load_atl=ctx.training_load_atl,
            training_load_ctl=ctx.training_load_ctl,
            hrv_drop_pct=ctx.hrv_drop_pct,
            rhr_spike_bpm=ctx.rhr_spike_bpm,
        ),
        adjustment_alerts=alerts,
    )


async def _fetch_coros_activity(
    label_id: str, sport_type: int, access_token: str | None = None
) -> tuple[dict, list[dict]]:
    """Call COROS MCP HTTP transport to fetch activity detail + lap data.

    Uses the provided OAuth session access_token if given, else falls back to the
    COROS_ACCESS_TOKEN env var.
    """
    coros_token = access_token or _load_coros_token()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if coros_token:
        headers["Authorization"] = f"Bearer {coros_token}"

    async with httpx.AsyncClient(timeout=30) as client:
        # getActivityDetail
        detail_resp = await client.post(
            COROS_MCP_BASE,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "getActivityDetail",
                    "arguments": {"labelId": label_id, "sportType": sport_type},
                },
            },
            headers=headers,
        )
        if detail_resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"COROS MCP getActivityDetail failed: {detail_resp.status_code}",
            )
        detail_body = detail_resp.json()
        detail = _extract_mcp_result(detail_body, "getActivityDetail")

        # queryActivityLapData
        lap_resp = await client.post(
            COROS_MCP_BASE,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "queryActivityLapData",
                    "arguments": {"labelId": label_id, "sportType": sport_type},
                },
            },
            headers=headers,
        )
        lap_data: list[dict] = []
        if lap_resp.status_code == 200:
            lap_body = lap_resp.json()
            try:
                lap_data = _extract_mcp_result(lap_body, "queryActivityLapData") or []
                if not isinstance(lap_data, list):
                    lap_data = [lap_data] if lap_data else []
            except HTTPException:
                lap_data = []

    return detail, lap_data


def _extract_mcp_result(body: dict, tool_name: str) -> dict | list:
    """Pull the actual payload from a JSON-RPC MCP response."""
    if body.get("error"):
        raise HTTPException(status_code=502, detail=f"{tool_name}: {body['error']}")
    result = body.get("result", {})
    # MCP tools/call wraps content in result.content[0].text (JSON string)
    content = result.get("content")
    if isinstance(content, list) and content:
        import json as _json
        text = content[0].get("text", "")
        try:
            parsed = _json.loads(text)
            # COROS wraps response in {result:0, data:{...}}
            if isinstance(parsed, dict) and "data" in parsed:
                return parsed["data"]
            return parsed
        except Exception:
            return {}
    return result


def _build_adjustment_alerts(ctx: CorosContext, analysis: dict) -> list[AdjustmentAlert]:
    """Generate Level 1/2/3 adjustment alerts from context signals.

    Level 1: Single-day emergency (HRV drop or RHR spike).
    Level 2: Weekly review signal (fatigue risk + training load).
    Level 3: Cycle reassessment (ATL/CTL ratio).
    """
    alerts: list[AdjustmentAlert] = []

    # Level 1 — immediate protection
    if ctx.hrv_drop_pct is not None and ctx.hrv_drop_pct >= 20:
        alerts.append(AdjustmentAlert(
            level="L1_emergency",
            title="HRV 低于基线 ≥20%",
            detail=f"HRV 较7日均值下降 {ctx.hrv_drop_pct:.0f}%，建议今日插入恢复跑或休息，不要叠加高强度训练。",
        ))
    if ctx.rhr_spike_bpm is not None and ctx.rhr_spike_bpm >= 7:
        alerts.append(AdjustmentAlert(
            level="L1_emergency",
            title="静息心率异常升高",
            detail=f"静息心率超出基线 {ctx.rhr_spike_bpm:.0f} bpm，当前身体负荷偏高，建议强制安排恢复日。",
        ))

    # Level 2 — weekly review
    fatigue = analysis.get("fatigue_risk_level", "low")
    atl = ctx.training_load_atl
    ctl = ctx.training_load_ctl
    if fatigue == "high":
        alerts.append(AdjustmentAlert(
            level="L2_weekly",
            title="本次训练疲劳信号偏高",
            detail="规则层评估疲劳风险为高，下周建议降低配速 5~10s/km 或缩减跑量 10%。",
        ))
    if atl is not None and ctl is not None and ctl > 0 and (atl / ctl) > 1.3:
        ratio = atl / ctl
        alerts.append(AdjustmentAlert(
            level="L2_weekly",
            title=f"短期负荷比偏高（ATL/CTL={ratio:.2f}）",
            detail="急性与慢性训练负荷比超过 1.3，受伤风险上升，下次训练建议轻松恢复跑。",
        ))

    # Level 3 — cycle reassessment signal (informational)
    if ctx.recovery_pct is not None and ctx.recovery_pct < 50:
        alerts.append(AdjustmentAlert(
            level="L3_cycle",
            title=f"恢复状态偏低（{ctx.recovery_pct}%）",
            detail="COROS 恢复指数低于 50%，建议在下一个4周周期开始时重新评估配速区间。",
        ))

    return alerts


def _load_coros_token() -> str | None:
    """Read COROS_ACCESS_TOKEN from env / .env.local."""
    import os
    from pathlib import Path as P
    token = os.getenv("COROS_ACCESS_TOKEN")
    if token:
        return token
    env_path = P(__file__).resolve().parents[3] / ".env.local"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("COROS_ACCESS_TOKEN="):
                return line.split("=", 1)[1].strip()
    return None