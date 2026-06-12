from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

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
)
from app.services.fit_parser import FitParserError, parse_fit_activity
from app.services.analysis_engine import build_activity_analysis
from app.services.coach_commentary import build_coach_commentary
from app.services.report_builder import build_activity_report


router = APIRouter()
UPLOAD_DIR = Path(__file__).resolve().parents[3] / "data" / "uploads"


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
    coach_commentary = build_coach_commentary(parsed_activity, analysis, report)

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