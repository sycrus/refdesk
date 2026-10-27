// The app (PRD 8A): S1 New board, then S2/S3 for a run, and S4 for one item. The run ID
// and item ID live in the URL (?run=<id>&item=<record id>), so a reload or a shared link
// reopens the same screen; no router library. S5 review is ?run=<id>&review=1 and
// S6 approve and export is ?run=<id>&approve=1.
import { useEffect, useState } from "react";
import { ApiError, createBoard } from "./api/client";
import type { BoardItem, RunView } from "./api/types";
import { NewBoard } from "./screens/NewBoard";
import { ApproveScreen } from "./screens/ApproveScreen";
import { ItemDetail } from "./screens/ItemDetail";
import { ReviewScreen } from "./screens/ReviewScreen";
import { RunScreen } from "./screens/RunScreen";

function currentRun(): string | null {
  return new URLSearchParams(window.location.search).get("run");
}

function currentItem(): string | null {
  return new URLSearchParams(window.location.search).get("item");
}

function currentReview(): boolean {
  return new URLSearchParams(window.location.search).get("review") === "1";
}

function currentApprove(): boolean {
  return new URLSearchParams(window.location.search).get("approve") === "1";
}

export function App() {
  const [runId, setRunId] = useState<string | null>(currentRun);
  const [itemId, setItemId] = useState<string | null>(currentItem);
  const [reviewing, setReviewing] = useState<boolean>(currentReview);
  const [approving, setApproving] = useState<boolean>(currentApprove);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onPop = () => {
      setRunId(currentRun());
      setItemId(currentItem());
      setReviewing(currentReview());
      setApproving(currentApprove());
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function open(id: string | null, item: string | null = null, screen: "" | "review" | "approve" = "") {
    const extra = item ? `&item=${encodeURIComponent(item)}` : screen ? `&${screen}=1` : "";
    const query = id ? `?run=${encodeURIComponent(id)}${extra}` : window.location.pathname;
    window.history.pushState(null, "", query);
    setError(null);
    setRunId(id);
    setItemId(item);
    setReviewing(screen === "review");
    setApproving(screen === "approve");
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
      {runId && approving ? (
        <ApproveScreen runId={runId} onBack={() => open(runId)} />
      ) : runId && reviewing ? (
        <ReviewScreen runId={runId} onBack={() => open(runId)} onContinue={() => open(runId, null, "approve")} />
      ) : runId && itemId ? (
        <ItemDetail runId={runId} itemId={itemId} onBack={() => open(runId)} />
      ) : runId ? (
        <RunScreen
          runId={runId}
          onNewBoard={() => open(null)}
          onMoreLikeThis={moreLikeThis}
          onOpenItem={(item) => open(runId, item)}
          onReview={() => open(runId, null, "review")}
          onApprove={() => open(runId, null, "approve")}
        />
      ) : (
        <NewBoard onCreated={open} />
      )}
    </main>
  );
}
