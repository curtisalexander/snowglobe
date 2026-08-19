# ADR 0012: Use plain Svelte for the local viewer UI

- **Status:** Accepted
- **Date:** August 19, 2026

## Context

ADR 0001 selected React for the viewer. The implemented interface is a small,
single-page local application without routing or server rendering. Its result API,
Arrow ingestion, bounded viewport, and dedicated DuckDB worker are framework-independent
TypeScript modules. React's component runtime and hook ceremony do not simplify this
UI.

## Decision

- Replace React with Svelte and TypeScript for the viewer UI.
- Keep Vite as the development server and production bundler.
- Use plain Svelte rather than SvelteKit; the viewer does not need routing, server-side
  rendering, or a JavaScript application server.
- Preserve the dedicated worker lifecycle and bounded main-thread viewport contract.

This supersedes only the React choice in ADR 0001.

## Consequences

- Viewer state and lifecycle behavior use Svelte assignments and lifecycle hooks
  instead of React hooks and setter callbacks.
- Existing framework-independent API, Arrow, viewport, and worker modules remain
  unchanged.
- Svelte reduces UI source and runtime overhead, but DuckDB-Wasm remains the dominant
  production asset.
- The browser data-handling and loopback network boundaries are unchanged.
