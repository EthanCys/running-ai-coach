"""Coach commentary generator.

Builds a structured coach response (summary / strengths / watchouts / next_steps)
from the analysis + report dicts.  When an LLM is configured the prompt is sent
to it; otherwise a deterministic fallback is returned.

Improvements over v1:
- Accepts optional CorosContext so Level 1/2/3 signals enrich the prompt.
- System prompt mirrors SKILL.md constraints (fact-only, separate work/rest
  segments, output must be consistent with rule-layer conclusions).
- Coach personality defaults to "伙伴型 D" from SKILL.md.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING
from urllib import error, request

from app.services.fit_parser import ParsedFitActivity

if TYPE_CHECKING:
    from app.services.coros_adapter import CorosContext


def build_coach_commentary(
    activity: ParsedFitActivity,
    analysis: dict,
    report: dict,
    context: "CorosContext | None" = None,
    history: list[dict] | None = None,
) -> dict:
    prompt_context = _build_prompt_context(activity, analysis, report, context, history)
    fallback = _build_fallback_commentary(activity, analysis, context)

    llm_commentary = _build_llm_commentary(prompt_context)
    if llm_commentary is not None:
        return llm_commentary

    return {
        "source": "fallback",
        "model": None,
        "prompt_context": prompt_context,
        **fallback,
    }


# ── LLM call ─────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一位精英跑步教练，用数据驱动的方式分析训练，风格专业但口语化（伙伴型，参照 SKILL.md 风格 D）。

【思考框架 — 必须按此顺序推理】
1. 定性：先判断这是什么训练（间歇/阈值/长距离/恢复/渐进）。依据是工作段结构，不是全程均值。
2. 分段解读：必须分别解读工作段与恢复段。间歇跑质量看工作段配速 + 组间心率回落，
   绝不能用全程平均配速评判间歇质量。
3. 交叉印证：用多个指标互相验证同一个结论，单一指标不下结论。
   例如「心率漂移低 + 配速稳定 + 触地时间稳定 → 后程没有失代偿」。
4. 给方案：建议必须落到具体的下一次训练（配速区间、距离、强度），不要泛泛而谈。

【量化评级锚点 — 用这些标准解读数据，不要含糊其辞】
- 触地时间 GCT：<200ms 精英 | 200-250ms 良好 | >250ms 待改善
- 垂直振幅比 VR：<6% 优秀 | 6-8% 良好 | >8% 偏高
- 心率漂移 cardiac drift：<5% 优秀 | 5-8% 正常 | >8% 后程失代偿
- HRR-60（1分钟心率回落）：>30bpm 精英 | 20-30 良好 | <20 待观察
- 有氧解耦率：<5% 精英耐力 | 5-10% 达标 | >10% 后程效率衰减
- 步频：170-185spm 是理想区间（配速越快步频越高）

【硬性约束 — 违反即为失败】
1. 只能使用 user 消息中提供的事实；不得虚构任何指标、配速或诊断。没有的数据就说「本次未记录」。
2. 必须区分工作段（interval/work）与恢复段（recovery/cooldown），禁止用全程平均配速判断间歇质量。
3. 结论必须与规则层输出一致（training_type、fatigue_risk_level、recommendation）。
4. Level 1 紧急信号（hrv_drop_pct≥20 或 rhr_spike_bpm≥7）优先于一切建议，必须放在 next_steps 第一条。
5. 不做医疗诊断；禁止「加油」「Fighting」「💪」等空泛激励。
6. 若提供了 history（历史同类训练），必须做纵向对比（如「触地从上次 205ms 降到今天 198ms」）。

【输出格式】
严格返回 JSON，键为 summary、key_findings、strengths、watchouts、next_steps，值均为简体中文：
- summary：字符串，2-4 句话，点明训练定性 + 最重要的 1 个发现。
- key_findings：短句数组，每项是「指标 + 数值 + 评级 + 含义」的完整解读，允许展开细节（每项不超过80字）。
- strengths、watchouts：短句数组（每项不超过40字）。
- next_steps：短句数组，每项是具体可执行的下一步，带配速/距离/强度（每项不超过50字）。
风格：先肯定→再指出问题→最后给方案；口语化，适度 emoji（最多2个）。
允许在 key_findings 里展开专业细节，不要为了简短牺牲专业度。
"""


