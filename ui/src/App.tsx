// The app (PRD 8A): S1 New board, then S2/S3 for a run, and S4 for one item. The run ID
// and item ID live in the URL (?run=<id>&item=<record id>), so a reload or a shared link
// reopens the same screen; no router library. S5 review is ?run=<id>&review=1 and
// S6 approve and export is ?run=<id>&approve=1. S7 run history is ?history=1 and one
// run's events are ?audit=<id> (issue 159). The disclaimer and terms are ?terms=1, linked
// from the footer on every screen (issue 219). In the demo profile (ADR-025, read from
// /healthz) the first screen is the example boards, a banner sits on every screen, and
// screens stop offering what the demo API refuses.
//
// The shell (issue 229): the stage panel on the left, always open (it can be minimised
// to icons, remembered per browser), and the screen on the right. The panel shows the
// stages of a board only when a board is open; the earlier stages open read-only at
// ?run=<id>&stage=brief and ?run=<id>&stage=search.
import { useCallback, useEffect, useState } from "react";
import { ApiError, createBoard, getHealth, getRun } from "./api/client";
import type { BoardItem, Health, RunView } from "./api/types";
import { NewBoard } from "./screens/NewBoard";
import { ApproveScreen } from "./screens/ApproveScreen";
import { HistoryScreen, RunAudit } from "./screens/HistoryScreen";
import { ReviewScreen } from "./screens/ReviewScreen";
import { RunScreen } from "./screens/RunScreen";
import { TermsScreen } from "./screens/TermsScreen";
import { FOOTER_LINE, TERMS_TITLE } from "./content/terms";
import { DEMO_BANNER, DEMO_BANNER_MORE } from "./content/demo";
import { appModeLine, boardModeLine, isMockBoard, MOCK_TAG } from "./content/modes";
import { DemoContext } from "./demo";
import { DemoHome } from "./screens/DemoHome";
import { BriefStage, SearchStage } from "./screens/StageScreens";
import { BoardsScreen } from "./screens/BoardsScreen";
import { SettingsScreen } from "./screens/SettingsScreen";
import type { BoardStage } from "./content/boards";
import { StagePanel, type StageKey } from "./components/StagePanel";

const PANEL_KEY = "refdesk-panel";
const ENDED = new Set(["done", "stopped", "cancelled"]);

function storedMinimised(): boolean {
  try {
    return localStorage.getItem(PANEL_KEY) === "min";
  } catch {
    return false;
  }
}

function param(name: string): string | null {
  return new URLSearchParams(window.location.search).get(name);
}

const currentRun = () => param("run");
const currentItem = () => param("item");
const currentReview = () => param("review") === "1";
const currentApprove = () => param("approve") === "1";
const currentHistory = () => param("history") === "1";
const currentAudit = () => param("audit");
const currentTerms = () => param("terms") === "1";
// Boards (S10) and Settings (S9) are ?boards=1 and ?settings=1 (issue 234).
type Page = "boards" | "settings" | null;
const currentPage = (): Page => (param("boards") === "1" ? "boards" : param("settings") === "1" ? "settings" : null);
const currentStage = (): "brief" | "search" | null => {
  const stage = param("stage");
  return stage === "brief" || stage === "search" ? stage : null;
};

