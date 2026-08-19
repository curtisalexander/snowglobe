# Snowglobe documentation

## Current project documents

- [Implementation plan](../PLAN.md) — current single-analyst scope, milestones, and progress.
- [Architecture decisions](decisions/README.md) — accepted technical and security decisions; these take precedence when older source material differs.
- [Local threat model](threat-model.md) — loopback trust boundary, data flows, limitations, and required evidence.
- [Snowflake configuration](configuration.md) — current `connections.toml` contract.
- [Querido reuse audit](querido-reference.md) — pinned source review and reuse boundary.

## Retained source material

- [Original architecture proposal](architecture-proposal.md)
- [Data-context guardrails](data-context-guardrails.html)
- [Leader guide](data-context-leader-guide.html)

The proposal and companion HTML documents are retained as the brainstorming/design input from which the plan was developed. They are not rewritten after every implementation decision. `PLAN.md` and accepted ADRs are authoritative when later decisions refine or supersede that source material.
