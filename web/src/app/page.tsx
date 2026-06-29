"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8010";

// ── types ──────────────────────────────────────────────────────────────────────
type Preset = { id: string; label: string };

type ReportCard = {
  label_id: string;
  sport_type: number;
  summary: { sport: string | null; total_distance_m: number | null; total_timer_time_sec: number | null };
  metrics: {
    avg_pace_sec_per_km: number | null;
    avg_heart_rate_bpm: number | null;
    hr_drift_pct: number | null;
    pace_stability_score: number | null;
  };
  analysis: {
    training_type: string;
    intensity_level: string;
    fatigue_risk_level: string;
    recovery_quality: string;
    ef_ratio: number | null;
    mechanics_stability_score: number | null;
  };
  coach_commentary: {
    source: string; model: string | null;
    summary: string; strengths: string[]; watchouts: string[]; next_steps: string[];
  };
  report: {
    verdict: string;
    recommendation: { category: string; detail: string; reason: string };
    risks: Array<{ level: string; title: string; detail: string }>;
  };
};

type RecordBrief = {
  label_id: string; sport_type: number; date: string;
  distance_m: number | null; duration_sec: number | null; avg_pace_sec_per_km: number | null;
};

type ChatMessage = {
  role: "user" | "assistant";
  text: string;
  card?: ReportCard | null;
  records?: RecordBrief[] | null;
};

const DEFAULT_PRESETS: Preset[] = [
  { id: "analyze_latest", label: "分析我最近一次跑步" },
  { id: "list_recent", label: "看看我最近的训练" },
  { id: "review_week", label: "复盘这周训练" },
];

export default function Home() {
  const [corosSession, setCorosSession] = useState<string | null>(null);
  const [connectNote, setConnectNote] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [presets] = useState<Preset[]>(DEFAULT_PRESETS);

  const scrollRef = useRef<HTMLDivElement>(null);

  // mount: handle OAuth callback + restore session
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("coros");
    const session = params.get("session");
    const apply = async () => {
      if (status === "connected" && session) {
        localStorage.setItem("coros_session", session);
        setCorosSession(session);
        setConnectNote("已成功连接高驰账号 ✓");
        window.history.replaceState({}, "", window.location.pathname);
        setReady(true);
        return;
      }
      if (status === "error") {
        setConnectNote(`授权失败：${params.get("reason") ?? "未知原因"}`);
        window.history.replaceState({}, "", window.location.pathname);
        setReady(true);
        return;
      }
      // restore: verify the stored session is still valid on the backend
      const stored = localStorage.getItem("coros_session");
      if (stored) {
        try {
          const resp = await fetch(`${API_BASE}/api/v1/auth/coros/status?session=${encodeURIComponent(stored)}`);
          const data = await resp.json();
          if (data.connected) {
            setCorosSession(stored);
          } else {
            // backend no longer recognizes this session (e.g. it expired) → reconnect
            localStorage.removeItem("coros_session");
            setConnectNote("高驰连接已失效，请重新连接。");
          }
        } catch {
          // backend unreachable — keep the stored session optimistically
          setCorosSession(stored);
        }
      }
      setReady(true);
    };
    const id = setTimeout(() => void apply(), 0);
    return () => clearTimeout(id);
  }, []);

  // autoscroll on new message
  useEffect(() => {
    const id = setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }), 50);
    return () => clearTimeout(id);
  }, [messages, isSending]);

  function connectCoros() {
    window.location.href = `${API_BASE}/api/v1/auth/coros/login`;
  }
  function disconnectCoros() {
    localStorage.removeItem("coros_session");
    setCorosSession(null);
    setMessages([]);
  }

  async function send(message: string) {
    const text = message.trim();
    if (!text || isSending) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setIsSending(true);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(corosSession ? { "X-Coros-Session": corosSession } : {}),
        },
        body: JSON.stringify({ message: text }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        setMessages((prev) => [...prev, { role: "assistant", text: data.detail ?? "出错了，请重试。" }]);
      } else {
        setMessages((prev) => [...prev, {
          role: "assistant",
          text: data.reply,
          card: data.report_card ?? null,
          records: data.records ?? null,
        }]);
      }
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", text: "无法连接服务，请确认后端已启动。" }]);
    } finally {
      setIsSending(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(input);
  }

  // ── render ────────────────────────────────────────────────────────────────
  return (
    <main className="min-h-screen bg-[linear-gradient(135deg,#0D1B2A_0%,#111D35_60%,#0A1424_100%)] text-stone-100">
      <div className="mx-auto flex min-h-screen w-full max-w-3xl flex-col px-4 py-6 sm:px-6">
        <header className="flex items-center justify-between border-b border-white/10 pb-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-[#00E5CC]">跑步 AI 教练</p>
            <h1 className="mt-1 text-xl font-semibold">{corosSession ? "和你的教练聊聊" : "连接高驰，开始对话"}</h1>
          </div>
          {corosSession && (
            <button onClick={disconnectCoros} className="rounded-full border border-white/15 px-3 py-1.5 text-xs text-stone-300 hover:bg-white/10">
              断开高驰
            </button>
          )}
        </header>

        {!ready ? null : !corosSession ? (
          <AuthGate onConnect={connectCoros} note={connectNote} />
        ) : (
          <ChatView
            messages={messages}
            presets={presets}
            input={input}
            setInput={setInput}
            onSubmit={onSubmit}
            onPreset={(p) => void send(p.id)}
            onRecord={(r) => void send(`分析这次 ${r.label_id}`)}
            isSending={isSending}
            scrollRef={scrollRef}
          />
        )}
      </div>
    </main>
  );
}

