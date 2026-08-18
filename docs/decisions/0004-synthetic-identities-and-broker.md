# ADR 0004: Synthetic identities and in-process broker

- **Status:** Accepted for the synthetic proof
- **Date:** August 18, 2026

## Context

An accepted MCP receipt is unsafe until the request is associated with a human and
the separately authenticated Result API can enforce that ownership. The production
OIDC provider, token format, deployment store, and retention policy are not yet
known, but those inputs should not block a synthetic boundary proof.

## Decision

- Authentication adapters produce internal, verified claim objects; headers,
  request IDs, and request bodies are never treated as identity claims directly.
- Agent claims use audience `snowglobe-mcp` and contain both an agent-session subject
  and the authenticated human subject for whom the request is submitted.
- Viewer claims independently use audience `snowglobe-viewer`; the viewer subject
  must equal the request owner on every operation.
- Begin with a test-only in-process broker holding opaque request ID, owner, status,
  expiry, and a private synthetic Arrow source handle.
- Clamp requested TTL to a server maximum. Reject wrong audiences and deny unknown,
  cross-user, cancelled, and expired source access without reflective detail.
- A request may be acknowledged as accepted only after its owner and source have
  been inserted into the broker. The production store must later provide equivalent
  atomicity and appropriate durability.

## Consequences

- The synthetic proof can test audience and ownership behavior without pretending
  to select a production identity provider.
- Request IDs remain correlators rather than bearer credentials.
- The in-process broker cannot support multiple processes, restart durability, or a
  production deployment. Replacing it requires a reviewed store decision.
- Public HTTP and MCP authentication adapters still need implementation before the
  broker is connected to either deployable app.
