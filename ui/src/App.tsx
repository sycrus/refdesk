// The app (PRD 8A): S1 New board, then S2/S3 for a run, and S4 for one item. The run ID
// and item ID live in the URL (?run=<id>&item=<record id>), so a reload or a shared link
// reopens the same screen; no router library.
import { useEffect, useState } from "react";
import { ApiError, createBoard } from "./api/client";
import type { BoardItem, RunView } from "./api/types";
import { NewBoard } from "./screens/NewBoard";
import { ItemDetail } from "./screens/ItemDetail";
import { RunScreen } from "./screens/RunScreen";

function currentRun(): string | null {
  return new URLSearchParams(window.location.search).get("run");
}

function currentItem(): string | null {
  return new URLSearchParams(window.location.search).get("item");
}

export function App() {
  const [runId, setRunId] = useState<string | null>(currentRun);
  const [itemId, setItemId] = useState<string | null>(currentItem);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onPop = () => {
      setRunId(currentRun());
      setItemId(currentItem());
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function open(id: string | null, item: string | null = null) {
    const query = id
      ? `?run=${encodeURIComponent(id)}${item ? `&item=${encodeURIComponent(item)}` : ""}`
      : window.location.pathname;
    window.history.pushState(null, "", query);
    setError(null);
    setRunId(id);
    setItemId(item);
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
      {runId && itemId ? (
        <ItemDetail runId={runId} itemId={itemId} onBack={() => open(runId)} />
      ) : runId ? (
        <RunScreen
          runId={runId}
          onNewBoard={() => open(null)}
          onMoreLikeThis={moreLikeThis}
          onOpenItem={(item) => open(runId, item)}
        />
      ) : (
        <NewBoard onCreated={open} />
      )}
    </main>
  );
}
