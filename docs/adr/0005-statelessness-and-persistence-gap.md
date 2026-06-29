# ADR 0005: Stateless MVP, persistence deferred

**Status:** Accepted (with known debt)
**Date:** 2026-06-29

## Context

The MVP-PRD lists cross-run trend analysis ("am I improving or accumulating
fatigue?") as a core value. Trend analysis requires storing a user's history.
The current implementation is **stateless**: each `/analyze` or `/upload` call
parses one activity, returns a report, and keeps nothing (FIT bytes are written
to `api/data/uploads/` but never read back for trends).

The original TECHNICAL-SPEC designed a full PostgreSQL schema (users,
activities, activity_samples, derived_metrics, analysis_reports, chat_sessions,
chat_messages). That schema is the eventual target, not the current state.

## Decision

Ship the MVP **stateless**, and treat persistence as the next major workstream
rather than a launch blocker.

Rationale: the immediate goal is to validate that the *single-run analysis* is
good enough that a runner wants to come back. Building the full store before
proving the analysis is worth keeping would be premature.

## Consequences

**Good**
- Faster to validate the core "is the analysis trustworthy?" question.
- No data-protection surface area while still iterating on analysis quality.

**Bad / cost**
- The headline PRD value (personal baselines, trend insights) is not yet
  deliverable. The product today is a single-run analyser.
- COROS context signals that *could* be computed from history (HRV vs 7-day
  baseline) must be supplied by the caller instead.

**Risks**
- Validating retention is hard without trends, which are themselves the
  retention driver — a partial chicken-and-egg. Mitigation: COROS already stores
  history, so an early step is to *read* COROS trend endpoints at analysis time
  (compute baselines on the fly) before building our own store.

## Migration path (when this is superseded)

The full plan — identity from MCP auth, idempotent sync, the trimmed schema,
trend engine, and chat memory — is specified in
[../PERSISTENCE-DESIGN.md](../PERSISTENCE-DESIGN.md). Summary order:

1. Read COROS history endpoints (recovery/HRV/load) at analyze-time to populate
   `CorosContext` automatically (unblocks ADR 0004 L1/L2). No DB needed.
2. Introduce identity (`user_id` from MCP auth) + `activities` +
   `derived_metrics` with an idempotent sync.
3. Add a trend engine that compares the current activity to the user's own
   rolling 7/28-day history.
4. Add `chat_sessions` + `chat_messages` for grounded chat with memory.
