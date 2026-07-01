from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import fmean, pstdev

import fitdecode


class FitParserError(Exception):
    """Raised when a FIT file cannot be parsed into the expected summary."""


@dataclass(slots=True)
class ParsedFitActivity:
    manufacturer: str | None
    product_name: str | None
    sport: str | None
    sub_sport: str | None
    start_time: datetime | None
    total_elapsed_time_sec: float | None
    total_timer_time_sec: float | None
    total_distance_m: float | None
    total_calories: int | None
    lap_count: int
    record_count: int
    laps: list[ParsedFitLap]
    segments: list[ParsedFitSegment]
    metrics: ParsedFitMetrics
    km_splits: list["ParsedFitKmSplit"]


@dataclass(slots=True)
class ParsedFitKmSplit:
    """Per-kilometer breakdown — the basis for professional split-by-split analysis."""
    km_index: int  # 1-based
    distance_m: float
    duration_sec: float
    avg_pace_sec_per_km: float | None
    avg_heart_rate_bpm: float | None
    avg_stance_time_ms: float | None
    avg_step_length_m: float | None


@dataclass(slots=True)
class ParsedFitLap:
    lap_index: int | None
    start_time: datetime | None
    end_time: datetime | None
    total_elapsed_time_sec: float | None
    total_timer_time_sec: float | None
    total_distance_m: float | None
    total_calories: int | None
    avg_speed_mps: float | None
    avg_heart_rate_bpm: int | None
    max_heart_rate_bpm: int | None
    avg_running_cadence_spm: int | None


@dataclass(slots=True)
class ParsedFitSegment:
    segment_type: str
    start_offset_sec: float | None
    end_offset_sec: float | None
    duration_sec: float
    distance_m: float | None
    avg_pace_sec_per_km: float | None
    avg_heart_rate_bpm: float | None


@dataclass(slots=True)
class ParsedFitMetrics:
    avg_pace_sec_per_km: float | None
    pace_stability_score: float | None
    avg_heart_rate_bpm: float | None
    max_heart_rate_bpm: int | None
    avg_running_cadence_spm: float | None
    pace_fade_pct: float | None
    hr_drift_pct: float | None
    avg_step_length_m: float | None
    avg_stance_time_ms: float | None
    hr_outlier_count: int
    interval_count: int
    recovery_count: int
    rest_count: int


@dataclass(slots=True)
class RecordSample:
    timestamp: datetime | None
    distance_m: float | None
    speed_mps: float | None
    heart_rate_bpm: int | None
    step_length_m: float | None
    stance_time_ms: float | None


