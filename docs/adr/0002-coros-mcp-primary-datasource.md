# ADR 0002: COROS MCP is the primary data source, FIT upload is fallback

**Status:** Accepted
**Date:** 2026-06-29
**Supersedes:** the FIT-upload-only design in the original MVP-PRD / TECHNICAL-SPEC.

## Context

The first prototype only accepted FIT file uploads. Uploading a FIT file has
real friction: the user must find, export, and upload the file after every run.
Most people will not do this repeatedly.

Watch platforms increasingly expose data through MCP (Model Context Protocol) or
OAuth APIs. COROS publishes an MCP endpoint (`https://mcpcn.coros.com/mcp`) that
returns activity detail, lap data, recovery, HRV, sleep, and training load. A
sibling project (`ai-running-coach` SKILL.md) already uses this MCP successfully.

A separate strategic concern: "be a bridge that sends data to an AI" is a thin
moat — a user can paste a screenshot into ChatGPT. The defensible value is the
*quality of the coaching agent* plus *accumulated personal data*, not the
plumbing. The data source choice should serve that: low friction → more data →
better personal baselines.

## Decision

- **Primary path:** `POST /api/v1/activities/analyze` takes a COROS `labelId` +
  `sportType`, calls the COROS MCP (getActivityDetail + queryActivityLapData),
  and runs the same analysis pipeline.
- **Fallback path:** `POST /api/v1/activities/upload` keeps the FIT flow for
  platforms without an MCP.
- Both paths converge on the shared `ParsedFitActivity` domain model (ADR 0003).

## Consequences

**Good**
- Near-zero friction for COROS users → more frequent use → more data to build
  personal baselines, which is the real moat.
- Access to signals a bare FIT file lacks (recovery %, HRV trend, training load).

**Bad / cost**
- Coupling to COROS's (preview) MCP schema. Field names are mapped defensively
  in `coros_adapter.py` with multiple fallbacks per field.
- Auth: standalone server use needs a COROS access token; inside an MCP-capable
  host (Claude Desktop / Kiro CLI) the host handles auth.

**Risks**
- MCP schema changes break the adapter. Mitigation: all field access goes
  through `_safe_*` helpers and the adapter is the only file that knows COROS
  field names.
- Vendor lock-in to one watch brand. Mitigation: ADR 0003's adapter pattern
  keeps Garmin/others a pure add-on.
