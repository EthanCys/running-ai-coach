from __future__ import annotations

from app.services.fit_parser import ParsedFitActivity, ParsedFitMetrics


def build_activity_report(activity: ParsedFitActivity, analysis: dict) -> dict:
    metrics = activity.metrics
    run_type_guess = analysis["training_type"]
    findings = _build_findings(metrics, activity, analysis)
    risks = _build_risks(metrics, activity, analysis)
    recommendation = _build_recommendation(metrics, run_type_guess, risks, analysis)

    verdict_parts = [
        _run_type_phrase(run_type_guess),
        _structure_phrase(activity, analysis),
        _analysis_phrase(analysis),
        _stability_phrase(metrics),
        _pace_phrase(metrics),
        _drift_phrase(metrics),
    ]
    verdict = " ".join(part for part in verdict_parts if part)

    return {
        "verdict": verdict,
        "run_type_guess": run_type_guess,
        "findings": findings,
        "risks": risks,
        "recommendation": recommendation,
    }


def _run_type_phrase(run_type_guess: str) -> str:
    phrases = {
        "interval_session": "这次更像一堂间歇质量课。",
        "long_aerobic": "这次更像一次长距离有氧跑。",
        "steady_aerobic": "这次更像一次稳定有氧跑。",
        "recovery_run": "这次更像一次恢复跑。",
        "progression_run": "这次更像一次渐进跑。",
        "mixed_run": "这次是一堂混合强度训练。",
    }
    return phrases.get(run_type_guess, "这是一堂跑步训练。")


def _analysis_phrase(analysis: dict) -> str:
    fatigue = analysis.get("fatigue_risk_level")
    hr_drift = analysis.get("hr_drift_pct")
    if hr_drift is None:
        return ""
    if hr_drift < 3 and fatigue == "low":
        return "心率表现稳定，当前没有明显疲劳信号。"
    if hr_drift < 5:
        return f"心率漂移处于正常范围，疲劳风险{_risk_level_zh(fatigue)}。"
    return f"心率漂移偏高，疲劳风险{_risk_level_zh(fatigue)}。"


def _structure_phrase(activity: ParsedFitActivity, analysis: dict) -> str:
    interval_count = activity.metrics.interval_count
    recovery_count = activity.metrics.recovery_count
    if analysis.get("training_type") == "interval_session" and interval_count >= 2:
        return f"按分段结果看，这次训练包含 {interval_count} 个工作段和 {recovery_count} 个恢复段。"
    if interval_count >= 2:
        return f"虽然识别出 {interval_count} 段较快跑和 {recovery_count} 段恢复，但按工作段阈值看，这次更接近有氧训练而不是标准质量课。"
    if activity.segments:
        segment_labels = [segment.segment_type for segment in activity.segments[:3]]
        return f"训练前半段结构依次为：{'、'.join(_segment_type_zh(label) for label in segment_labels)}。"
    return ""


def _pace_phrase(metrics: ParsedFitMetrics) -> str:
    if metrics.pace_fade_pct is None:
        return ""
    if metrics.pace_fade_pct <= -1:
        return "后程配速略快于前程，收尾控制不错。"
    if metrics.pace_fade_pct < 2:
        return "全程配速整体比较稳定。"
    return "后程配速出现下降，后续要留意配速控制和疲劳管理。"


def _stability_phrase(metrics: ParsedFitMetrics) -> str:
    if metrics.pace_stability_score is None:
        return ""
    if metrics.pace_stability_score >= 0.85:
        return "整堂课的配速控制质量较高。"
    if metrics.pace_stability_score >= 0.65:
        return "整堂课的配速控制还可以，但存在一定波动。"
    return "配速波动偏大，配速和体感控制还有提升空间。"


def _drift_phrase(metrics: ParsedFitMetrics) -> str:
    if metrics.hr_drift_pct is None:
        return ""
    if metrics.hr_drift_pct < 3:
        return "心率漂移较低，说明后程代价控制得不错。"
    if metrics.hr_drift_pct < 6:
        return "心率漂移已经出现，但仍在中等范围。"
    return "心率漂移偏高，说明耐力效率或当日恢复状态需要关注。"