def parse_fit_activity(file_path: Path) -> ParsedFitActivity:
    manufacturer: str | None = None
    product_name: str | None = None
    sport: str | None = None
    sub_sport: str | None = None
    start_time: datetime | None = None
    total_elapsed_time_sec: float | None = None
    total_timer_time_sec: float | None = None
    total_distance_m: float | None = None
    total_calories: int | None = None
    laps: list[ParsedFitLap] = []
    records: list[RecordSample] = []

    try:
        with fitdecode.FitReader(file_path) as fit_reader:
            for frame in fit_reader:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue

                if frame.name == "file_id":
                    manufacturer = _coerce_text(_get_value(frame, "manufacturer"), manufacturer)
                    product_name = _coerce_text(_get_value(frame, "product_name"), product_name)
                    continue

                if frame.name == "device_info":
                    product_name = _coerce_text(_get_value(frame, "product_name"), product_name)
                    manufacturer = _coerce_text(_get_value(frame, "manufacturer"), manufacturer)
                    continue

                if frame.name == "session":
                    sport = _coerce_text(_get_value(frame, "sport"), sport)
                    sub_sport = _coerce_text(_get_value(frame, "sub_sport"), sub_sport)
                    start_time = _coerce_datetime(_get_value(frame, "start_time"), start_time)
                    total_elapsed_time_sec = _coerce_float(
                        _get_value(frame, "total_elapsed_time"), total_elapsed_time_sec
                    )
                    total_timer_time_sec = _coerce_float(
                        _get_value(frame, "total_timer_time"), total_timer_time_sec
                    )
                    total_distance_m = _coerce_float(
                        _get_value(frame, "total_distance"), total_distance_m
                    )
                    total_calories = _coerce_int(_get_value(frame, "total_calories"), total_calories)
                    continue

                if frame.name == "lap":
                    laps.append(
                        ParsedFitLap(
                            lap_index=_coerce_int(_get_value(frame, "message_index"), None),
                            start_time=_coerce_datetime(_get_value(frame, "start_time"), None),
                            end_time=_coerce_datetime(_get_value(frame, "timestamp"), None),
                            total_elapsed_time_sec=_coerce_float(
                                _get_value(frame, "total_elapsed_time"), None
                            ),
                            total_timer_time_sec=_coerce_float(
                                _get_value(frame, "total_timer_time"), None
                            ),
                            total_distance_m=_coerce_float(_get_value(frame, "total_distance"), None),
                            total_calories=_coerce_int(_get_value(frame, "total_calories"), None),
                            avg_speed_mps=_coerce_float(
                                _get_value(frame, "enhanced_avg_speed")
                                or _get_value(frame, "avg_speed"),
                                None,
                            ),
                            avg_heart_rate_bpm=_coerce_int(
                                _get_value(frame, "avg_heart_rate"), None
                            ),
                            max_heart_rate_bpm=_coerce_int(
                                _get_value(frame, "max_heart_rate"), None
                            ),
                            avg_running_cadence_spm=_coerce_int(
                                _scale_cadence(_get_value(frame, "avg_running_cadence")), None
                            ),
                        )
                    )
                    continue

                if frame.name == "record":
                    records.append(
                        RecordSample(
                            timestamp=_coerce_datetime(_get_value(frame, "timestamp"), None),
                            distance_m=_coerce_float(_get_value(frame, "distance"), None),
                            speed_mps=_coerce_float(
                                _get_value(frame, "enhanced_speed") or _get_value(frame, "speed"),
                                None,
                            ),
                            heart_rate_bpm=_coerce_int(_get_value(frame, "heart_rate"), None),
                            step_length_m=_coerce_float(
                                _scale_step_length(_get_value(frame, "step_length")), None
                            ),
                            stance_time_ms=_coerce_float(_get_value(frame, "stance_time"), None),
                        )
                    )

        if not any(
            value is not None
            for value in (
                manufacturer,
                product_name,
                sport,
                sub_sport,
                start_time,
                total_elapsed_time_sec,
                total_timer_time_sec,
                total_distance_m,
                total_calories,
                laps,
                records,
            )
        ):
            raise FitParserError("FIT file parsed but no activity summary fields were found")
    except fitdecode.FitError as exc:
        raise FitParserError(f"FIT decode failed: {exc}") from exc

    cleaned_records, hr_outlier_count = _clean_records(records)
    segments = _build_segments(cleaned_records)
    km_splits = _build_km_splits(cleaned_records)

    metrics = _build_metrics(
        total_timer_time_sec=total_timer_time_sec,
        total_distance_m=total_distance_m,
        laps=laps,
        records=cleaned_records,
        segments=segments,
        hr_outlier_count=hr_outlier_count,
    )

    return ParsedFitActivity(
        manufacturer=manufacturer,
        product_name=product_name,
        sport=sport,
        sub_sport=sub_sport,
        start_time=start_time,
        total_elapsed_time_sec=total_elapsed_time_sec,
        total_timer_time_sec=total_timer_time_sec,
        total_distance_m=total_distance_m,
        total_calories=total_calories,
        lap_count=len(laps),
        record_count=len(records),
        laps=laps,
        segments=segments,
        metrics=metrics,
        km_splits=km_splits,
    )


def _coerce_text(value: object, current: str | None) -> str | None:
    if value in (None, ""):
        return current
    return str(value)


