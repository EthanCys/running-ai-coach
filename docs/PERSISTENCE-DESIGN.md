# Persistence, User System & Trend Analysis — Design

> Answers the product question: *after a user authorizes their MCP, the agent
> should remember them across sessions — keep chat history, sync their data, and
> analyze how they change over time.* Trends are the core PRD value, so the
> system must stop being stateless.
>
> This doc is the concrete plan that supersedes the stateless MVP
> ([adr/0005](adr/0005-statelessness-and-persistence-gap.md)).

## 1. What "remember the user" actually requires

Four distinct capabilities, often conflated:

| Capability | Question it answers | Storage need |
|---|---|---|
| **Identity** | who is this user, across sessions? | a stable `user_id` tied to their COROS account |
| **Data sync** | what has this user done? | a local copy of their activities + daily health |
| **Chat memory** | what have we discussed before? | conversation history per user |
| **Trend analysis** | how is this user changing? | derived metrics over time + baselines |

You need all four. They share one anchor: a **stable user identity** derived
from the MCP authorization.

## 2. Identity: deriving a user from MCP authorization

When a user authorizes the COROS MCP (OAuth), we get an access token that
represents *their* account. The plan:

1. On first authorized call, fetch a stable account identifier from COROS
   (`queryUserInfo` / device binding). Hash it into our own `user_id`.
2. Store the mapping `user_id ↔ coros_account` once. Never store raw tokens at
   rest unencrypted — encrypt the refresh token, keep access tokens in memory.
3. Every subsequent request resolves to the same `user_id`, so all history,
   chat, and trends attach to one person.

```
COROS OAuth ─→ access token ─→ queryUserInfo ─→ stable account id
                                                      │  hash
                                                      ▼
                                                   user_id  (our anchor)
```

This is the missing piece today: the current `/analyze` endpoint has no notion
of *who* is calling.

## 3. Storage model

Start with PostgreSQL (the TECHNICAL-SPEC already sketches it). Trimmed initial
schema — only what trends + chat need:

```
users
  id (uuid, pk)            -- our user_id
  coros_account_hash       -- stable link to COROS account
  display_name
  created_at
  last_synced_at

oauth_credentials
  user_id (fk)
  provider                 -- 'coros'
  refresh_token_encrypted
  scope
  expires_at

activities
  id (uuid, pk)
  user_id (fk)
  source                   -- 'coros_mcp' | 'fit_upload'
  external_id              -- COROS labelId (dedupe key)
  sport_type
  start_time
  distance_m, duration_sec, ...
  raw_payload_json         -- the parsed activity, for reprocessing
  created_at
  UNIQUE(user_id, source, external_id)   -- idempotent sync

derived_metrics
  activity_id (fk, pk)
  avg_pace_sec_per_km, pace_stability_score, pace_fade_pct,
  hr_drift_pct, ef_ratio, fatigue_risk_level, training_type,
  mechanics_stability_score, ...
  analysis_version         -- bump when formulas change → recompute
  created_at

daily_health            -- the COROS context, stored per day
  user_id (fk)
  date
  recovery_pct, sleep_hrv, resting_hr_bpm,
  training_load_atl, training_load_ctl
  PRIMARY KEY(user_id, date)

chat_sessions
  id (uuid, pk)
  user_id (fk)
  activity_id (fk, nullable)   -- a chat may be about one run or general
  created_at

chat_messages
  id (uuid, pk)
  session_id (fk)
  role                     -- 'user' | 'assistant'
  content
  grounded_context_json    -- the facts shown to the LLM for this turn
  created_at
```

Key design points:
- `UNIQUE(user_id, source, external_id)` makes re-syncing the same COROS
  activity idempotent — sync can run repeatedly without duplicates.
- `analysis_version` lets us recompute old activities when the rule layer
  changes, without losing the raw payload.
- `grounded_context_json` on each message preserves *exactly* which facts the
  LLM was given — essential for the rule-layer-first guarantee
  ([adr/0001](adr/0001-rule-layer-first.md)) and for debugging bad advice.

## 4. Data sync strategy

Two triggers:

- **On login / on demand:** "sync my data" → pull recent COROS activities since
  `last_synced_at` via `querySportRecords`, upsert into `activities`, compute and
  store `derived_metrics`, pull `daily_health` for the window.
- **Backfill (first connect):** pull the last N weeks (default 6, mirroring the
  SKILL.md `baseline_weeks`) to seed baselines immediately.

Sync is incremental and idempotent thanks to the unique constraint. The rule
layer runs once at sync time and the result is stored, so reports are instant on
later views.

```
sync(user) :
  records = MCP.querySportRecords(since=last_synced_at)
  for r in records:
      if upsert activities (user_id, 'coros_mcp', r.labelId):   # new only
          parsed  = coros_adapter.build_parsed_activity(detail, laps)
          metrics = analysis_engine.build_activity_analysis(parsed)
          store derived_metrics(metrics, analysis_version)
  store daily_health(MCP.recovery/hrv/load for window)
  user.last_synced_at = now
```

## 5. Trend analysis — the actual product value

Once `derived_metrics` and `daily_health` accumulate, the trend engine compares
the current run to the user's *own* history (never population averages):

- **Efficiency trend:** EF ratio (speed/HR) for comparable easy runs over 4/8/12
  weeks — is the same pace getting cheaper?
- **Load balance:** rolling 7-day (ATL) vs 28-day (CTL) load and the ratio — the
  real input for L2 adjustments ([adr/0004](adr/0004-three-tier-adjustment.md)).
- **Fatigue trajectory:** HRV and resting HR vs each user's own baseline — this
  is what makes L1 alerts fire *automatically* instead of from manual input.
- **Consistency:** frequency, volume progression vs the 10% rule.

This directly unblocks the two known gaps in AGENTS.md: L1/L2 signals become
auto-computed from stored `daily_health` instead of being typed by the user.

## 6. Chat memory

Per user, scoped to the current session and optionally an activity:

- A chat turn loads: the relevant `derived_metrics` (the facts), a short
  `trend_summary`, and the recent `chat_messages` for continuity.
- The LLM still only sees **grounded facts** — chat memory adds continuity, not
  new numeric authority. Each turn stores its `grounded_context_json`.
- Keep a rolling window of recent messages + a periodically refreshed summary to
  bound context size.

## 7. Privacy & trust (non-negotiable)

- Encrypt refresh tokens at rest; never log tokens or raw PII.
- Store the COROS account as a hash, not the raw account.
- Let a user delete their data (cascade on `user_id`).
- The product is training guidance, not medical advice — persisted history does
  not change that boundary.

## 8. Build order (incremental, each step shippable)

1. **Compute baselines on the fly (no DB yet).** At analyze-time, call COROS
   history endpoints to populate `CorosContext` automatically. This alone
   unblocks automatic L1/L2 alerts and proves the trend value cheaply.
2. **Add identity + activities + derived_metrics.** Introduce `user_id` from MCP
   auth; persist synced activities idempotently.
3. **Add the trend engine** over stored metrics; surface trend insights in the
   report.
4. **Add chat_sessions + chat_messages**; wire grounded chat with memory.
5. **Add daily_health caching + scheduled sync** so trends stay fresh without a
   manual "sync" each time.

Step 1 delivers most of the perceived value (auto fatigue detection + "you're
improving vs 4 weeks ago") before any database exists — do it first.
