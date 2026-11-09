// S10 Boards (PRD 8A, issue 234): every board, newest first, as equal-size cards. Each
// card shows a cover of up to four open works (empty tiles when fewer), the board's name,
// how far it has got, its stop reason when it stopped (never hidden), and when it was last
// saved. A draft opens on its Shortlist, an approved board at Approve. Everything comes from the
// run list (GET /runs), which never carries the brief; names come from the run ID until
// someone renames the board.
import { type FormEvent, useEffect, useId, useState } from "react";
import { ApiError, listRuns, renameBoard } from "../api/client";
import type { RunSummary } from "../api/types";
import { Icon, type IconName } from "../components/Icon";
import { safeUrl } from "../components/safeUrl";
import { type BoardStage, stageLine } from "../content/boards";
import { useDemo } from "../demo";
import "./screens.css";

const STAGE_ICON: Record<BoardStage, IconName> = {
  cancelled: "dash",
  search: "search",
  exported: "lock",
  export: "export",
  shortlist: "grid",
  verify: "verify",
  approve: "sign",
};

function when(iso: string): string {
  return new Date(iso).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function BoardCard({ row, onOpen, onRenamed }: { row: RunSummary; onOpen: () => void; onRenamed: (row: RunSummary) => void }) {
  const demo = useDemo();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(row.name);
  const [error, setError] = useState<string | null>(null);
  const inputId = useId();
  const tiles = [0, 1, 2, 3].map((i) => row.cover[i]);
  const stage = row.stage as BoardStage;

  async function save(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const view = await renameBoard(row.run_id, name);
      onRenamed({ ...row, name: view.name ?? name });
      setEditing(false);
    } catch (err) {
      setError(`Not renamed: ${err instanceof ApiError ? err.message : String(err)}`);
    }
  }

  return (
    <li className="rd-board-card">
      <a
        className="rd-board-card-open"
        href={`?run=${encodeURIComponent(row.run_id)}`}
        onClick={(event) => {
          event.preventDefault();
          onOpen();
        }}
      >
        <span className="rd-board-cover" aria-hidden="true">
          {tiles.map((tile, i) =>
            tile ? <img key={tile.record_id} src={safeUrl(tile.image_url)} alt="" loading="lazy" /> : <span key={`empty-${i}`} />,
          )}
        </span>
        <span className="rd-board-card-body">
          <strong className="rd-board-card-name">{row.name}</strong>
          <span className={`rd-board-card-stage rd-board-card-stage--${stage}`}>
            <Icon name={STAGE_ICON[stage] ?? "circle"} />
            {stageLine(stage)}
          </span>
          {row.stop_banner && (
            <span className="rd-board-card-stop">
              <Icon name="alert" />
              {row.stop_banner}
            </span>
          )}
          <span className="rd-board-card-when">{`Saved ${when(row.saved_at ?? row.created_at)}`}</span>
        </span>
      </a>
      {!demo && !row.read_only && (
        <div className="rd-board-card-rename">
          {editing ? (
            <form onSubmit={save} aria-label={`Rename ${row.name}`}>
              <label htmlFor={inputId} className="rd-visually-hidden">
                New name
              </label>
              <input id={inputId} value={name} maxLength={80} onChange={(event) => setName(event.target.value)} />
              <button type="submit">Save</button>
              <button type="button" onClick={() => setEditing(false)}>
                Cancel
              </button>
            </form>
          ) : (
            <button type="button" onClick={() => setEditing(true)} aria-label={`Rename ${row.name}`}>
              Rename
            </button>
          )}
          {error && (
            <p className="rd-error" role="alert">
              {error}
            </p>
          )}
        </div>
      )}
    </li>
  );
}

export function BoardsScreen({ onOpenBoard }: { onOpenBoard: (runId: string, stage: BoardStage) => void }) {
  const [rows, setRows] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listRuns()
      .then((list) => {
        if (!cancelled) setRows(list);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="rd-screen" aria-labelledby="boards-title">
      <h1 id="boards-title" className="rd-screen-title">
        Boards
      </h1>
      <p className="rd-note">
        Every board saves as you work. A draft opens on its Shortlist; an approved board opens at Approve. An exported board is read-only.
      </p>
      {error && (
        <p className="rd-error" role="alert">
          The boards did not load: {error}
        </p>
      )}
      {!rows && !error && <p role="status">Loading the boards…</p>}
      {rows && rows.length === 0 && <p>No boards yet. Start one from New board.</p>}
      {rows && rows.length > 0 && (
        <ul className="rd-boards" aria-label="Boards">
          {rows.map((row) => (
            <BoardCard
              key={row.run_id}
              row={row}
              onOpen={() => onOpenBoard(row.run_id, row.stage as BoardStage)}
              onRenamed={(updated) => setRows((list) => (list ?? []).map((r) => (r.run_id === updated.run_id ? updated : r)))}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