def _coerce_datetime(value: object, current: datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return current


def _coerce_float(value: object, current: float | None) -> float | None:
    if value is None:
        return current
    try:
        return float(value)
    except (TypeError, ValueError):
        return current


def _get_value(frame: fitdecode.FitDataMessage, field_name: str) -> object | None:
    try:
        return frame.get_value(field_name)
    except KeyError:
        return None


def _coerce_int(value: object, current: int | None) -> int | None:
    if value is None:
        return current
    try:
        return int(value)
    except (TypeError, ValueError):
        return current


def _scale_step_length(value: object) -> object:
    try:
        return float(value) / 1000
    except (TypeError, ValueError):
        return value


def _scale_cadence(value: object) -> object:
    try:
        return int(round(float(value) * 2))
    except (TypeError, ValueError):
        return value


def _build_metrics(
    *,
    total_timer_time_sec: float | None,
    total_distance_m: float | None,
    laps: list[ParsedFitLap],
    records: list[RecordSample],
    segments: list[ParsedFitSegment],
    hr_outlier_count: int,
) -> ParsedFitMetrics:
    moving_records = [record for record in records if record.speed_mps is not None and record.speed_mps > 0.5]
    distance_m = total_distance_m
    if distance_m is None:
        distance_candidates = [record.distance_m for record in moving_records if record.distance_m is not None]
        distance_m = distance_candidates[-1] if distance_candidates else None

    avg_pace_sec_per_km: float | None = None
    if total_timer_time_sec and distance_m and distance_m > 0:
        avg_pace_sec_per_km = total_timer_time_sec / (distance_m / 1000)

    lap_speeds = [lap.avg_speed_mps for lap in laps if lap.avg_speed_mps is not None and lap.avg_speed_mps > 0]
    record_speeds = [r.speed_mps for r in moving_records if r.speed_mps is not None]
    pace_stability_score = _compute_pace_stability_score(lap_speeds, record_speeds)

    heart_rates = [record.heart_rate_bpm for record in moving_records if record.heart_rate_bpm is not None]
    avg_heart_rate_bpm = round(fmean(heart_rates), 2) if heart_rates else None
    max_heart_rate_bpm = max(heart_rates) if heart_rates else None

    cadence_values = []
    cadence_weights = []
    for lap in laps:
        if lap.avg_running_cadence_spm is None or lap.total_timer_time_sec in (None, 0):
            continue
        cadence_values.append(lap.avg_running_cadence_spm)
        cadence_weights.append(lap.total_timer_time_sec)

    avg_running_cadence_spm = None
    if cadence_values and cadence_weights and sum(cadence_weights) > 0:
        avg_running_cadence_spm = round(
            sum(value * weight for value, weight in zip(cadence_values, cadence_weights))
            / sum(cadence_weights),
            2,
        )

    first_half, second_half = _split_record_halves(moving_records, distance_m)
    pace_fade_pct = _compute_pace_fade_pct(first_half, second_half)
    hr_drift_pct = _compute_hr_drift_pct(first_half, second_half)

    step_lengths = [record.step_length_m for record in moving_records if record.step_length_m is not None]
    avg_step_length_m = round(fmean(step_lengths), 3) if step_lengths else None

    stance_times = [record.stance_time_ms for record in moving_records if record.stance_time_ms is not None]
    avg_stance_time_ms = round(fmean(stance_times), 2) if stance_times else None

    return ParsedFitMetrics(
        avg_pace_sec_per_km=round(avg_pace_sec_per_km, 2) if avg_pace_sec_per_km is not None else None,
        pace_stability_score=pace_stability_score,
        avg_heart_rate_bpm=avg_heart_rate_bpm,
        max_heart_rate_bpm=max_heart_rate_bpm,
        avg_running_cadence_spm=avg_running_cadence_spm,
        pace_fade_pct=pace_fade_pct,
        hr_drift_pct=hr_drift_pct,
        avg_step_length_m=avg_step_length_m,
        avg_stance_time_ms=avg_stance_time_ms,
        hr_outlier_count=hr_outlier_count,
        interval_count=sum(1 for segment in segments if segment.segment_type == "interval"),
        recovery_count=sum(1 for segment in segments if segment.segment_type == "recovery"),
        rest_count=sum(1 for segment in segments if segment.segment_type == "rest"),
    )


def _clean_records(records: list[RecordSample]) -> tuple[list[RecordSample], int]:
    smoothed_speeds = _smooth_speed_series([record.speed_mps for record in records])
    cleaned_heart_rates, hr_outlier_count = _clean_heart_rate_series(
        [record.heart_rate_bpm for record in records]
    )
    cleaned_records = [
        RecordSample(
            timestamp=record.timestamp,
            distance_m=record.distance_m,
            speed_mps=smoothed_speeds[index],
            heart_rate_bpm=cleaned_heart_rates[index],
            step_length_m=record.step_length_m,
            stance_time_ms=record.stance_time_ms,
        )
        for index, record in enumerate(records)
    ]
    return cleaned_records, hr_outlier_count


def _smooth_speed_series(values: list[float | None], radius: int = 2) -> list[float | None]:
    smoothed: list[float | None] = []
    for index, value in enumerate(values):
        if value is None:
            smoothed.append(None)
            continue
        window = [
            candidate
            for candidate in values[max(0, index - radius) : min(len(values), index + radius + 1)]
            if candidate is not None
        ]
        smoothed.append(round(fmean(window), 3) if window else value)
    return smoothed


def _clean_heart_rate_series(values: list[int | None]) -> tuple[list[int | None], int]:
    cleaned = values[:]
    corrections = 0

    for index, value in enumerate(cleaned):
        if value is None:
            continue
        if value < 55 or value > 230:
            cleaned[index] = None
            corrections += 1

    for index, value in enumerate(cleaned):
        if value is None:
            prev_value = _nearest_valid_value(cleaned, index, -1)
            next_value = _nearest_valid_value(cleaned, index, 1)
            if prev_value is not None and next_value is not None and abs(prev_value - next_value) <= 6:
                cleaned[index] = round((prev_value + next_value) / 2)
                corrections += 1
            continue

        prev_value = _nearest_valid_value(cleaned, index, -1)
        next_value = _nearest_valid_value(cleaned, index, 1)
        if prev_value is None or next_value is None:
            continue
        neighbor_mean = (prev_value + next_value) / 2
        if abs(prev_value - next_value) <= 10 and abs(value - neighbor_mean) >= 20:
            cleaned[index] = round(neighbor_mean)
            corrections += 1

    return cleaned, corrections


def _nearest_valid_value(values: list[int | None], start_index: int, step: int) -> int | None:
    index = start_index + step
    while 0 <= index < len(values):
        if values[index] is not None:
            return values[index]
        index += step
    return None


def _build_km_splits(records: list[RecordSample]) -> list[ParsedFitKmSplit]:
    """Split records into per-kilometer buckets using cumulative distance.

    Each split reports pace (from time delta), avg HR, avg stance time and avg
    step length — the per-km detail a coach needs to read pacing strategy,
    negative splits, and mechanical fade across the run.
    """
    pts = [
        r for r in records
        if r.distance_m is not None and r.timestamp is not None
    ]
    if len(pts) < 2:
        return []

    splits: list[ParsedFitKmSplit] = []
    km_index = 1
    bucket_start_idx = 0
    next_mark = 1000.0
    base_distance = pts[0].distance_m or 0.0

    for i, r in enumerate(pts):
        dist = (r.distance_m or 0.0) - base_distance
        if dist >= next_mark or i == len(pts) - 1:
            bucket = pts[bucket_start_idx : i + 1]
            if len(bucket) >= 2:
                seg_dist = (bucket[-1].distance_m or 0.0) - (bucket[0].distance_m or 0.0)
                seg_time = _duration_between(bucket[0], bucket[-1])
                hrs = [b.heart_rate_bpm for b in bucket if b.heart_rate_bpm is not None]
                gcts = [b.stance_time_ms for b in bucket if b.stance_time_ms is not None and b.stance_time_ms > 0]
                sls = [b.step_length_m for b in bucket if b.step_length_m is not None and b.step_length_m > 0]
                pace = round(seg_time / (seg_dist / 1000), 1) if seg_dist > 0 and seg_time > 0 else None
                splits.append(
                    ParsedFitKmSplit(
                        km_index=km_index,
                        distance_m=round(seg_dist, 1),
                        duration_sec=round(seg_time, 1),
                        avg_pace_sec_per_km=pace,
                        avg_heart_rate_bpm=round(fmean(hrs), 1) if hrs else None,
                        avg_stance_time_ms=round(fmean(gcts), 1) if gcts else None,
                        avg_step_length_m=round(fmean(sls), 3) if sls else None,
                    )
                )
                km_index += 1
            bucket_start_idx = i + 1
            next_mark += 1000.0

    return splits


def _build_segments(records: list[RecordSample]) -> list[ParsedFitSegment]:
    records_with_time = [record for record in records if record.timestamp is not None]
    if len(records_with_time) < 2:
        return []

    moving_speeds = [record.speed_mps for record in records_with_time if record.speed_mps is not None and record.speed_mps > 0.8]
    if not moving_speeds:
        return []

    # If the run is paced uniformly (speed CV < 6%), structural segmentation adds
    # noise rather than signal.  Return a single "steady_run" segment instead.
    mean_speed = fmean(moving_speeds)
    if mean_speed > 0 and pstdev(moving_speeds) / mean_speed < 0.06:
        first = records_with_time[0]
        last = records_with_time[-1]
        duration = _duration_between(first, last)
        distance = _segment_distance(records_with_time)
        avg_pace = round(1000 / mean_speed, 2)
        avg_hr_val = _average_heart_rate(records_with_time)
        return [
            ParsedFitSegment(
                segment_type="steady_run",
                start_offset_sec=0.0,
                end_offset_sec=round(duration, 2),
                duration_sec=round(duration, 2),
                distance_m=distance,
                avg_pace_sec_per_km=avg_pace,
                avg_heart_rate_bpm=round(avg_hr_val, 2) if avg_hr_val is not None else None,
            )
        ]

    fast_threshold = max(3.2, _percentile(moving_speeds, 0.78) or 3.2)
    raw_segments: list[dict[str, int | str]] = []

    current_state = _classify_record_state(records_with_time[0], fast_threshold)
    start_index = 0
    for index, record in enumerate(records_with_time[1:], start=1):
        state = _classify_record_state(record, fast_threshold)
        if state == current_state:
            continue
        raw_segments.append(
            {
                "segment_type": current_state,
                "start_index": start_index,
                "end_index": index - 1,
            }
        )
        current_state = state
        start_index = index

    raw_segments.append(
        {
            "segment_type": current_state,
            "start_index": start_index,
            "end_index": len(records_with_time) - 1,
        }
    )

    merged_segments = _merge_short_segments(records_with_time, raw_segments)
    parsed_segments = [
        _materialize_segment(records_with_time, segment)
        for segment in merged_segments
        if _materialize_segment(records_with_time, segment) is not None
    ]
    return _relabel_segments(parsed_segments)


def _classify_record_state(record: RecordSample, fast_threshold: float) -> str:
    speed = record.speed_mps or 0
    if speed < 0.5:
        return "rest"
    if speed < 1.9:
        return "recovery"
    if speed >= fast_threshold:
        return "work"
    return "steady"


def _merge_short_segments(
    records: list[RecordSample], raw_segments: list[dict[str, int | str]], min_duration_sec: float = 30
) -> list[dict[str, int | str]]:
    merged: list[dict[str, int | str]] = []
    index = 0
    while index < len(raw_segments):
        segment = raw_segments[index]
        duration_sec = _duration_between(
            records[int(segment["start_index"])],
            records[int(segment["end_index"])],
        )
        if duration_sec >= min_duration_sec or len(raw_segments) == 1:
            merged.append(segment.copy())
            index += 1
            continue

        next_segment = raw_segments[index + 1] if index + 1 < len(raw_segments) else None
        if merged and next_segment and merged[-1]["segment_type"] == next_segment["segment_type"]:
            merged[-1]["end_index"] = next_segment["end_index"]
            index += 2
            continue
        if merged:
            merged[-1]["end_index"] = segment["end_index"]
        elif next_segment:
            next_segment["start_index"] = segment["start_index"]
        else:
            merged.append(segment.copy())
        index += 1
    return merged


def _materialize_segment(
    records: list[RecordSample], segment: dict[str, int | str]
) -> ParsedFitSegment | None:
    start_index = int(segment["start_index"])
    end_index = int(segment["end_index"])
    chunk = records[start_index : end_index + 1]
    if len(chunk) < 2:
        return None

    first_timestamp = records[0].timestamp
    start_timestamp = chunk[0].timestamp
    end_timestamp = chunk[-1].timestamp
    if first_timestamp is None or start_timestamp is None or end_timestamp is None:
        return None

    duration_sec = _duration_between(chunk[0], chunk[-1])
    distance_m = _segment_distance(chunk)
    avg_speed = _average_speed(chunk)
    avg_pace_sec_per_km = round(1000 / avg_speed, 2) if avg_speed and avg_speed > 0 else None

    return ParsedFitSegment(
        segment_type=str(segment["segment_type"]),
        start_offset_sec=round((start_timestamp - first_timestamp).total_seconds(), 2),
        end_offset_sec=round((end_timestamp - first_timestamp).total_seconds(), 2),
        duration_sec=round(duration_sec, 2),
        distance_m=distance_m,
        avg_pace_sec_per_km=avg_pace_sec_per_km,
        avg_heart_rate_bpm=round(_average_heart_rate(chunk), 2) if _average_heart_rate(chunk) is not None else None,
    )


def _relabel_segments(segments: list[ParsedFitSegment]) -> list[ParsedFitSegment]:
    if not segments:
        return segments

    relabeled = [
        ParsedFitSegment(
            segment_type=segment.segment_type,
            start_offset_sec=segment.start_offset_sec,
            end_offset_sec=segment.end_offset_sec,
            duration_sec=segment.duration_sec,
            distance_m=segment.distance_m,
            avg_pace_sec_per_km=segment.avg_pace_sec_per_km,
            avg_heart_rate_bpm=segment.avg_heart_rate_bpm,
        )
        for segment in segments
    ]

    for segment in relabeled:
        if segment.segment_type == "work" and segment.duration_sec < 45:
            segment.segment_type = "steady"

    # Skip interval detection when the run is steady-paced (CV < 0.06).
    work_paces = [
        segment.avg_pace_sec_per_km
        for segment in relabeled
        if segment.segment_type == "work" and segment.avg_pace_sec_per_km is not None
    ]
    if work_paces:
        all_moving_paces = [
            segment.avg_pace_sec_per_km
            for segment in relabeled
            if segment.avg_pace_sec_per_km is not None and segment.segment_type not in {"rest"}
        ]
        if all_moving_paces:
            mean_pace = fmean(all_moving_paces)
            cv = pstdev(all_moving_paces) / mean_pace if mean_pace > 0 else 1.0
            if cv < 0.06:
                for segment in relabeled:
                    if segment.segment_type == "work":
                        segment.segment_type = "steady"

    interval_indexes = [index for index, segment in enumerate(relabeled) if segment.segment_type == "work"]
    if len(interval_indexes) >= 2:
        first_interval = interval_indexes[0]
        last_interval = interval_indexes[-1]
        for index in interval_indexes:
            relabeled[index].segment_type = "interval"
        for index in range(first_interval):
            if relabeled[index].segment_type in {"steady", "recovery"}:
                relabeled[index].segment_type = "warmup"
        for index in range(last_interval + 1, len(relabeled)):
            if relabeled[index].segment_type in {"steady", "recovery"}:
                relabeled[index].segment_type = "cooldown"
        for index in range(first_interval + 1, last_interval):
            if relabeled[index].segment_type == "steady":
                relabeled[index].segment_type = "recovery"
    else:
        moving_indexes = [index for index, segment in enumerate(relabeled) if segment.segment_type != "rest"]
        if moving_indexes:
            first_index = moving_indexes[0]
            if relabeled[first_index].duration_sec >= 120:
                relabeled[first_index].segment_type = "warmup"
            last_index = moving_indexes[-1]
            if last_index != first_index and relabeled[last_index].segment_type in {"recovery", "steady"} and relabeled[last_index].duration_sec >= 120:
                relabeled[last_index].segment_type = "cooldown"

    return _merge_adjacent_segments(relabeled)


def _merge_adjacent_segments(segments: list[ParsedFitSegment]) -> list[ParsedFitSegment]:
    if not segments:
        return []

    merged = [segments[0]]
    for segment in segments[1:]:
        previous = merged[-1]
        if previous.segment_type != segment.segment_type:
            merged.append(segment)
            continue

        combined_duration = previous.duration_sec + segment.duration_sec
        combined_distance = None
        if previous.distance_m is not None or segment.distance_m is not None:
            combined_distance = round((previous.distance_m or 0) + (segment.distance_m or 0), 2)

        avg_pace_sec_per_km = None
        if previous.avg_pace_sec_per_km is not None or segment.avg_pace_sec_per_km is not None:
            weighted_pace_sum = 0.0
            weighted_pace_weight = 0.0
            if previous.avg_pace_sec_per_km is not None:
                weighted_pace_sum += previous.avg_pace_sec_per_km * previous.duration_sec
                weighted_pace_weight += previous.duration_sec
            if segment.avg_pace_sec_per_km is not None:
                weighted_pace_sum += segment.avg_pace_sec_per_km * segment.duration_sec
                weighted_pace_weight += segment.duration_sec
            if weighted_pace_weight > 0:
                avg_pace_sec_per_km = round(weighted_pace_sum / weighted_pace_weight, 2)

        avg_heart_rate_bpm = None
        if previous.avg_heart_rate_bpm is not None or segment.avg_heart_rate_bpm is not None:
            weighted_hr_sum = 0.0
            weighted_hr_weight = 0.0
            if previous.avg_heart_rate_bpm is not None:
                weighted_hr_sum += previous.avg_heart_rate_bpm * previous.duration_sec
                weighted_hr_weight += previous.duration_sec
            if segment.avg_heart_rate_bpm is not None:
                weighted_hr_sum += segment.avg_heart_rate_bpm * segment.duration_sec
                weighted_hr_weight += segment.duration_sec
            if weighted_hr_weight > 0:
                avg_heart_rate_bpm = round(weighted_hr_sum / weighted_hr_weight, 2)

        merged[-1] = ParsedFitSegment(
            segment_type=previous.segment_type,
            start_offset_sec=previous.start_offset_sec,
            end_offset_sec=segment.end_offset_sec,
            duration_sec=round(combined_duration, 2),
            distance_m=combined_distance,
            avg_pace_sec_per_km=avg_pace_sec_per_km,
            avg_heart_rate_bpm=avg_heart_rate_bpm,
        )

    return merged


def _duration_between(first: RecordSample, last: RecordSample) -> float:
    if first.timestamp is None or last.timestamp is None:
        return 0
    return max((last.timestamp - first.timestamp).total_seconds(), 0)


def _segment_distance(records: list[RecordSample]) -> float | None:
    distances = [record.distance_m for record in records if record.distance_m is not None]
    if len(distances) < 2:
        return None
    return round(max(distances[-1] - distances[0], 0), 2)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * percentile))
    return ordered[max(0, min(index, len(ordered) - 1))]


