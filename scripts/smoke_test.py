#!/usr/bin/env python3
"""End-to-end smoke test for the analysis pipeline.

Covers the four upgrades:
  1. System prompt / commentary shape (summary + key_findings + 3 lists)
  2. Per-km splits (fit_parser.km_splits populated from a real FIT)
  3. Split comparison (first vs second half)
  4. History persistence (record → read back → longitudinal compare)

Runs without a live LLM: build_coach_commentary falls back deterministically,
and the fallback path now also produces key_findings, so we can assert shape
either way.

Usage:
    cd api && .venv/bin/python ../scripts/smoke_test.py [path/to.fit]

If no FIT path is given, it looks for real files in
~/work/scripts/trainingRecords/ and falls back to a synthetic activity.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Make `app` importable when run from repo root or api/.
API_DIR = Path(__file__).resolve().parents[1] / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from app.services import history_store
from app.services.analysis_engine import build_activity_analysis
from app.services.coach_commentary import build_coach_commentary
from app.services.report_builder import build_activity_report
from app.services.fit_parser import parse_fit_activity, FitParserError


GREEN, RED, RESET = "\033[92m", "\033[91m", "\033[0m"
passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"{GREEN}✓{RESET} {name}")
    else:
        failed += 1
        print(f"{RED}✗{RESET} {name}  {detail}")


def find_fit_file(explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    search = Path.home() / "work" / "scripts" / "trainingRecords"
    if search.exists():
        fits = sorted(search.glob("*.fit"), key=lambda p: p.stat().st_mtime, reverse=True)
        if fits:
            return fits[0]
    return None


def main() -> int:
    explicit = sys.argv[1] if len(sys.argv) > 1 else None
    fit_path = find_fit_file(explicit)

    # Isolate history to a temp dir so the smoke test never touches real data.
    history_store._HISTORY_DIR = Path(tempfile.mkdtemp()) / "history"

    print("=" * 60)
    print("Running AI Coach — end-to-end smoke test")
    print("=" * 60)

    if fit_path is None:
        print(f"{RED}No FIT file found.{RESET} Pass one explicitly: smoke_test.py path/to.fit")
        print("Skipping FIT-dependent checks.")
        return 1

    print(f"Using FIT: {fit_path}\n")

    # ── 1. Parse ────────────────────────────────────────────────────────────
    try:
        activity = parse_fit_activity(fit_path)
    except FitParserError as exc:
        print(f"{RED}FIT parse failed: {exc}{RESET}")
        return 1

    check("FIT parsed", activity is not None)
    check("distance present", (activity.total_distance_m or 0) > 0,
          f"distance={activity.total_distance_m}")

    # ── 2. Per-km splits (upgrade #2) ─────────────────────────────────────────
    dist_km = (activity.total_distance_m or 0) / 1000
    check("km_splits populated", len(activity.km_splits) >= 1,
          f"got {len(activity.km_splits)} splits for {dist_km:.1f}km")
    if activity.km_splits:
        s0 = activity.km_splits[0]
        check("km_split has pace", s0.avg_pace_sec_per_km is not None,
              f"km1 pace={s0.avg_pace_sec_per_km}")
        # roughly one split per km (allow ±2 for partial last km / gaps)
        check("split count ≈ distance", abs(len(activity.km_splits) - round(dist_km)) <= 2,
              f"{len(activity.km_splits)} splits vs {dist_km:.1f}km")

    # ── 3. Analysis + report ──────────────────────────────────────────────────
    analysis = build_activity_analysis(activity)
    report = build_activity_report(activity, analysis)
    check("analysis has training_type", "training_type" in analysis,
          str(analysis.get("training_type")))
    check("report has recommendation", "recommendation" in report)

    training_type = analysis.get("training_type", "unknown")

    # ── 4. First analysis: no history yet ─────────────────────────────────────
    hist0 = history_store.recent_same_type(user_id="default", training_type=training_type)
    check("history empty on first run", hist0 == [])

    commentary1 = build_coach_commentary(activity, analysis, report, None, hist0)
    check("commentary has summary", isinstance(commentary1.get("summary"), str)
          and len(commentary1["summary"]) > 0)
    check("commentary has key_findings (upgrade #1)", "key_findings" in commentary1)
    check("commentary has 3 lists",
          all(isinstance(commentary1.get(k), list) for k in ("strengths", "watchouts", "next_steps")))
    check("prompt_context has per_km_splits (upgrade #2)",
          "per_km_splits" in commentary1["prompt_context"])
    check("prompt_context has split_comparison (upgrade #2)",
          "split_comparison" in commentary1["prompt_context"])
    check("prompt_context has rating_thresholds (upgrade #1)",
          "rating_thresholds" in commentary1["prompt_context"])
    check("prompt_context has history field (upgrade #3)",
          "history" in commentary1["prompt_context"])
    print(f"    commentary source = {commentary1['source']} (fallback expected without LLM)")

    # Record this activity, then simulate a second same-type session.
    history_store.record_activity(
        user_id="default", activity_id="SMOKE_1", training_type=training_type,
        date="2026-07-01",
        metrics={
            "avg_pace_sec": activity.metrics.avg_pace_sec_per_km,
            "stance_ms": activity.metrics.avg_stance_time_ms,
            "hr_drift_pct": activity.metrics.hr_drift_pct,
        },
    )

    # ── 5. Second run: history should now feed the LLM (upgrade #3) ────────────
    hist1 = history_store.recent_same_type(
        user_id="default", training_type=training_type, exclude_activity_id="SMOKE_2"
    )
    check("history has prior session on 2nd run", len(hist1) == 1,
          f"got {len(hist1)}")
    commentary2 = build_coach_commentary(activity, analysis, report, None, hist1)
    check("2nd commentary embeds history",
          len(commentary2["prompt_context"]["history"]) == 1)

    # ── 6. Dedupe safety ───────────────────────────────────────────────────────
    history_store.record_activity(
        user_id="default", activity_id="SMOKE_1", training_type=training_type,
        date="2026-07-01", metrics={"stance_ms": 999},
    )
    hist_after = history_store.recent_same_type(user_id="default", training_type=training_type)
    check("dedupe: SMOKE_1 not double-counted", len(hist_after) == 1,
          f"got {len(hist_after)}")

    print("\n" + "=" * 60)
    print(f"RESULT: {GREEN}{passed} passed{RESET}, "
          f"{(RED + str(failed) + ' failed' + RESET) if failed else '0 failed'}")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