def _build_findings(metrics: ParsedFitMetrics, activity: ParsedFitActivity, analysis: dict) -> list[dict]:
    findings: list[dict] = []

    findings.append(
        {
            "title": "规则层结论",
            "detail": (
                f"规则层将这次训练判定为{_training_type_zh(analysis['training_type'])}，"
                f"动作稳定性为 {analysis['mechanics_stability_score']}。"
            ),
            "evidence": {
                "ef_ratio": analysis["ef_ratio"],
                "recovery_hr_drop_bpm": analysis["recovery_hr_drop_bpm"],
                "mechanics_stability_score": analysis["mechanics_stability_score"],
                "fatigue_risk_level": analysis["fatigue_risk_level"],
            },
        }
    )

    if activity.segments:
        findings.append(
            {
                "title": "训练结构",
                "detail": _segment_summary(activity),
                "evidence": {
                    "interval_count": metrics.interval_count,
                    "recovery_count": metrics.recovery_count,
                    "rest_count": metrics.rest_count,
                    "hr_outlier_count": metrics.hr_outlier_count,
                },
            }
        )

    findings.append(
        {
            "title": "跑量与时长",
            "detail": (
                f"本次训练完成了 {round((activity.total_distance_m or 0) / 1000, 2)} 公里，"
                f"移动时间约 {round((activity.total_timer_time_sec or 0) / 60, 1)} 分钟。"
            ),
            "evidence": {
                "total_distance_m": activity.total_distance_m,
                "total_timer_time_sec": activity.total_timer_time_sec,
            },
        }
    )

    if metrics.pace_fade_pct is not None:
        findings.append(
            {
                "title": "配速走势",
                "detail": (
                    "后半程相对前半程的配速变化为 "
                    f"{metrics.pace_fade_pct}%。"
                ),
                "evidence": {
                    "pace_fade_pct": metrics.pace_fade_pct,
                    "pace_stability_score": metrics.pace_stability_score,
                },
            }
        )

    if metrics.hr_drift_pct is not None:
        findings.append(
            {
                "title": "心率漂移",
                "detail": (
                    "心率相对速度的漂移为 "
                    f"{metrics.hr_drift_pct}%，可用于判断后程代价是否上升。"
                ),
                "evidence": {
                    "hr_drift_pct": metrics.hr_drift_pct,
                    "avg_heart_rate_bpm": metrics.avg_heart_rate_bpm,
                },
            }
        )

    if metrics.avg_running_cadence_spm is not None and metrics.avg_step_length_m is not None:
        findings.append(
            {
                "title": "步态概况",
                "detail": (
                    f"平均步频约 {round(metrics.avg_running_cadence_spm)} spm，"
                    f"平均步幅约 {metrics.avg_step_length_m} 米。"
                ),
                "evidence": {
                    "avg_running_cadence_spm": metrics.avg_running_cadence_spm,
                    "avg_step_length_m": metrics.avg_step_length_m,
                },
            }
        )

    return findings[:4]


