# ADR 0000: Architecture Decision Record Index

This directory records the significant architecture decisions for Running AI
Coach. Each ADR is immutable once accepted; to change a decision, add a new ADR
that supersedes the old one.

## Format

Each ADR follows: **Context → Decision → Consequences (good / bad / risks)**.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-rule-layer-first.md) | Rule layer computes facts, LLM only translates | Accepted |
| [0002](0002-coros-mcp-primary-datasource.md) | COROS MCP is the primary data source, FIT upload is fallback | Accepted |
| [0003](0003-shared-domain-model-and-adapters.md) | Shared domain model + adapter pattern for data sources | Accepted |
| [0004](0004-three-tier-adjustment.md) | Three-tier (L1/L2/L3) training adjustment model | Accepted |
| [0005](0005-statelessness-and-persistence-gap.md) | Stateless MVP, persistence deferred | Accepted (with known debt) |
| [0006](0006-standalone-oauth.md) | Standalone web app does its own COROS OAuth (DCR + PKCE) | Accepted |

## Status values

- **Proposed** — under discussion, not yet built.
- **Accepted** — decided and reflected in the code.
- **Superseded by ADR-XXXX** — replaced by a later decision.