def _split_record_halves(
    moving_records: list[RecordSample], distance_m: float | None
) -> tuple[list[RecordSample], list[RecordSample]]:
    with_distance = [record for record in moving_records if record.distance_m is not None]
    if distance_m and with_distance:
        midpoint = distance_m / 2
        first_half = [record for record in with_distance if record.distance_m is not None and record.distance_m <= midpoint]
        second_half = [record for record in with_distance if record.distance_m is not None and record.distance_m > midpoint]
        if first_half and second_half:
            return first_half, second_half

    midpoint_index = len(moving_records) // 2
    return moving_records[:midpoint_index], moving_records[midpoint_index:]


def _compute_pace_fade_pct(
    first_half: list[RecordSample], second_half: list[RecordSample]
) -> float | None:
    avg_speed_first = _average_speed(first_half)
    avg_speed_second = _average_speed(second_half)
    if avg_speed_first is None or avg_speed_second is None or avg_speed_second <= 0:
        return None
    return round(((avg_speed_first / avg_speed_second) - 1) * 100, 2)


def _compute_hr_drift_pct(
    first_half: list[RecordSample], second_half: list[RecordSample]
) -> float | None:
    avg_speed_first = _average_speed(first_half)
    avg_speed_second = _average_speed(second_half)
    avg_hr_first = _average_heart_rate(first_half)
    avg_hr_second = _average_heart_rate(second_half)
    if (
        avg_speed_first is None
        or avg_speed_second is None
        or avg_speed_first <= 0
        or avg_speed_second <= 0
        or avg_hr_first is None
        or avg_hr_second is None
        or avg_hr_first <= 0
    ):
        return None
    first_ratio = avg_hr_first / avg_speed_first
    second_ratio = avg_hr_second / avg_speed_second
    return round(((second_ratio / first_ratio) - 1) * 100, 2)


def _average_speed(records: list[RecordSample]) -> float | None:
    speeds = [record.speed_mps for record in records if record.speed_mps is not None and record.speed_mps > 0]
    return fmean(speeds) if speeds else None


def _average_heart_rate(records: list[RecordSample]) -> float | None:
    heart_rates = [record.heart_rate_bpm for record in records if record.heart_rate_bpm is not None]
    return fmean(heart_rates) if heart_rates else None


def _compute_pace_stability_score(lap_speeds: list[float], record_speeds: list[float] | None = None) -> float | None:
    if len(lap_speeds) >= 2:
        mean_speed = fmean(lap_speeds)
        if mean_speed <= 0:
            return None
        coefficient_of_variation = pstdev(lap_speeds) / mean_speed
        score = max(0.0, 1 - min(coefficient_of_variation / 0.12, 1.0))
        return round(score, 3)
    # Fallback: use per-record speed CV when only one lap is available.
    if record_speeds and len(record_speeds) >= 2:
        mean_speed = fmean(record_speeds)
        if mean_speed <= 0:
            return None
        coefficient_of_variation = pstdev(record_speeds) / mean_speed
        score = max(0.0, 1 - min(coefficient_of_variation / 0.12, 1.0))
        return round(score, 3)
    return None