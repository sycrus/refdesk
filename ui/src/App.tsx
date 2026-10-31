// The app (PRD 8A): S1 New board, then S2/S3 for a run, and S4 for one item. The run ID
// and item ID live in the URL (?run=<id>&item=<record id>), so a reload or a shared link
// reopens the same screen; no router library. S5 review is ?run=<id>&review=1 and
// S6 approve and export is ?run=<id>&approve=1. S7 run history is ?history=1 and one
// run's events are ?audit=<id> (issue 159).
import { useEffect, useState } from "react";
import { ApiError, createBoard } from "./api/client";
import type { BoardItem, RunView } from "./api/types";
import { NewBoard } from "./screens/NewBoard";
import { ApproveScreen } from "./screens/ApproveScreen";
import { HistoryScreen, RunAudit } from "./screens/HistoryScreen";
import { ItemDetail } from "./screens/ItemDetail";
import { ReviewScreen } from "./screens/ReviewScreen";
import { RunScreen } from "./screens/RunScreen";

function param(name: string): string | null {
  return new URLSearchParams(window.location.search).get(name);
}

const currentRun = () => param("run");
const currentItem = () => param("item");
const currentReview = () => param("review") === "1";
const currentApprove = () => param("approve") === "1";
const currentHistory = () => param("history") === "1";
const currentAudit = () => param("audit");

export function App() {
  const [runId, setRunId] = useState<string | null>(currentRun);
  const [itemId, setItemId] = useState<string | null>(currentItem);
  const [reviewing, setReviewing] = useState<boolean>(currentReview);
  const [approving, setApproving] = useState<boolean>(currentApprove);
  const [history, setHistory] = useState<boolean>(currentHistory);
  const [auditId, setAuditId] = useState<string | null>(currentAudit);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onPop = () => {
      setRunId(currentRun());
      setItemId(currentItem());
      setReviewing(currentReview());
      setApproving(currentApprove());
      setHistory(currentHistory());
      setAuditId(currentAudit());
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function show(query: string) {
    window.history.pushState(null, "", query);
    setError(null);
  }

  function open(id: string | null, item: string | null = null, screen: "" | "review" | "approve" = "") {
    const extra = item ? `&item=${encodeURIComponent(item)}` : screen ? `&${screen}=1` : "";
    show(id ? `?run=${encodeURIComponent(id)}${extra}` : window.location.pathname);
    setRunId(id);
    setItemId(item);
    setReviewing(screen === "review");
    setApproving(screen === "approve");
    setHistory(false);
    setAuditId(null);
  }

  function openHistory(audit: string | null = null) {
    show(audit ? `?audit=${encodeURIComponent(audit)}` : "?history=1");
    setRunId(null);
    setItemId(null);
    setReviewing(false);
    setApproving(false);
    setHistory(audit === null);
    setAuditId(audit);
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

  function navLink(href: string, text: string, onClick: () => void, current: boolean) {
    return (
      <a
        href={href}
        aria-current={current ? "page" : undefined}
        onClick={(event) => {
          event.preventDefault();
          onClick();
        }}
      >
        {text}
      </a>
    );
  }

  return (
    <>
      <nav className="rd-app-nav" aria-label="refdesk">
        {navLink(window.location.pathname, "New board", () => open(null), !runId && !history && !auditId)}
        {navLink("?history=1", "Run history", () => openHistory(), history || auditId !== null)}
      </nav>
      <main>
        {error && (
          <p className="rd-error" role="alert">
            {error}
          </p>
        )}
        {auditId ? (
          <RunAudit runId={auditId} onBack={() => openHistory()} onOpenBoard={(id) => open(id)} />
        ) : history ? (
          <HistoryScreen onOpenAudit={(id) => openHistory(id)} />
        ) : runId && approving ? (
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
    </>
  );
}