def _build_llm_commentary(prompt_context: dict) -> dict | None:
    config = _load_llm_config()
    if not config:
        return None

    payload = {
        "model": config["model"],
        "temperature": 0.5,
        "max_tokens": 2000,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(prompt_context, ensure_ascii=False)},
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
        "key_findings": parsed.get("key_findings", [])[:6],
        "strengths": parsed["strengths"][:3],
        "watchouts": parsed["watchouts"][:3],
        "next_steps": parsed["next_steps"][:3],
    }


# ── prompt context ────────────────────────────────────────────────────────────

def _build_prompt_context(
    activity: ParsedFitActivity,
    analysis: dict,
    report: dict,
    context: "CorosContext | None",
    history: list[dict] | None = None,
) -> dict:
    ctx_dict: dict = {}
    if context is not None:
        ctx_dict = {
            "recovery_pct": context.recovery_pct,
            "sleep_hrv": context.sleep_hrv,
            "resting_hr_bpm": context.resting_hr_bpm,
            "training_load_atl": context.training_load_atl,
            "training_load_ctl": context.training_load_ctl,
            "hrv_drop_pct": context.hrv_drop_pct,
            "rhr_spike_bpm": context.rhr_spike_bpm,
        }
        # Remove None values to keep prompt compact
        ctx_dict = {k: v for k, v in ctx_dict.items() if v is not None}

    # Level flags for the LLM to see explicitly
    level1_triggered = bool(
        ctx_dict.get("hrv_drop_pct", 0) >= 20
        or ctx_dict.get("rhr_spike_bpm", 0) >= 7
    )

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
                "segment_type": s.segment_type,
                "duration_sec": s.duration_sec,
                "distance_m": s.distance_m,
                "avg_pace_sec_per_km": s.avg_pace_sec_per_km,
                "avg_heart_rate_bpm": s.avg_heart_rate_bpm,
            }
            for s in activity.segments
        ],
        "per_km_splits": [
            {
                "km": sp.km_index,
                "pace_sec": sp.avg_pace_sec_per_km,
                "hr_bpm": sp.avg_heart_rate_bpm,
                "stance_ms": sp.avg_stance_time_ms,
                "step_len_m": sp.avg_step_length_m,
            }
            for sp in activity.km_splits
        ],
        "split_comparison": _km_split_comparison(activity.km_splits),
        "report": {
            "verdict": report["verdict"],
            "recommendation": report["recommendation"],
            "risks": report["risks"],
        },
        "coros_context": ctx_dict,
        "rating_thresholds": {
            "stance_time_ms": {"elite": "<200", "good": "200-250", "poor": ">250"},
            "vertical_ratio_pct": {"excellent": "<6", "good": "6-8", "high": ">8"},
            "hr_drift_pct": {"excellent": "<5", "normal": "5-8", "decoupled": ">8"},
            "cadence_spm": {"ideal": "170-185"},
            "efficiency_note": "ef_ratio 只在同类训练纵向对比时有意义，单次不作绝对评分。",
        },
        "history": history or [],
        "adjustment_flags": {
            "level1_emergency": level1_triggered,
            "level2_high_fatigue": analysis.get("fatigue_risk_level") == "high",
            "level3_reassess": ctx_dict.get("recovery_pct", 100) < 50,
        },
        "instructions": {
            "role": "running coach, 伙伴风格D",
            "must_separate_work_and_rest": True,
            "work_segment_speed_threshold_mps": 3.7,
            "constraints": [
                "只能使用提供的事实，不得虚构。",
                "必须优先解读工作段与恢复段，不能只看平均配速。",
                "建议必须与规则层输出一致。",
                "若 level1_emergency=true，next_steps 第一条必须是保护建议。",
                "输出语言必须是简体中文。",
            ],
        },
    }


