from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import error, request

from app.services.fit_parser import ParsedFitActivity


def build_coach_commentary(activity: ParsedFitActivity, analysis: dict, report: dict) -> dict:
    prompt_context = _build_prompt_context(activity, analysis, report)
    fallback = _build_fallback_commentary(activity, analysis)

    llm_commentary = _build_llm_commentary(prompt_context)
    if llm_commentary is not None:
        return llm_commentary

    return {
        "source": "fallback",
        "model": None,
        "prompt_context": prompt_context,
        "summary": fallback["summary"],
        "strengths": fallback["strengths"],
        "watchouts": fallback["watchouts"],
        "next_steps": fallback["next_steps"],
    }


def _build_llm_commentary(prompt_context: dict) -> dict | None:
    config = _load_llm_config()
    if not config:
        return None

    payload = {
        "model": config["model"],
        "temperature": 0.3,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一位严谨的中文跑步教练。只能使用提供给你的事实，不得虚构数据。"
                    "必须区分工作段、恢复段、热身和放松，不能只看全程平均配速。"
                    "严格返回 JSON，键必须是 summary、strengths、watchouts、next_steps。"
                    "summary 是中文字符串；strengths、watchouts、next_steps 都必须是中文短句数组。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt_context, ensure_ascii=False),
            },
        ],
    }

    api_request = request.Request(
        config["base_url"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(api_request, timeout=40) as response:
            response_payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except (TimeoutError, error.URLError, error.HTTPError, json.JSONDecodeError):
        return None

    content = _extract_message_content(response_payload)
    if content is None:
        return None

    parsed = _parse_llm_json(content)
    if parsed is None:
        return None

    return {
        "source": "llm",
        "model": config["model"],
        "prompt_context": prompt_context,
        "summary": parsed["summary"],
        "strengths": parsed["strengths"][:3],
        "watchouts": parsed["watchouts"][:3],
        "next_steps": parsed["next_steps"][:3],
    }


def _load_llm_config() -> dict | None:
    values = {
        "api_key": os.getenv("LLM_API_KEY"),
        "model": os.getenv("LLM_MODEL"),
        "base_url": os.getenv("LLM_BASE_URL"),
        "provider": os.getenv("LLM_PROVIDER"),
    }

    env_path = Path(__file__).resolve().parents[2] / ".env.local"
    if env_path.exists():
        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            normalized_key = key.strip()
            if normalized_key == "LLM_API_KEY" and not values["api_key"]:
                values["api_key"] = value.strip()
            if normalized_key == "LLM_MODEL" and not values["model"]:
                values["model"] = value.strip()
            if normalized_key == "LLM_BASE_URL" and not values["base_url"]:
                values["base_url"] = value.strip()
            if normalized_key == "LLM_PROVIDER" and not values["provider"]:
                values["provider"] = value.strip()

    if not values["api_key"] or not values["model"] or not values["base_url"]:
        return None

    return values


def _extract_message_content(payload: dict) -> str | None:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [part.get("text") for part in content if isinstance(part, dict) and isinstance(part.get("text"), str)]
        return "\n".join(text_parts) if text_parts else None
    return None


def _parse_llm_json(content: str) -> dict | None:
    trimmed = content.strip()
    if trimmed.startswith("```"):
        lines = trimmed.splitlines()
        if len(lines) >= 3:
            trimmed = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(trimmed)
    except json.JSONDecodeError:
        start = trimmed.find("{")
        end = trimmed.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            payload = json.loads(trimmed[start : end + 1])
        except json.JSONDecodeError:
            return None

    if not isinstance(payload, dict):
        return None
    summary = payload.get("summary")
    strengths = payload.get("strengths")
    watchouts = payload.get("watchouts")
    next_steps = payload.get("next_steps")
    if not isinstance(summary, str):
        return None
    if not all(isinstance(value, list) for value in [strengths, watchouts, next_steps]):
        return None
    if not all(isinstance(item, str) for value in [strengths, watchouts, next_steps] for item in value):
        return None

    return {
        "summary": summary,
        "strengths": strengths,
        "watchouts": watchouts,
        "next_steps": next_steps,
    }


def _build_prompt_context(activity: ParsedFitActivity, analysis: dict, report: dict) -> dict:
    return {
        "summary": {
            "sport": activity.sport,
            "distance_m": activity.total_distance_m,
            "moving_time_sec": activity.total_timer_time_sec,
            "lap_count": activity.lap_count,
        },
        "metrics": {
            "avg_pace_sec_per_km": activity.metrics.avg_pace_sec_per_km,
            "avg_heart_rate_bpm": activity.metrics.avg_heart_rate_bpm,
            "pace_stability_score": activity.metrics.pace_stability_score,
            "pace_fade_pct": activity.metrics.pace_fade_pct,
            "hr_drift_pct": activity.metrics.hr_drift_pct,
            "avg_running_cadence_spm": activity.metrics.avg_running_cadence_spm,
            "avg_step_length_m": activity.metrics.avg_step_length_m,
            "avg_stance_time_ms": activity.metrics.avg_stance_time_ms,
        },
        "analysis": analysis,
        "segments": [
            {
                "segment_type": segment.segment_type,
                "duration_sec": segment.duration_sec,
                "distance_m": segment.distance_m,
                "avg_pace_sec_per_km": segment.avg_pace_sec_per_km,
                "avg_heart_rate_bpm": segment.avg_heart_rate_bpm,
            }
            for segment in activity.segments
        ],
        "report": {
            "verdict": report["verdict"],
            "recommendation": report["recommendation"],
            "risks": report["risks"],
        },
        "instructions": {
            "role": "running coach",
            "skill_principles": {
                "must_separate_work_and_rest": True,
                "do_not_classify_by_average_pace_only": True,
                "work_segment_speed_threshold_mps": 3.7,
                "work_segment_distance_threshold_m": 500,
                "short_interval_distance_threshold_m": 300,
            },
            "constraints": [
                "只能使用提供的事实。",
                "不得虚构指标、阈值或诊断。",
                "必须优先解读工作段与恢复段。",
                "建议必须与规则层输出一致。",
                "输出语言必须是中文。",
            ],
        },
    }


def _build_fallback_commentary(activity: ParsedFitActivity, analysis: dict) -> dict:
    training_type = analysis["training_type"].replace("_", " ")
    recovery_quality = analysis["recovery_quality"].replace("_", " ")
    fatigue = analysis["fatigue_risk_level"]
    ef_ratio = analysis.get("ef_ratio")
    mechanics = analysis.get("mechanics_stability_score")

    ef_str = f"（有氧效率系数 {ef_ratio}）" if ef_ratio is not None else ""
    summary = (
        f"这次训练更像{_training_type_zh(training_type)}{ef_str}。"
        f"动作稳定性为 {mechanics}/100。"
        f"工作段之间的恢复质量为{_recovery_quality_zh(recovery_quality)}，当前疲劳风险为{_risk_level_zh(fatigue)}。"
    )

    strengths = []
    if ef_ratio is not None and fatigue == "low":
        strengths.append("本次训练的有氧效率基线已经建立，适合和后续同类训练做纵向对比。")
    if mechanics is not None and mechanics >= 80:
        strengths.append("整堂课的动作稳定性保持得不错。")
    if (activity.metrics.hr_drift_pct or 0) < 3:
        strengths.append("心率漂移较低，说明后程代价控制得比较好。")

    watchouts = []
    if recovery_quality == "limited":
        watchouts.append("恢复段中心率下降不够明显，说明工作段之间恢复还不够充分。")
    if fatigue == "moderate":
        watchouts.append("当前内部负荷已经不低，下一次训练应保持克制。")
    if fatigue == "high":
        watchouts.append("当前疲劳信号偏高，下一步应优先恢复而不是继续上强度。")
    if activity.metrics.hr_outlier_count > 0:
        watchouts.append(f"这份文件里修正了 {activity.metrics.hr_outlier_count} 个心率噪点。")

    next_steps = []
    if analysis["training_type"] == "interval_session":
        next_steps.append("下一次训练优先安排轻松恢复跑或休息。")
    else:
        next_steps.append("下一次训练先保持有氧强度，除非主观状态明显恢复。")
    if recovery_quality == "limited":
        next_steps.append("下一次质量课可以适当拉长恢复时间，或让前几组起跑更克制。")
    if mechanics is not None and mechanics < 75:
        next_steps.append("后程要多关注步频和触地时间，避免动作走形。")

    return {
        "summary": summary,
        "strengths": strengths[:3],
        "watchouts": watchouts[:3],
        "next_steps": next_steps[:3],
    }


def _training_type_zh(value: str) -> str:
    mapping = {
        "interval session": "间歇质量课",
        "long aerobic": "长距离有氧跑",
        "steady aerobic": "稳定有氧跑",
        "recovery run": "恢复跑",
        "progression run": "渐进跑",
        "mixed run": "混合强度训练",
    }
    return mapping.get(value, value)


def _recovery_quality_zh(value: str) -> str:
    mapping = {"good": "良好", "moderate": "一般", "limited": "有限", "unknown": "未知"}
    return mapping.get(value, value)


def _risk_level_zh(value: str) -> str:
    mapping = {"low": "低", "moderate": "中", "high": "高"}
    return mapping.get(value, value)