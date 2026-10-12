// The app (PRD 8A): S1 New board, then S2/S3 for a run. The run ID lives in the URL
// (?run=<id>), so a reload or a shared link reopens the same board; no router library.
import { useEffect, useState } from "react";
import { ApiError, createBoard } from "./api/client";
import type { BoardItem, RunView } from "./api/types";
import { NewBoard } from "./screens/NewBoard";
import { RunScreen } from "./screens/RunScreen";

function currentRun(): string | null {
  return new URLSearchParams(window.location.search).get("run");
}

export function App() {
  const [runId, setRunId] = useState<string | null>(currentRun);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onPop = () => setRunId(currentRun());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function open(id: string | null) {
    window.history.pushState(null, "", id ? `?run=${encodeURIComponent(id)}` : window.location.pathname);
    setError(null);
    setRunId(id);
  }

  async function moreLikeThis(run: RunView, item: BoardItem) {
    // A new board anchored on this work, with the same brief and constraints.
    try {
      const created = await createBoard({ ...(run.request ?? { brief: "" }), anchor_id: item.record.id });
      open(created.run_id);
    } catch (err) {
      setError(`More like this failed: ${err instanceof ApiError ? err.message : String(err)}`);
    }
  }

  return (
    <main>
      {error && (
        <p className="rd-error" role="alert">
          {error}
        </p>
      )}
      {runId ? (
        <RunScreen runId={runId} onNewBoard={() => open(null)} onMoreLikeThis={moreLikeThis} />
      ) : (
        <NewBoard onCreated={open} />
      )}
    </main>
  );
}
