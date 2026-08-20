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
    starting: "Preparing in-memory workspace…",
    ready: "In-memory workspace ready",
    failed: "In-memory workspace unavailable",
  };

  let worker: DatabaseWorker | null = null;
  let workerState: WorkerState = "starting";
  let requests: RequestSummary[] | null = null;
  let listFailed = false;
  let requestId = "";
  let lookupFailed = false;
  let lookupPending = false;
  let listLoading = false;
  let loadingRequest: string | null = null;
  let openedRequest: string | null = null;
  let loadFailed = false;
  let viewport: Viewport | null = null;

  onMount(() => {
    startWorkspace();
    void refreshRequests();
    const refreshTimer = window.setInterval(() => void refreshRequests(), 2_000);

    return () => {
      window.clearInterval(refreshTimer);
      worker?.destroy();
      worker = null;
    };
  });

  function startWorkspace(): void {
    worker?.destroy();
    workerState = "starting";
    let nextWorker: DatabaseWorker;
    nextWorker = startDatabaseWorker((state) => {
      if (worker === nextWorker) workerState = state;
    });
    worker = nextWorker;
  }

  async function refreshRequests(): Promise<void> {
    if (listLoading) return;
    listLoading = true;
    try {
      requests = await listRequests();
      listFailed = false;
    } catch {
      listFailed = true;
    } finally {
      listLoading = false;
    }
  }

  async function loadRequest(id: string): Promise<void> {
    const databaseWorker = worker;
    if (!databaseWorker || loadingRequest || viewport) return;

    loadingRequest = id;
    loadFailed = false;
    try {
      const stream = await openResultStream(id);
      await databaseWorker.load(stream, maximumResultBytes);
      viewport = await databaseWorker.viewport(0, maximumViewportRows);
      openedRequest = id;
    } catch {
      databaseWorker.destroy();
      if (worker === databaseWorker) worker = null;
      loadFailed = true;
      startWorkspace();
    } finally {
      loadingRequest = null;
    }
  }

  async function findRequest(): Promise<void> {
    if (lookupPending) return;
    const searchedRequestId = requestId.trim();
    lookupFailed = false;
    lookupPending = true;
    try {
      const item = await getRequest(searchedRequestId);
      requests = [
        item,
        ...(requests ?? []).filter((request) => request.requestId !== item.requestId),
      ];
    } catch {
      lookupFailed = true;
    } finally {
      lookupPending = false;
    }
  }

  function closeResult(): void {
    worker?.destroy();
    worker = null;
    viewport = null;
    openedRequest = null;
    loadFailed = false;
    startWorkspace();
  }
</script>

<main>
  <header>
    <img src={logo} alt="" class="logo" />
    <div>
      <h1>Snowglobe</h1>
      <p>Local Snowflake result viewer</p>
    </div>
  </header>

  <section class="workspace" aria-live="polite">
    <div class:status={true} class:status--ready={workerState === "ready"} class:status--failed={workerState === "failed"} aria-hidden="true"></div>
    <div>
      <h2>{statusLabel[workerState]}</h2>
      <p>
        {viewport
          ? `Showing ${openedRequest ?? "the selected request"} in this tab.`
          : "Choose a short-lived result to load it into the local browser worker."}
      </p>
      {#if workerState === "failed"}
        <button type="button" class="secondary" onclick={startWorkspace}>Retry workspace</button>
      {/if}
    </div>
  </section>

  <section class="results" aria-labelledby="results-heading">
    <div class="section-heading">
      <div>
        <h2 id="results-heading">Recent requests</h2>
      </div>
      <div class="heading-actions">
        {#if requests}<span>{requests.length} available</span>{/if}
        <button type="button" class="secondary" disabled={listLoading} onclick={() => void refreshRequests()}>
          {listLoading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
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
        <button type="submit" disabled={lookupPending}>
          {lookupPending ? "Finding…" : "Find request"}
        </button>
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
    {#if loadFailed}
      <p class="notice" role="alert">The result could not be loaded. You can try again.</p>
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
              <small>Expires <time datetime={request.expiresAt}>{new Date(request.expiresAt).toLocaleString()}</time></small>
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
          <h2 id="viewport-heading">Result preview</h2>
        </div>
        <div class="heading-actions">
          <span>First {viewport.rows.length} rows</span>
          <button type="button" class="secondary" onclick={closeResult}>Close result</button>
        </div>
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
    Results are short-lived and are not restored. Closing this page destroys the
    in-memory workspace.
  </aside>
</main>
