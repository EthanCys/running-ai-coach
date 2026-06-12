"use client";

import { FormEvent, useState } from "react";

type UploadResponse = {
  activity_id: string;
  filename: string;
  status: string;
  message: string;
  stored_path: string;
  summary: {
    manufacturer: string | null;
    product_name: string | null;
    sport: string | null;
    sub_sport: string | null;
    start_time: string | null;
    total_elapsed_time_sec: number | null;
    total_timer_time_sec: number | null;
    total_distance_m: number | null;
    total_calories: number | null;
    lap_count: number;
    record_count: number;
  };
  metrics: {
    avg_pace_sec_per_km: number | null;
    pace_stability_score: number | null;
    avg_heart_rate_bpm: number | null;
    max_heart_rate_bpm: number | null;
    avg_running_cadence_spm: number | null;
    pace_fade_pct: number | null;
    hr_drift_pct: number | null;
    avg_step_length_m: number | null;
    avg_stance_time_ms: number | null;
    hr_outlier_count: number;
    interval_count: number;
    recovery_count: number;
    rest_count: number;
  };
  analysis: {
    training_type: string;
    ef_ratio: number | null;
    hr_drift_pct: number | null;
    recovery_quality: string;
    recovery_hr_drop_bpm: number | null;
    fatigue_risk_level: string;
    mechanics_stability_score: number | null;
  };
  coach_commentary: {
    source: string;
    model: string | null;
    prompt_context: Record<string, unknown>;
    summary: string;
    strengths: string[];
    watchouts: string[];
    next_steps: string[];
  };
  report: {
    verdict: string;
    run_type_guess: string;
    findings: Array<{
      title: string;
      detail: string;
      evidence: Record<string, string | number | null>;
    }>;
    risks: Array<{
      level: string;
      title: string;
      detail: string;
    }>;
    recommendation: {
      category: string;
      detail: string;
      reason: string;
    };
  };
  laps: Array<{
    lap_index: number | null;
    start_time: string | null;
    end_time: string | null;
    total_elapsed_time_sec: number | null;
    total_timer_time_sec: number | null;
    total_distance_m: number | null;
    total_calories: number | null;
    avg_speed_mps: number | null;
    avg_heart_rate_bpm: number | null;
    max_heart_rate_bpm: number | null;
    avg_running_cadence_spm: number | null;
  }>;
  segments: Array<{
    segment_type: string;
    start_offset_sec: number | null;
    end_offset_sec: number | null;
    duration_sec: number;
    distance_m: number | null;
    avg_pace_sec_per_km: number | null;
    avg_heart_rate_bpm: number | null;
  }>;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResponse | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("请先选择一个 FIT 文件。");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    setIsUploading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/activities/upload`, {
        method: "POST",
        body: formData,
      });

      const data: unknown = await response.json();
      if (!response.ok) {
        setResult(null);
        const detail = hasDetailMessage(data) ? data.detail : undefined;
        setError(detail ?? "上传失败。");
        return;
      }

      setResult(data as UploadResponse);
    } catch {
      setResult(null);
      setError("无法连接后端服务，请确认 API 已启动后再试。");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <main className="min-h-screen overflow-hidden bg-[radial-gradient(circle_at_top_left,_rgba(255,255,255,0.9),_rgba(255,255,255,0)_38%),linear-gradient(135deg,_#f8f0dc_0%,_#f2e3c6_36%,_#e6d0a8_100%)] text-stone-900">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 py-8 sm:px-10 lg:px-12">
        <header className="flex flex-col gap-4 border-b border-stone-900/10 pb-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-stone-600">
              跑步 AI 教练
            </p>
            <h1 className="mt-2 max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">
              上传 FIT 文件，把手表原始数据转成可读、可解释的训练报告。
            </h1>
          </div>
        </header>

        <section className="grid flex-1 gap-8 py-10 lg:grid-cols-[0.8fr_1.2fr]">
          <div className="space-y-6">
            <section className="rounded-[2rem] border border-stone-900/10 bg-white/75 p-6 shadow-[0_18px_40px_rgba(88,55,12,0.08)] backdrop-blur">
              <p className="text-sm font-semibold uppercase tracking-[0.22em] text-stone-500">
                上传训练文件
              </p>
              <h2 className="mt-3 text-2xl font-semibold">上传一次训练，查看完整分析</h2>
              <p className="mt-3 text-sm leading-7 text-stone-700">
                上传 FIT 文件后，系统会清洗数据、识别训练结构、计算关键指标，并给出中文教练式解读。
              </p>

              <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
                <label className="flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-[1.5rem] border border-dashed border-stone-900/20 bg-stone-50/80 px-6 text-center transition hover:border-stone-900/40 hover:bg-stone-50">
                  <span className="text-sm font-semibold uppercase tracking-[0.2em] text-stone-500">
                    选择 FIT 文件
                  </span>
                  <span className="mt-3 text-base text-stone-700">
                    {file ? file.name : "点击选择，或拖入你的训练导出文件。"}
                  </span>
                  <input
                    className="hidden"
                    type="file"
                    accept=".fit"
                    onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  />
                </label>

                <button
                  className="w-full rounded-full bg-stone-950 px-5 py-3 text-sm font-semibold uppercase tracking-[0.2em] text-stone-50 transition hover:bg-stone-800 disabled:cursor-not-allowed disabled:bg-stone-500"
                  disabled={isUploading}
                  type="submit"
                >
                  {isUploading ? "正在上传..." : "开始分析"}
                </button>
              </form>

              {error ? (
                <p className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
              ) : null}
            </section>
          </div>

          <div className="space-y-6">
            <section className="rounded-[2rem] border border-stone-900/10 bg-stone-950 p-6 text-stone-50 shadow-[0_24px_70px_rgba(39,24,0,0.25)]">
              <p className="text-sm font-semibold uppercase tracking-[0.24em] text-amber-200/80">
                训练报告
              </p>

              {result ? (
                <div className="mt-6 space-y-4">
                  <div className="rounded-2xl bg-white/8 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs uppercase tracking-[0.2em] text-stone-300">教练解读</p>
                      <span className="rounded-full border border-white/10 bg-white/8 px-2.5 py-1 text-xs text-stone-200">
                        {result.coach_commentary.source === "llm"
                          ? `模型${result.coach_commentary.model ? `: ${result.coach_commentary.model}` : ""}`
                          : "本地回退"}
                      </span>
                    </div>
                    <p className="mt-3 text-lg font-medium leading-8 text-stone-50">{result.coach_commentary.summary}</p>
                    <div className="mt-4 grid gap-4 md:grid-cols-3">
                      <CommentaryList title="优点" items={result.coach_commentary.strengths} />
                      <CommentaryList title="注意点" items={result.coach_commentary.watchouts} />
                      <CommentaryList title="下一步" items={result.coach_commentary.next_steps} />
                    </div>
                  </div>

                  <div className="rounded-2xl bg-amber-100 p-4 text-stone-900">
                    <p className="text-xs uppercase tracking-[0.2em] text-stone-600">下一次训练建议</p>
                    <p className="mt-2 text-base font-medium leading-7">
                      {result.report.recommendation.detail}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-stone-700">
                      {result.report.recommendation.reason}
                    </p>
                  </div>

                  <div className="rounded-2xl bg-white/8 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-stone-300">关键指标</p>
                    <div className="mt-3 grid gap-4 md:grid-cols-2">
                      <DataCard label="训练类型" value={formatSegmentType(result.analysis.training_type)} />
                      <DataCard label="有氧效率系数" value={formatEfRatio(result.analysis.ef_ratio)} />
                      <DataCard label="疲劳风险" value={formatSegmentType(result.analysis.fatigue_risk_level)} />
                      <DataCard label="恢复质量" value={formatSegmentType(result.analysis.recovery_quality)} />
                      <DataCard label="恢复段心率下降" value={formatBpmDelta(result.analysis.recovery_hr_drop_bpm)} />
                      <DataCard label="动作稳定性" value={formatScore100(result.analysis.mechanics_stability_score)} />
                    </div>
                  </div>

                  <div className="rounded-2xl bg-white/8 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-stone-300">训练概览</p>
                    <div className="mt-3 grid gap-4 md:grid-cols-2">
                      <DataCard label="距离" value={formatDistance(result.summary.total_distance_m)} />
                      <DataCard label="移动时间" value={formatDuration(result.summary.total_timer_time_sec)} />
                      <DataCard label="平均配速" value={formatPace(result.metrics.avg_pace_sec_per_km)} />
                      <DataCard label="平均心率" value={formatBpm(result.metrics.avg_heart_rate_bpm)} />
                      <DataCard label="配速稳定性" value={formatScore(result.metrics.pace_stability_score)} />
                      <DataCard label="心率漂移" value={formatPercent(result.metrics.hr_drift_pct)} />
                    </div>
                  </div>

                  <div className="rounded-2xl bg-white/8 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-stone-300">结论</p>
                    <p className="mt-2 text-base leading-7 text-stone-100">{result.report.verdict}</p>
                  </div>

                  <div className="rounded-2xl bg-white/8 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-stone-300">关键发现</p>
                    <div className="mt-3 space-y-3">
                      {result.report.findings.map((finding) => (
                        <div key={finding.title} className="rounded-xl bg-black/15 p-3">
                          <p className="font-medium text-stone-100">{finding.title}</p>
                          <p className="mt-1 text-sm leading-6 text-stone-300">{finding.detail}</p>
                          <div className="mt-2 flex flex-wrap gap-2">
                            {Object.entries(finding.evidence).map(([key, value]) => (
                              <span
                                key={key}
                                className="rounded-full border border-white/10 bg-white/8 px-2.5 py-1 text-xs text-stone-200"
                              >
                                {formatEvidenceLabel(key, value)}
                              </span>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-2xl bg-white/8 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs uppercase tracking-[0.2em] text-stone-300">更多结构化信息</p>
                    </div>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <DataCard label="步频" value={formatSpm(result.metrics.avg_running_cadence_spm)} />
                      <DataCard label="修正心率噪点" value={String(result.metrics.hr_outlier_count)} />
                    </div>
                  </div>

                  {result.report.risks.length > 0 ? (
                    <div className="rounded-2xl bg-white/8 p-4">
                      <p className="text-xs uppercase tracking-[0.2em] text-stone-300">风险提示</p>
                      <div className="mt-3 space-y-3">
                        {result.report.risks.map((risk) => (
                          <div key={`${risk.level}-${risk.title}`} className="rounded-xl bg-black/15 p-3">
                            <div className="flex items-center justify-between gap-3">
                              <p className="font-medium text-stone-100">{risk.title}</p>
                              <span className="rounded-full bg-amber-200/15 px-2.5 py-1 text-xs uppercase tracking-[0.16em] text-amber-200">
                                {risk.level}
                              </span>
                            </div>
                            <p className="mt-1 text-sm leading-6 text-stone-300">{risk.detail}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="mt-6 rounded-2xl bg-white/8 p-6 text-sm leading-7 text-stone-300">
                  上传 FIT 文件后，这里会显示完整训练分析结果。
                </div>
              )}
            </section>

          </div>
        </section>
      </div>
    </main>
  );
}

function DataCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-white/8 p-4">
      <p className="text-xs uppercase tracking-[0.2em] text-stone-300">{label}</p>
      <p className="mt-2 text-lg font-semibold text-stone-50">{value}</p>
    </div>
  );
}

function CommentaryList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-xl bg-black/15 p-3">
      <p className="text-xs uppercase tracking-[0.18em] text-stone-300">{title}</p>
      <div className="mt-2 space-y-2">
        {items.length > 0 ? (
          items.map((item) => (
            <p key={`${title}-${item}`} className="text-sm leading-6 text-stone-200">
              {item}
            </p>
          ))
        ) : (
          <p className="text-sm leading-6 text-stone-400">-</p>
        )}
      </div>
    </div>
  );
}

function hasDetailMessage(payload: unknown): payload is { detail?: string } {
  return typeof payload === "object" && payload !== null && "detail" in payload;
}

function formatDistance(distanceM: number | null): string {
  if (distanceM == null) return "-";
  return `${(distanceM / 1000).toFixed(2)} 公里`;
}

function formatDuration(durationSec: number | null): string {
  if (durationSec == null) return "-";
  const hours = Math.floor(durationSec / 3600);
  const minutes = Math.floor((durationSec % 3600) / 60);
  const seconds = Math.round(durationSec % 60);
  if (hours > 0) {
    return `${hours}小时 ${minutes}分 ${seconds}秒`;
  }
  return `${minutes}分 ${seconds}秒`;
}

function formatPace(paceSecPerKm: number | null): string {
  if (paceSecPerKm == null) return "-";
  const minutes = Math.floor(paceSecPerKm / 60);
  const roundedSeconds = Math.round(paceSecPerKm % 60);
  const normalizedMinutes = roundedSeconds === 60 ? minutes + 1 : minutes;
  const normalizedSeconds = roundedSeconds === 60 ? 0 : roundedSeconds;
  return `${normalizedMinutes}:${normalizedSeconds.toString().padStart(2, "0")} /公里`;
}

function formatBpm(value: number | null): string {
  if (value == null) return "-";
  return `${Math.round(value)} bpm`;
}

function formatSpm(value: number | null): string {
  if (value == null) return "-";
  return `${Math.round(value)} spm`;
}

function formatPercent(value: number | null): string {
  if (value == null) return "-";
  return `${value.toFixed(2)}%`;
}

function formatScore(value: number | null): string {
  if (value == null) return "-";
  return `${(value * 100).toFixed(0)}/100`;
}

function formatScore100(value: number | null): string {
  if (value == null) return "-";
  return `${value.toFixed(1)}/100`;
}

function formatEfRatio(value: number | null): string {
  if (value == null) return "-";
  return value.toFixed(4);
}

function formatBpmDelta(value: number | null): string {
  if (value == null) return "-";
  return `${value.toFixed(1)} bpm 下降`;
}

function formatEvidenceLabel(key: string, value: string | number | null): string {
  if (value == null) {
    return `${humanizeKey(key)}: -`;
  }
  if (key.includes("distance")) {
    return `${humanizeKey(key)}: ${formatDistance(Number(value))}`;
  }
  if (key.includes("time")) {
    return `${humanizeKey(key)}: ${formatDuration(Number(value))}`;
  }
  if (key.includes("pace_fade") || key.includes("drift")) {
    return `${humanizeKey(key)}: ${formatPercent(Number(value))}`;
  }
  if (key.includes("stability_score")) {
    if (key.includes("mechanics") || key.includes("cardio")) {
      return `${humanizeKey(key)}: ${formatScore100(Number(value))}`;
    }
    return `${humanizeKey(key)}: ${formatScore(Number(value))}`;
  }
  if (key === "ef_ratio") {
    return `${humanizeKey(key)}: ${formatEfRatio(Number(value))}`;
  }
  if (key.includes("heart_rate") || key.includes("hr")) {
    if (key.includes("drop")) {
      return `${humanizeKey(key)}: ${formatBpmDelta(Number(value))}`;
    }
    return `${humanizeKey(key)}: ${formatBpm(Number(value))}`;
  }
  if (key.includes("efficiency")) {
    return `${humanizeKey(key)}: ${formatScore100(Number(value))}`;
  }
  if (key.includes("count")) {
    return `${humanizeKey(key)}: ${Math.round(Number(value))}`;
  }
  if (key.includes("cadence")) {
    return `${humanizeKey(key)}: ${formatSpm(Number(value))}`;
  }
  return `${humanizeKey(key)}: ${String(value)}`;
}

function formatSegmentType(value: string): string {
  const mapping: Record<string, string> = {
    interval_session: "间歇质量课",
    long_aerobic: "长距离有氧跑",
    steady_aerobic: "稳定有氧跑",
    recovery_run: "恢复跑",
    progression_run: "渐进跑",
    mixed_run: "混合强度训练",
    low: "低",
    moderate: "中",
    high: "高",
    good: "良好",
    limited: "有限",
    unknown: "未知",
  };
  return mapping[value] ?? value.replaceAll("_", " ");
}

function humanizeKey(key: string): string {
  const mapping: Record<string, string> = {
    ef_ratio: "有氧效率系数",
    recovery_hr_drop_bpm: "恢复段心率下降",
    mechanics_stability_score: "动作稳定性",
    fatigue_risk_level: "疲劳风险",
    interval_count: "工作段数量",
    recovery_count: "恢复段数量",
    rest_count: "休息段数量",
    hr_outlier_count: "修正心率噪点",
    total_distance_m: "距离",
    total_timer_time_sec: "移动时间",
    pace_fade_pct: "后程配速变化",
    pace_stability_score: "配速稳定性",
    hr_drift_pct: "心率漂移",
    avg_heart_rate_bpm: "平均心率",
  };
  return mapping[key] ?? key.replaceAll("_", " ");
}
