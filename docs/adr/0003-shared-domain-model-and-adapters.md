# ADR 0003: Shared domain model + adapter pattern for data sources

**Status:** Accepted
**Date:** 2026-06-29

## Context

We now have two data sources (COROS MCP, FIT upload) and want a third later
(Garmin, Strava, Apple Health). If each source had its own analysis path, every
new source would require re-implementing pace fade, HR drift, fatigue scoring,
etc. — and the outputs would drift apart.

The sibling `ai-running-coach` project solved this with an abstract tool layer
(`ADAPTERS.md`): core logic calls `GET_SPORT_RECORDS`, and a per-device adapter
maps it to the concrete API. We adopt the same idea in code.

## Decision

A single **shared domain model**, `ParsedFitActivity` (with `ParsedFitMetrics`,
`ParsedFitLap`, `ParsedFitSegment`), defined in `fit_parser.py`, is the contract
between data sources and the analysis pipeline.

- Each data source has **one adapter** whose only job is to produce a
  `ParsedFitActivity`:
  - `fit_parser.parse_fit_activity(path)` — FIT files.
  - `coros_adapter.build_parsed_activity(detail, lap_data, ctx)` — COROS MCP.
- `analysis_engine`, `report_builder`, and `coach_commentary` depend only on
  `ParsedFitActivity`. They never know where the data came from.
- Source-specific extras that don't fit the FIT model (recovery %, HRV trend)
  travel in a separate `CorosContext` object, kept out of the core model.

Adding Garmin = write `garmin_adapter.py` that returns `ParsedFitActivity`.
Nothing downstream changes.

## Consequences

**Good**
- New data sources are additive and isolated.
- One place to test/trust the analysis, regardless of source.

**Bad / cost**
- The model is named `ParsedFit*` for historical reasons even though it's now
  source-agnostic. Renaming is deferred to avoid churn; documented here so it
  doesn't confuse readers.
- Source-specific richness (e.g. per-second streams) must either fit the model
  or ride in a side channel like `CorosContext`.

**Risks**
- The lowest-common-denominator model could lose useful source-specific detail.
  Mitigation: the `*Context` side-channel pattern lets a source pass extra
  signals without polluting the shared model.
