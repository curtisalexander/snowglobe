import { useEffect, useRef, useState } from "react";

import logo from "../../../assets/snowglobe-logo.webp";
import {
  listRequests,
  openResultStream,
  type RequestSummary,
} from "./result-api";
import { startDatabaseWorker, type DatabaseWorker, type WorkerState } from "./worker";
import type { Viewport } from "./viewport";
import "./styles.css";

const maximumFrameBytes = 8 * 1024 * 1024;
const viewportRows = 50;

const statusLabel: Record<WorkerState, string> = {
  starting: "Preparing private workspace…",
  ready: "Private workspace ready",
  failed: "Private workspace unavailable",
};

export function App() {
  const worker = useRef<DatabaseWorker | null>(null);
  const [workerState, setWorkerState] = useState<WorkerState>("starting");
  const [requests, setRequests] = useState<RequestSummary[] | null>(null);
  const [listFailed, setListFailed] = useState(false);
  const [loadingRequest, setLoadingRequest] = useState<string | null>(null);
  const [viewport, setViewport] = useState<Viewport | null>(null);

  useEffect(() => {
    const databaseWorker = startDatabaseWorker(setWorkerState);
    worker.current = databaseWorker;
    return () => {
      worker.current = null;
      databaseWorker.destroy();
    };
  }, []);

  useEffect(() => {
    let active = true;
    listRequests()
      .then((items) => {
        if (active) setRequests(items);
      })
      .catch(() => {
        if (active) setListFailed(true);
      });
    return () => {
      active = false;
    };
  }, []);

  async function loadRequest(requestId: string): Promise<void> {
    const databaseWorker = worker.current;
    if (!databaseWorker || loadingRequest || viewport) return;

    setLoadingRequest(requestId);
    try {
      const stream = await openResultStream(requestId);
      await databaseWorker.load(stream, maximumFrameBytes);
      setViewport(await databaseWorker.viewport(0, viewportRows));
    } catch {
      databaseWorker.destroy();
      setWorkerState("failed");
    } finally {
      setLoadingRequest(null);
    }
  }

  return (
    <main>
      <header>
        <img src={logo} alt="" className="logo" />
        <div>
          <p className="eyebrow">Governed data, kept in view</p>
          <h1>Snowglobe</h1>
          <p className="lede">
            Explore approved Snowflake results without placing result data in an
            AI agent’s context.
          </p>
        </div>
      </header>

      <section className="workspace" aria-live="polite">
        <div className={`status status--${workerState}`} aria-hidden="true" />
        <div>
          <h2>{statusLabel[workerState]}</h2>
          <p>
            {viewport
              ? "The admitted result is available only in this in-memory workspace."
              : "Choose a short-lived result to load it into the private browser worker."}
          </p>
        </div>
      </section>

      <section className="results" aria-labelledby="results-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Authenticated Result API</p>
            <h2 id="results-heading">Recent requests</h2>
          </div>
          {requests && <span>{requests.length} available</span>}
        </div>

        {listFailed && (
          <p className="notice" role="alert">
            A valid viewer session is required to list results.
          </p>
        )}
        {requests?.length === 0 && (
          <p className="notice">No requests are available for this viewer.</p>
        )}
        {requests && requests.length > 0 && (
          <ul className="request-list">
            {requests.map((request) => (
              <li key={request.requestId}>
                <div>
                  <strong>{request.status}</strong>
                  <code>{request.requestId}</code>
                  <small>Expires {new Date(request.expiresAt).toLocaleString()}</small>
                </div>
                <button
                  type="button"
                  disabled={
                    request.status !== "complete" ||
                    workerState !== "ready" ||
                    loadingRequest !== null ||
                    viewport !== null
                  }
                  onClick={() => void loadRequest(request.requestId)}
                >
                  {loadingRequest === request.requestId ? "Loading…" : "Open result"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {viewport && <ResultViewport viewport={viewport} />}

      <aside>
        Results are short-lived, not restored automatically, and never returned
        through the MCP tool. Reloading or closing this page destroys the in-memory
        workspace.
      </aside>
    </main>
  );
}

function ResultViewport({ viewport }: { viewport: Viewport }) {
  return (
    <section className="viewport" aria-labelledby="viewport-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Bounded viewport</p>
          <h2 id="viewport-heading">Result preview</h2>
        </div>
        <span>First {viewport.rows.length} rows</span>
      </div>
      <div className="table-scroll" tabIndex={0}>
        <table>
          <thead>
            <tr>
              {viewport.columns.map((column, index) => (
                <th key={index} scope="col">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {viewport.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, columnIndex) => (
                  <td key={columnIndex}>{cell ?? <span className="null">null</span>}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {viewport.hasMore && (
        <p className="viewport-note">More rows remain in the worker.</p>
      )}
    </section>
  );
}