// ── Stage 1: authorization gate ──────────────────────────────────────────────
function AuthGate({ onConnect, note }: { onConnect: () => void; note: string | null }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center text-center">
      <div className="max-w-md space-y-6">
        <div className="text-5xl">🏃</div>
        <div className="space-y-2">
          <h2 className="text-2xl font-semibold">把你的运动数据交给 AI 教练</h2>
          <p className="text-sm leading-7 text-stone-400">
            连接你的高驰账号后，教练会读取你的训练数据，用通俗的语言告诉你这次跑得怎么样、
            该注意什么、下一步怎么练。数据用于本次分析，不做诊断。
          </p>
        </div>
        <button
          onClick={onConnect}
          className="w-full rounded-full bg-[#00E5CC] py-3.5 text-sm font-semibold text-stone-900 transition hover:bg-[#00cdb8]"
        >
          连接高驰账号
        </button>
        {note && <p className="text-xs text-[#FF6B4A]">{note}</p>}
        <p className="text-xs text-stone-500">授权通过高驰官方 OAuth 完成，我们不保存你的账号密码。</p>
      </div>
    </div>
  );
}

// ── Stage 2: chat view ────────────────────────────────────────────────────────
function ChatView({
  messages, presets, input, setInput, onSubmit, onPreset, onRecord, isSending, scrollRef,
}: {
  messages: ChatMessage[];
  presets: Preset[];
  input: string;
  setInput: (v: string) => void;
  onSubmit: (e: FormEvent) => void;
  onPreset: (p: Preset) => void;
  onRecord: (r: RecordBrief) => void;
  isSending: boolean;
  scrollRef: React.RefObject<HTMLDivElement | null>;
}) {
  const empty = messages.length === 0;
  return (
    <div className="flex flex-1 flex-col">
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto py-5">
        {empty && (
          <div className="flex flex-col items-center justify-center gap-5 pt-10 text-center">
            <div className="text-4xl">👋</div>
            <p className="max-w-sm text-sm leading-7 text-stone-400">
              你好，我是你的跑步教练。想从哪开始？
            </p>
            <div className="flex flex-col gap-2 w-full max-w-xs">
              {presets.map((p) => (
                <button key={p.id} onClick={() => onPreset(p)}
                  className="rounded-2xl border border-white/12 bg-white/5 px-4 py-3 text-sm text-stone-200 transition hover:border-[#00E5CC]/40 hover:bg-white/8">
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={
              m.role === "user"
                ? "max-w-[85%] rounded-2xl rounded-br-md bg-[#00E5CC] px-4 py-2.5 text-sm text-stone-900"
                : "max-w-[92%] space-y-3"
            }>
              {m.role === "assistant" ? (
                <div className="rounded-2xl rounded-bl-md bg-white/6 px-4 py-3 text-sm leading-7 text-stone-100">
                  {m.text}
                </div>
              ) : (
                m.text
              )}
              {m.card && <ReportCardView card={m.card} />}
              {m.records && m.records.length > 0 && (
                <div className="space-y-2">
                  {m.records.map((r) => (
                    <button key={r.label_id} onClick={() => onRecord(r)}
                      className="flex w-full items-center justify-between rounded-xl border border-white/10 bg-white/4 px-3 py-2 text-left text-xs transition hover:border-[#00E5CC]/40">
                      <span className="text-stone-300">{r.date || "—"}</span>
                      <span className="text-stone-100">{fmtDist(r.distance_m)} · {fmtPace(r.avg_pace_sec_per_km)}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {isSending && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-md bg-white/6 px-4 py-3 text-sm text-stone-400">教练正在分析…</div>
          </div>
        )}
      </div>

      <form onSubmit={onSubmit} className="border-t border-white/10 pt-3">
        <div className="flex items-center gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="问问你的教练，例如：分析我最近一次跑步"
            className="flex-1 rounded-full bg-white/8 border border-white/10 px-4 py-3 text-sm text-stone-100 placeholder-stone-500 focus:outline-none focus:border-[#00E5CC]"
          />
          <button type="submit" disabled={isSending || !input.trim()}
            className="rounded-full bg-[#00E5CC] px-5 py-3 text-sm font-semibold text-stone-900 transition hover:bg-[#00cdb8] disabled:opacity-40">
            发送
          </button>
        </div>
      </form>
    </div>
  );
}

// ── report card embedded in a chat bubble ─────────────────────────────────────
function ReportCardView({ card }: { card: ReportCard }) {
  const a = card.analysis;
  const c = card.coach_commentary;
  return (
    <div className="space-y-3 rounded-2xl border border-white/10 bg-white/5 p-4">
      {/* headline metrics */}
      <div className="grid grid-cols-3 gap-2">
        <Stat label="距离" value={fmtDist(card.summary.total_distance_m)} />
        <Stat label="用时" value={fmtDur(card.summary.total_timer_time_sec)} />
        <Stat label="平均配速" value={fmtPace(card.metrics.avg_pace_sec_per_km)} />
        <Stat label="平均心率" value={fmtBpm(card.metrics.avg_heart_rate_bpm)} />
        <Stat label="心率漂移" value={fmtPct(card.metrics.hr_drift_pct)} />
        <Stat label="训练类型" value={fmtType(a.training_type)} />
      </div>

      {/* assessment pills */}
      <div className="flex flex-wrap gap-2">
        <Pill label={`疲劳 ${fmtType(a.fatigue_risk_level)}`} tone={a.fatigue_risk_level === "high" ? "warn" : "ok"} />
        <Pill label={`强度 ${fmtType(a.intensity_level)}`} tone="neutral" />
        <Pill label={`恢复 ${fmtType(a.recovery_quality)}`} tone="neutral" />
        {a.mechanics_stability_score != null && <Pill label={`动作 ${a.mechanics_stability_score}/100`} tone="neutral" />}
      </div>

      {/* strengths / watchouts / next */}
      <div className="grid gap-2 sm:grid-cols-3">
        <MiniList title="✓ 优点" items={c.strengths} color="text-[#00E5CC]" />
        <MiniList title="! 注意" items={c.watchouts} color="text-[#FF6B4A]" />
        <MiniList title="→ 下一步" items={c.next_steps} color="text-[#9B8EF5]" />
      </div>

      {/* recommendation */}
      <div className="rounded-xl bg-[#00E5CC]/10 border border-[#00E5CC]/20 p-3">
        <p className="text-xs text-[#00E5CC]">下次训练建议</p>
        <p className="mt-1 text-sm leading-6">{card.report.recommendation.detail}</p>
      </div>

      {/* risks */}
      {card.report.risks.length > 0 && (
        <div className="space-y-1.5">
          {card.report.risks.map((r) => (
            <div key={r.title} className="rounded-xl bg-amber-900/15 border border-amber-500/20 px-3 py-2">
              <p className="text-xs font-medium text-amber-200">⚠️ {r.title}</p>
              <p className="mt-0.5 text-xs text-amber-100/70 leading-5">{r.detail}</p>
            </div>
          ))}
        </div>
      )}

      <p className="text-right text-[10px] text-stone-500">
        {c.source === "llm" ? `${c.model ?? "AI"} 解读` : "规则层解读"}
      </p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-black/20 px-2.5 py-2">
      <p className="text-[10px] text-stone-400">{label}</p>
      <p className="mt-0.5 text-sm font-semibold">{value}</p>
    </div>
  );
}

function Pill({ label, tone }: { label: string; tone: "ok" | "warn" | "neutral" }) {
  const cls = tone === "warn"
    ? "bg-[#FF6B4A]/15 text-[#FF6B4A] border-[#FF6B4A]/30"
    : tone === "ok"
    ? "bg-[#00E5CC]/12 text-[#00E5CC] border-[#00E5CC]/25"
    : "bg-white/8 text-stone-300 border-white/12";
  return <span className={`rounded-full border px-2.5 py-1 text-xs ${cls}`}>{label}</span>;
}

function MiniList({ title, items, color }: { title: string; items: string[]; color: string }) {
  return (
    <div className="rounded-xl bg-black/15 p-2.5">
      <p className={`text-xs font-semibold ${color}`}>{title}</p>
      <div className="mt-1.5 space-y-1">
        {items.length > 0 ? items.map((it) => (
          <p key={it} className="text-[11px] leading-5 text-stone-300">{it}</p>
        )) : <p className="text-[11px] text-stone-500">-</p>}
      </div>
    </div>
  );
}

// ── formatters ────────────────────────────────────────────────────────────────
function fmtDist(m: number | null) { return m != null ? `${(m / 1000).toFixed(2)} km` : "-"; }
function fmtDur(sec: number | null) {
  if (sec == null) return "-";
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = Math.round(sec % 60);
  return h > 0 ? `${h}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}` : `${m}:${String(s).padStart(2,"0")}`;
}
function fmtPace(s: number | null) {
  if (s == null) return "-";
  const m = Math.floor(s / 60), sec = Math.round(s % 60);
  return `${sec === 60 ? m + 1 : m}:${String(sec === 60 ? 0 : sec).padStart(2,"0")}/km`;
}
function fmtBpm(v: number | null) { return v != null ? `${Math.round(v)} bpm` : "-"; }
function fmtPct(v: number | null) { return v != null ? `${v.toFixed(1)}%` : "-"; }
function fmtType(v: string) {
  const m: Record<string, string> = {
    interval_session: "间歇课", long_aerobic: "长有氧", steady_aerobic: "稳定有氧",
    recovery_run: "恢复跑", progression_run: "渐进跑", mixed_run: "混合强度",
    easy: "轻松", moderate: "中等", hard: "高强度",
    low: "低", high: "高", good: "良好", limited: "有限", unknown: "未知",
  };
  return m[v] ?? v.replace(/_/g, " ");
}
