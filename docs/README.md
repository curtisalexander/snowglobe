# Snowglobe documentation

## Current project documents

- [Implementation plan](../PLAN.md) — current single-analyst scope, milestones, and progress.
- [Architecture decisions](decisions/README.md) — accepted technical and security decisions; these take precedence when older source material differs.
- [Local threat model](threat-model.md) — loopback trust boundary, data flows, limitations, and required evidence.
- [Snowflake configuration](configuration.md) — current `connections.toml` contract.
- [Getting started](getting-started.md) — clone, Snowflake setup, preflight, launch,
  Amp, Codex, Claude Code, Continue.dev, Pi, and the first result-free agent flow.
- [Developer guide](developer-guide.md) — implemented architecture, end-to-end call
  paths, module ownership, invariants, tests, and a practical code-review order.
- [Result-free CLI decision](decisions/0013-result-free-cli-adapter.md) — how Pi and
  other shell-only agents use the running MCP service without adding a data channel.
- [Pi integration](pi-integration.md) — install and use Snowglobe's native Pi tools.
- [Constrained MVP runbook](constrained-mvp-runbook.md) — exact non-production setup,
  operation, lifecycle, shutdown, restart, and evidence procedure for Gate 5.
- [Connected MVP evidence template](mvp-evidence-template.md) — value-free checklist
  to copy outside the repository for the connected campaign.
- [Querido reuse audit](querido-reference.md) — pinned source review and reuse boundary.

## Retained source material

- [Original architecture proposal](architecture-proposal.md)
- [Data-context guardrails](data-context-guardrails.html)
- [Leader guide](data-context-leader-guide.html)

The proposal and companion HTML documents are retained as the brainstorming/design input from which the plan was developed. They are not rewritten after every implementation decision. `PLAN.md` and accepted ADRs are authoritative when later decisions refine or supersede that source material.
