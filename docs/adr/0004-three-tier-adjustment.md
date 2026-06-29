# ADR 0004: Three-tier (L1/L2/L3) training adjustment model

**Status:** Accepted
**Date:** 2026-06-29

## Context

A single run does not justify changing a training plan. A bad session can come
from poor sleep, heat, or a bad mood. But some signals *do* warrant immediate
action (a large HRV drop suggesting physiological overload). The product needs a
principled way to decide *when* a signal should change behaviour.

The sibling `ai-running-coach` SKILL.md encodes a three-level model drawn from
Hansons / Daniels / 80-20 theory. We adopt the same tiers, scaled to a
single-activity analysis context.

## Decision

`_build_adjustment_alerts()` in `activities.py` emits alerts at three tiers:

- **L1 — emergency (per-activity, single trigger fires):**
  `hrv_drop_pct >= 20%` or `resting_hr_spike >= 7 bpm` vs baseline →
  recommend an immediate recovery day. L1 always takes priority in
  `coach_commentary` next-steps.
- **L2 — weekly review (the main adjustment layer):**
  rule-layer `fatigue_risk_level == "high"`, or short/long load ratio
  `ATL/CTL > 1.3` → suggest reducing next-session pace 5–10 s/km or volume 10%.
- **L3 — cycle reassessment (informational):**
  `recovery_pct < 50%` → flag that pace zones should be re-evaluated at the next
  4-week cycle boundary.

The thresholds live in code with inline rationale and mirror the SKILL.md values.

## Consequences

**Good**
- The system reacts proportionally: it doesn't panic on one ordinary run, but it
  does flag genuine overload.
- Tiers map cleanly to coaching theory, which makes advice explainable.

**Bad / cost**
- Thresholds are currently global constants, not personalised.

**Risks**
- The L1/L2 signals (HRV drop, RHR spike, ATL/CTL) are **not yet auto-fetched**.
  They are passed in from the request (and, in the UI, typed by the user). Until
  the backend pulls these from the COROS MCP automatically, L1/L2 only fire when
  the caller supplies the data. This is the top follow-up item — see AGENTS.md
  "Known gaps".
- Global thresholds may misfire for outlier physiologies. Mitigation: future
  personalisation once per-user baselines exist (ADR 0005).