def _km_split_comparison(km_splits: list) -> dict:
    """Compare first vs second half of km splits — reveals negative/positive
    split and mechanical fade. Returns empty dict when insufficient data."""
    paced = [s for s in km_splits if s.avg_pace_sec_per_km is not None]
    if len(paced) < 4:
        return {}
    mid = len(paced) // 2
    first, second = paced[:mid], paced[mid:]

    def _avg(items, attr):
        vals = [getattr(i, attr) for i in items if getattr(i, attr) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    first_pace = _avg(first, "avg_pace_sec_per_km")
    second_pace = _avg(second, "avg_pace_sec_per_km")
    pattern = "unknown"
    if first_pace and second_pace:
        delta = second_pace - first_pace
        if delta <= -5:
            pattern = "negative_split"
        elif delta >= 5:
            pattern = "positive_split"
        else:
            pattern = "even_split"

    return {
        "first_half": {
            "avg_pace_sec": first_pace,
            "avg_hr_bpm": _avg(first, "avg_heart_rate_bpm"),
            "avg_stance_ms": _avg(first, "avg_stance_time_ms"),
        },
        "second_half": {
            "avg_pace_sec": second_pace,
            "avg_hr_bpm": _avg(second, "avg_heart_rate_bpm"),
            "avg_stance_ms": _avg(second, "avg_stance_time_ms"),
        },
        "pace_pattern": pattern,
    }


# ── deterministic fallback ────────────────────────────────────────────────────

def _build_fallback_commentary(
    activity: ParsedFitActivity,
    analysis: dict,
    context: "CorosContext | None",
) -> dict:
    training_type = analysis["training_type"].replace("_", " ")
    recovery_quality = analysis["recovery_quality"].replace("_", " ")
    fatigue = analysis["fatigue_risk_level"]
    ef_ratio = analysis.get("ef_ratio")
    mechanics = analysis.get("mechanics_stability_score")
    recovery_hr_drop_bpm = analysis.get("recovery_hr_drop_bpm")

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
    # Level 1 checks first
    if context and context.hrv_drop_pct is not None and context.hrv_drop_pct >= 20:
        watchouts.append(f"HRV 较基线下降 {context.hrv_drop_pct:.0f}%，今日是生理超载预警。")
    if context and context.rhr_spike_bpm is not None and context.rhr_spike_bpm >= 7:
        watchouts.append(f"静息心率超基线 {context.rhr_spike_bpm:.0f} bpm，恢复质量欠佳。")
    if recovery_quality == "limited":
        watchouts.append("恢复段中心率下降不够明显，说明工作段之间恢复还不够充分。")
    if fatigue in {"moderate", "high"}:
        watchouts.append(f"当前疲劳风险{_risk_level_zh(fatigue)}，下一次训练应保持克制。")
    if activity.metrics.hr_outlier_count > 0:
        watchouts.append(f"本次修正了 {activity.metrics.hr_outlier_count} 个心率噪点。")

    next_steps = []
    # Level 1 takes priority
    if context and (
        (context.hrv_drop_pct or 0) >= 20 or (context.rhr_spike_bpm or 0) >= 7
    ):
        next_steps.append("明天强制安排恢复跑或休息，不要叠加强度训练。")
    elif analysis["training_type"] == "interval_session":
        next_steps.append("下一次训练优先安排轻松恢复跑或休息。")
    elif fatigue == "high":
        next_steps.append("下一次训练建议轻松跑或直接休息，等状态恢复后再上强度。")
    else:
        next_steps.append("下一次训练先保持有氧强度，除非主观状态明显恢复。")
    if recovery_quality == "limited":
        next_steps.append("下一次质量课可以适当拉长恢复时间，或让前几组起跑更克制。")
    if mechanics is not None and mechanics < 75:
        next_steps.append("后程要多关注步频和触地时间，避免动作走形。")

    # key_findings: 用规则层已算好的数值 + 评级锚点，给出量化解读
    key_findings = []
    gct = activity.metrics.avg_stance_time_ms
    if gct is not None and gct > 0:
        rating = "精英" if gct < 200 else ("良好" if gct <= 250 else "待改善")
        key_findings.append(f"触地时间 {gct:.0f}ms（{rating}）。")
    drift = activity.metrics.hr_drift_pct
    if drift is not None:
        rating = "优秀" if drift < 5 else ("正常" if drift <= 8 else "后程失代偿")
        key_findings.append(f"心率漂移 {drift:.1f}%（{rating}），反映后程心血管代价。")
    if ef_ratio is not None:
        key_findings.append(f"有氧效率系数 {ef_ratio}（仅用于同类训练纵向对比）。")
    if mechanics is not None:
        key_findings.append(f"动作稳定性 {mechanics}/100。")
    if recovery_hr_drop_bpm is not None:
        key_findings.append(f"工作段与恢复段心率差 {recovery_hr_drop_bpm}bpm，恢复质量{_recovery_quality_zh(recovery_quality)}。")

    return {
        "summary": summary,
        "key_findings": key_findings[:6],
        "strengths": strengths[:3],
        "watchouts": watchouts[:3],
        "next_steps": next_steps[:3],
    }


# ── utilities ─────────────────────────────────────────────────────────────────

def _load_llm_config() -> dict | None:
    values = {
        "api_key": os.getenv("LLM_API_KEY"),
        "model": os.getenv("LLM_MODEL"),
        "base_url": os.getenv("LLM_BASE_URL"),
    }

    env_path = Path(__file__).resolve().parents[2] / ".env.local"
    if env_path.exists():
        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            k = key.strip()
            if k == "LLM_API_KEY" and not values["api_key"]:
                values["api_key"] = value.strip()
            if k == "LLM_MODEL" and not values["model"]:
                values["model"] = value.strip()
            if k == "LLM_BASE_URL" and not values["base_url"]:
                values["base_url"] = value.strip()

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
        parts = [p.get("text") for p in content if isinstance(p, dict) and isinstance(p.get("text"), str)]
        return "\n".join(parts) if parts else None
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
        start, end = trimmed.find("{"), trimmed.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            payload = json.loads(trimmed[start: end + 1])
        except json.JSONDecodeError:
            return None

    if not isinstance(payload, dict):
        return None
    summary = payload.get("summary")
    strengths, watchouts, next_steps = (
        payload.get("strengths"), payload.get("watchouts"), payload.get("next_steps")
    )
    # key_findings is optional for backward compatibility; default to empty list.
    key_findings = payload.get("key_findings", [])
    if not isinstance(key_findings, list):
        key_findings = []
    if not isinstance(summary, str):
        return None
    if not all(isinstance(v, list) for v in [strengths, watchouts, next_steps]):
        return None
    if not all(isinstance(i, str) for lst in [strengths, watchouts, next_steps] for i in lst):
        return None
    key_findings = [i for i in key_findings if isinstance(i, str)]
    return {
        "summary": summary,
        "key_findings": key_findings,
        "strengths": strengths,
        "watchouts": watchouts,
        "next_steps": next_steps,
    }


def _training_type_zh(value: str) -> str:
    return {
        "interval session": "间歇质量课", "long aerobic": "长距离有氧跑",
        "steady aerobic": "稳定有氧跑", "recovery run": "恢复跑",
        "progression run": "渐进跑", "mixed run": "混合强度训练",
    }.get(value, value)


def _recovery_quality_zh(value: str) -> str:
    return {"good": "良好", "moderate": "一般", "limited": "有限", "unknown": "未知"}.get(value, value)


def _risk_level_zh(value: str) -> str:
    return {"low": "低", "moderate": "中", "high": "高"}.get(value, value)
