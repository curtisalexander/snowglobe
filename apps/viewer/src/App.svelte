<script lang="ts">
  import { onMount } from "svelte";

  import logo from "../../../assets/snowglobe-logo.webp";
  import { maximumResultBytes, maximumViewportRows } from "./mvp-limits";
  import {
    getRequest,
    listRequests,
    openResultStream,
    type RequestSummary,
  } from "./result-api";
  import "./styles.css";
  import type { Viewport } from "./viewport";
  import { startDatabaseWorker, type DatabaseWorker, type WorkerState } from "./worker";

  const statusLabel: Record<WorkerState, string> = {
    starting: "Preparing private workspace…",
    ready: "Private workspace ready",
    failed: "Private workspace unavailable",
  };

  let worker: DatabaseWorker | null = null;
  let workerState: WorkerState = "starting";
  let requests: RequestSummary[] | null = null;
  let listFailed = false;
  let requestId = "";
  let lookupFailed = false;
  let loadingRequest: string | null = null;
  let viewport: Viewport | null = null;

  onMount(() => {
    worker = startDatabaseWorker((state) => (workerState = state));
    void listRequests()
      .then((items) => (requests = items))
      .catch(() => (listFailed = true));

    return () => {
      worker?.destroy();
      worker = null;
    };
  });

  async function loadRequest(id: string): Promise<void> {
    const databaseWorker = worker;
    if (!databaseWorker || loadingRequest || viewport) return;

    loadingRequest = id;
    try {
      const stream = await openResultStream(id);
      await databaseWorker.load(stream, maximumResultBytes);
      viewport = await databaseWorker.viewport(0, maximumViewportRows);
    } catch {
      databaseWorker.destroy();
      workerState = "failed";
    } finally {
      loadingRequest = null;
    }
  }

  async function findRequest(): Promise<void> {
    lookupFailed = false;
    try {
      const item = await getRequest(requestId.trim());
      requests = [
        item,
        ...(requests ?? []).filter((request) => request.requestId !== item.requestId),
      ];
    } catch {
      lookupFailed = true;
    }
  }
</script>

<main>
  <header>
    <img src={logo} alt="" class="logo" />
    <div>
      <p class="eyebrow">Governed data, kept in view</p>
      <h1>Snowglobe</h1>
      <p class="lede">
        Explore approved Snowflake results without placing result data in an AI agent’s
        context.
      </p>
    </div>
  </header>

  <section class="workspace" aria-live="polite">
    <div class:status={true} class:status--ready={workerState === "ready"} class:status--failed={workerState === "failed"} aria-hidden="true"></div>
    <div>
      <h2>{statusLabel[workerState]}</h2>
      <p>
        {viewport
          ? "The admitted result is available only in this in-memory workspace."
          : "Choose a short-lived result to load it into the private browser worker."}
      </p>
    </div>
  </section>

  <section class="results" aria-labelledby="results-heading">
    <div class="section-heading">
      <div>
        <p class="eyebrow">Local viewer backend</p>
        <h2 id="results-heading">Recent requests</h2>
      </div>
      {#if requests}<span>{requests.length} available</span>{/if}
    </div>

    <form class="request-lookup" onsubmit={(event) => { event.preventDefault(); void findRequest(); }}>
      <label for="request-id">Open a request ID returned by MCP</label>
      <div>
        <input
          id="request-id"
          bind:value={requestId}
          pattern={"[A-Za-z0-9_-]{20,32}"}
          required
          autocomplete="off"
          spellcheck="false"
        />
        <button type="submit">Find request</button>
      </div>
    </form>
    {#if lookupFailed}
      <p class="notice" role="alert">
        That request is not available in this local Snowglobe session.
      </p>
    {/if}
    {#if listFailed}
      <p class="notice" role="alert">The local viewer backend is unavailable.</p>
    {/if}
    {#if requests?.length === 0}
      <p class="notice">No requests are available in this local session.</p>
    {/if}
    {#if requests && requests.length > 0}
      <ul class="request-list">
        {#each requests as request (request.requestId)}
          <li>
            <div>
              <strong>{request.status}</strong>
              <code>{request.requestId}</code>
              <small>Expires {new Date(request.expiresAt).toLocaleString()}</small>
            </div>
            <button
              type="button"
              disabled={request.status !== "complete" || workerState !== "ready" || loadingRequest !== null || viewport !== null}
              onclick={() => void loadRequest(request.requestId)}
            >
              {loadingRequest === request.requestId ? "Loading…" : "Open result"}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  {#if viewport}
    <section class="viewport" aria-labelledby="viewport-heading">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Bounded viewport</p>
          <h2 id="viewport-heading">Result preview</h2>
        </div>
        <span>First {viewport.rows.length} rows</span>
      </div>
      <!-- svelte-ignore a11y_no_noninteractive_tabindex (scroll region must be keyboard reachable) -->
      <div class="table-scroll" role="region" aria-label="Result table" tabindex="0">
        <table>
          <thead>
            <tr>
              {#each viewport.columns as column, columnIndex (columnIndex)}
                <th scope="col">{column}</th>
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each viewport.rows as row, rowIndex (rowIndex)}
              <tr>
                {#each row as cell, columnIndex (columnIndex)}
                  <td>{#if cell === null}<span class="null">null</span>{:else}{cell}{/if}</td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      {#if viewport.hasMore}
        <p class="viewport-note">More rows remain in the worker.</p>
      {/if}
    </section>
  {/if}

  <aside>
    Results are short-lived, not restored automatically, and never returned through the
    MCP tool. Reloading or closing this page destroys the in-memory workspace.
  </aside>
</main>