def _build_risks(metrics: ParsedFitMetrics, activity: ParsedFitActivity, analysis: dict) -> list[str]:
    risks: list[dict] = []
    if analysis["fatigue_risk_level"] == "high":
        risks.append(
            {
                "level": "high",
                "title": "疲劳风险偏高",
                "detail": "规则层判断本次训练的内部负荷和后程代价偏高，下一次训练需要保守安排。",
            }
        )
    if metrics.hr_drift_pct is not None and metrics.hr_drift_pct >= 6:
        risks.append(
            {
                "level": "moderate",
                "title": "后程心肺代价上升明显",
                "detail": "后程心率漂移较高，说明耐力效率或环境管理需要关注。",
            }
        )
    if metrics.pace_fade_pct is not None and metrics.pace_fade_pct >= 3:
        risks.append(
            {
                "level": "moderate",
                "title": "后半程掉速明显",
                "detail": "后半程速度下降较多，说明配速控制或疲劳管理需要加强。",
            }
        )
    if metrics.pace_stability_score is not None and metrics.pace_stability_score < 0.6:
        risks.append(
            {
                "level": "low",
                "title": "配速不够稳定",
                "detail": "整堂课波动偏大，若能进一步稳住输出，训练质量会更高。",
            }
        )
    if (activity.total_distance_m or 0) >= 16000 and (metrics.avg_heart_rate_bpm or 0) >= 145:
        risks.append(
            {
                "level": "low",
                "title": "长距离负荷已有积累",
                "detail": "这次训练的跑量和内部负荷已经不低，下一次训练应保持克制。",
            }
        )
    if analysis["recovery_quality"] == "limited":
        risks.append(
            {
                "level": "low",
                "title": "工作段之间恢复一般",
                "detail": "恢复段中心率下降不够明显，当前更需要吸收训练而不是继续叠加强度。",
            }
        )
    return risks


def _build_recommendation(
    metrics: ParsedFitMetrics, run_type_guess: str, risks: list[dict], analysis: dict
) -> dict:
    if analysis["fatigue_risk_level"] == "high":
        return {
            "category": "recover_first",
            "detail": "下一次训练建议轻松跑或直接休息，等状态恢复后再上强度。",
            "reason": "规则层的疲劳评分已经偏高，当前优先级是恢复。",
        }
    if run_type_guess == "interval_session":
        return {
            "category": "easy_recovery",
            "detail": "下一次训练建议安排轻松恢复跑或休息，不要连续堆叠质量课。",
            "reason": "这次训练已经包含明确的工作段和恢复段，下一步更重要的是吸收刺激。",
        }
    if metrics.pace_stability_score is not None and metrics.pace_stability_score < 0.6:
        return {
            "category": "control_next",
            "detail": "下一次训练保持轻松，把重点放在从头到尾维持均匀输出。",
            "reason": "本次训练的波动偏大，短期最值得优化的是配速控制。",
        }
    if risks:
        return {
            "category": "recovery_next",
            "detail": "下一次训练建议 30 到 45 分钟轻松跑，不额外增加强度。",
            "reason": "从当前负荷信号看，恢复和控制比继续加压更重要。",
        }
    if run_type_guess == "long_aerobic":
        return {
            "category": "easy_follow_up",
            "detail": "下一次训练可安排短恢复跑，或根据腿部感觉直接休息。",
            "reason": "这次已经完成了足够有意义的有氧跑量。",
        }
    return {
        "category": "continue_aerobic",
        "detail": "下一次训练可以继续安排有氧稳定跑，重点还是均匀发力。",
        "reason": "这次训练整体控制尚可，可以继续积累有氧稳定性。",
    }


def _segment_summary(activity: ParsedFitActivity) -> str:
    segments = activity.segments
    if not segments:
        return "清洗后的记录流里没有提取出稳定的训练结构。"

    described = [
        f"{_segment_type_zh(segment.segment_type)} {round(segment.duration_sec / 60, 1)} 分钟"
        for segment in segments[:4]
    ]
    return "按清洗后的记录流判断，前几段结构为：" + "，".join(described) + "。"


def _segment_type_zh(value: str) -> str:
    mapping = {
        "warmup": "热身",
        "interval": "工作段",
        "recovery": "恢复段",
        "rest": "休息段",
        "cooldown": "放松",
        "steady": "稳定跑",
        "work": "工作段",
    }
    return mapping.get(value, value)


def _training_type_zh(value: str) -> str:
    mapping = {
        "interval_session": "间歇质量课",
        "long_aerobic": "长距离有氧跑",
        "steady_aerobic": "稳定有氧跑",
        "recovery_run": "恢复跑",
        "progression_run": "渐进跑",
        "mixed_run": "混合强度训练",
    }
    return mapping.get(value, value)


def _risk_level_zh(value: str) -> str:
    mapping = {"low": "低", "moderate": "中", "high": "高"}
    return mapping.get(value, value)