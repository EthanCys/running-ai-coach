# ADR 0001: Rule layer computes facts, LLM only translates

**Status:** Accepted
**Date:** 2026-06-29

## Context

The product turns workout data into coaching advice. There are two ways to do
this:

1. Hand the raw data to an LLM and let it both compute and explain.
2. Compute every number deterministically, then let the LLM only put those
   numbers into readable language.

Runners are sensitive to wrong advice. An LLM that invents "your HR drift was
8%" when it was 3% destroys trust on the first session. LLM numeric reasoning is
also non-reproducible — the same run could yield different "facts" each time.

## Decision

The **rule layer is the single source of numeric truth**. The LLM is a language
layer only.

- `analysis_engine.py` and `report_builder.py` compute all facts: training type,
  pace fade, HR drift, fatigue risk, recovery quality, mechanics score, the
  next-run recommendation, and the risk list.
- `coach_commentary.py` receives those facts as a structured `prompt_context`
  and may only rephrase them. The system prompt forbids inventing metrics,
  overriding the rule layer, or making medical claims.
- If the LLM call fails or no LLM is configured, a deterministic fallback in
  `coach_commentary.py` produces the same report shape from the same facts.

## Consequences

**Good**
- Output is reproducible and auditable; every sentence traces to a computed value.
- The product works with zero LLM dependency (fallback path).
- The rule layer is unit-testable in isolation — and is the part that most
  warrants tests.

**Bad / cost**
- More upfront engineering than "just prompt the model."
- Adding a new insight means writing deterministic logic, not just a prompt.

**Risks**
- The rule layer can still be *wrong* (bad thresholds). Mitigation: thresholds
  are documented inline with rationale, and should be calibrated against real
  runner data and ideally a coach's judgment.
- Prompt drift: the LLM may slip in unsupported claims. Mitigation: the system
  prompt enumerates hard constraints, and the response schema is validated.
