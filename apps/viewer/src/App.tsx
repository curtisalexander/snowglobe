import { useEffect, useState } from "react";

import logo from "../../../assets/snowglobe-logo.webp";
import { startDatabaseWorker, type WorkerState } from "./worker";
import "./styles.css";

const statusLabel: Record<WorkerState, string> = {
  starting: "Preparing private workspace…",
  ready: "Private workspace ready",
  failed: "Private workspace unavailable",
};

export function App() {
  const [workerState, setWorkerState] = useState<WorkerState>("starting");

  useEffect(() => {
    const worker = startDatabaseWorker(setWorkerState);
    return () => worker.destroy();
  }, []);

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
            No result is loaded. The first milestone connects this in-memory
            DuckDB worker to an authenticated synthetic Arrow stream.
          </p>
        </div>
      </section>

      <aside>
        Results are short-lived, not restored automatically, and never returned
        through the MCP tool.
      </aside>
    </main>
  );
}