export function App() {
  const [runId, setRunId] = useState<string | null>(currentRun);
  const [itemId, setItemId] = useState<string | null>(currentItem);
  const [reviewing, setReviewing] = useState<boolean>(currentReview);
  const [approving, setApproving] = useState<boolean>(currentApprove);
  const [history, setHistory] = useState<boolean>(currentHistory);
  const [auditId, setAuditId] = useState<string | null>(currentAudit);
  const [terms, setTerms] = useState<boolean>(currentTerms);
  const [page, setPage] = useState<Page>(currentPage);
  const [leftRunId, setLeftRunId] = useState<string | null>(null);
  const [stage, setStage] = useState<"brief" | "search" | null>(currentStage);
  const [panelRun, setPanelRun] = useState<RunView | null>(null);
  const [minimised, setMinimised] = useState<boolean>(storedMinimised);
  const [error, setError] = useState<string | null>(null);
  // null until /healthz answers; a failed check is treated as the full profile.
  const [health, setHealth] = useState<Health | null>(null);
  const demo = health?.profile === "demo";

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() =>
        setHealth({ status: "ok", profile: "full", mode: null, generator: null, judge: null }),
      );
  }, []);

  useEffect(() => {
    const onPop = () => {
      setRunId(currentRun());
      setItemId(currentItem());
      setReviewing(currentReview());
      setApproving(currentApprove());
      setHistory(currentHistory());
      setAuditId(currentAudit());
      setTerms(currentTerms());
      setStage(currentStage());
      setPage(currentPage());
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function show(query: string) {
    window.history.pushState(null, "", query);
    setError(null);
    setTerms(false);
  }

  function openTerms() {
    show("?terms=1");
    setTerms(true);
  }

  // The panel's copy of the open run: fetched when a board opens, polled while the run
  // works, and replaced whenever a board screen loads or changes the run.
  const followRun = useCallback((view: RunView) => setPanelRun(view), []);
  useEffect(() => {
    if (!runId) {
      setPanelRun(null);
      return;
    }
    const id = runId;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const view = await getRun(id);
        if (cancelled) return;
        setPanelRun(view);
        if (!ENDED.has(view.state)) timer = setTimeout(poll, 1000);
      } catch {
        // The screen itself reports a run it cannot load; the panel just has no stages.
      }
    }
    void poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [runId]);

  function toggleMinimised() {
    const next = !minimised;
    setMinimised(next);
    try {
      localStorage.setItem(PANEL_KEY, next ? "min" : "open");
    } catch {
      // Storage blocked: the choice applies to this page view only.
    }
  }

  function open(
    id: string | null,
    item: string | null = null,
    screen: "" | "review" | "approve" | "brief" | "search" = "",
  ) {
    const extra = item
      ? `&item=${encodeURIComponent(item)}`
      : screen === "brief" || screen === "search"
        ? `&stage=${screen}`
        : screen
          ? `&${screen}=1`
          : "";
    show(id ? `?run=${encodeURIComponent(id)}${extra}` : window.location.pathname);
    // Leaving a board for New board: say where it was saved (issue 234).
    setLeftRunId(!id && runId ? runId : null);
    setPage(null);
    setRunId(id);
    setItemId(item);
    setReviewing(screen === "review");
    setApproving(screen === "approve");
    setStage(screen === "brief" || screen === "search" ? screen : null);
    setHistory(false);
    setAuditId(null);
  }

  // Which stage the open screen belongs to, for the panel's "you are here".
  const board = runId && panelRun && panelRun.run_id === runId ? panelRun : null;
  // How this board was made (issue 251): the recorded line replaces "this machine" in the
  // demo, where "this machine" would read as the visitor's own.
  const modeLine = board ? boardModeLine(board) : null;
  let currentKey: StageKey | null = null;
  if (runId) {
    if (stage) currentKey = stage;
    else if (approving) currentKey = board?.read_only ? "export" : "approve";
    else if (reviewing) currentKey = "verify";
    else if (board && !ENDED.has(board.state)) currentKey = "search";
    else currentKey = "shortlist";
  }
  const STAGE_QUERY: Record<StageKey, string> = {
    brief: "&stage=brief",
    search: "&stage=search",
    shortlist: "",
    verify: "&review=1",
    approve: "&approve=1",
    export: "&approve=1",
  };
  function openStage(key: StageKey) {
    if (!runId) return;
    if (key === "brief" || key === "search") open(runId, null, key);
    else if (key === "verify") open(runId, null, "review");
    else if (key === "approve" || key === "export") open(runId, null, "approve");
    else open(runId);
  }
  const boardName = board?.name ?? "";

  function openHistory(audit: string | null = null) {
    show(audit ? `?audit=${encodeURIComponent(audit)}` : "?history=1");
    setPage(null);
    setRunId(null);
    setItemId(null);
    setReviewing(false);
    setApproving(false);
    setHistory(audit === null);
    setAuditId(audit);
  }

  function openPage(next: "boards" | "settings") {
    show(`?${next}=1`);
    setPage(next);
    setRunId(null);
    setItemId(null);
    setReviewing(false);
    setApproving(false);
    setStage(null);
    setHistory(false);
    setAuditId(null);
  }

  // Opening a board from Boards (issue 234): a draft opens on its Shortlist, where the
  // work is picked; the stage panel shows how far its gates have got. An approved or
  // exported board opens at Approve, which has its export or receipt.
  function openBoardAt(id: string, at: BoardStage) {
    if (at === "export" || at === "exported") open(id, null, "approve");
    else open(id);
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
    <DemoContext.Provider value={demo}>
      {demo && (
        <p className="rd-demo-banner" role="note">
          <strong>{DEMO_BANNER}</strong> {DEMO_BANNER_MORE}
        </p>
      )}
      <div className="rd-shell">
        <StagePanel
          minimised={minimised}
          onToggle={toggleMinimised}
          appMode={health ? appModeLine(health) : null}
          links={[
            {
              key: "new",
              label: demo ? "Example boards" : "New board",
              icon: "plus",
              href: window.location.pathname,
              current: !runId && !history && !auditId && !terms && !page,
              onOpen: () => open(null),
            },
            {
              key: "boards",
              label: "Boards",
              icon: "boards",
              href: "?boards=1",
              current: !terms && page === "boards",
              onOpen: () => openPage("boards"),
            },
            {
              key: "settings",
              label: "Settings",
              icon: "settings",
              href: "?settings=1",
              current: !terms && page === "settings",
              onOpen: () => openPage("settings"),
            },
            {
              key: "history",
              label: "Run history",
              icon: "history",
              href: "?history=1",
              current: !terms && (history || auditId !== null),
              onOpen: () => openHistory(),
            },
          ]}
          board={
            runId && board
              ? {
                  name: boardName,
                  run: board,
                  current: currentKey,
                  onOpen: openStage,
                  href: (key) => `?run=${encodeURIComponent(runId)}${STAGE_QUERY[key]}`,
                }
              : undefined
          }
        />
        <div className="rd-shell-main">
      <main>
        {/* Search and check and the board show the full stop banner themselves. */}
        {board && (stage === "brief" || approving || reviewing) && (board.stop_banner || board.keep_local || modeLine) && (
          <div className="rd-board-strip" role="group" aria-label="This board">
            {isMockBoard(board) && <span className="rd-tag rd-tag--mock">{MOCK_TAG}</span>}
            {board.stop_banner && (
              <span className="rd-board-strip-stop">
                <strong>{board.stop_banner}</strong>
                {!board.read_only && " · Nothing was exported"}
              </span>
            )}
            {modeLine && <span className="rd-board-strip-mode">{modeLine}</span>}
            {!demo && board.keep_local && <span className="rd-board-strip-local">This brief stays on this machine</span>}
          </div>
        )}
        {error && (
          <p className="rd-error" role="alert">
            {error}
          </p>
        )}
        {terms ? (
          <TermsScreen />
        ) : page === "boards" ? (
          <BoardsScreen onOpenBoard={openBoardAt} />
        ) : page === "settings" ? (
          <SettingsScreen />
        ) : auditId ? (
          <RunAudit runId={auditId} onBack={() => openHistory()} onOpenBoard={(id) => open(id)} />
        ) : history ? (
          <HistoryScreen onOpenAudit={(id) => openHistory(id)} />
        ) : runId && stage === "brief" ? (
          <BriefStage runId={runId} onOpenRun={(id) => open(id)} />
        ) : runId && stage === "search" ? (
          <SearchStage runId={runId} onResumed={(id) => open(id)} />
        ) : runId && approving ? (
          <ApproveScreen runId={runId} onBack={() => open(runId)} onRun={followRun} />
        ) : runId && reviewing ? (
          <ReviewScreen
            runId={runId}
            onBack={() => open(runId)}
            onContinue={() => open(runId, null, "approve")}
            onRun={followRun}
          />
        ) : runId ? (
          <RunScreen
            runId={runId}
            onNewBoard={() => open(null)}
            onMoreLikeThis={demo ? undefined : moreLikeThis}
            onOpenItem={(item) => open(runId, item)}
            onReview={demo ? undefined : () => open(runId, null, "review")}
            onApprove={demo ? undefined : () => open(runId, null, "approve")}
            onRun={followRun}
            itemId={itemId}
            onCloseItem={() => open(runId)}
          />
        ) : health === null ? (
          <p role="status">Loading…</p>
        ) : (
          <>
            <NewBoard onCreated={open} onOpenRun={(id) => open(id)} onAllBoards={() => openPage("boards")} leftRunId={leftRunId} />
            {demo && <DemoHome onOpenRun={(id) => open(id)} hero={false} />}
          </>
        )}
      </main>
      <footer className="rd-app-footer">
        <span>{FOOTER_LINE}</span> {navLink("?terms=1", TERMS_TITLE, openTerms, terms)}
      </footer>
        </div>
      </div>
    </DemoContext.Provider>
  );
}
