// Lightbox (PRD 8A, issue 232): one work, large, over the board, with its evidence panel
// beside it. It replaces S4 Item detail as a page; the URL still names the item
// (?run=<id>&item=<record id>), so a reload or a shared link reopens it.
//
// Keys: ← → move between works, Esc closes, Z zooms (drag to pan), I shows or hides the
// details, K keeps, D takes a work off the shortlist. Keys are ignored while typing in a
// field. Focus stays inside while it is open and goes back to where it was on close.
//
// Keeping a flagged work needs a note (the G3 rule, Joe 2026-11-09): K opens a note field,
// and the note is recorded as the review decision for that work. Images follow the card's
// rule (showsImage): only works the source states are open, from the source's own host.
import { type FormEvent, type PointerEvent, useEffect, useId, useRef, useState } from "react";
import type { BoardItem, RunView } from "../api/types";
import { AttributionStatus } from "../generated/wording";
import { ItemEvidence } from "../screens/ItemEvidence";
import { showsImage } from "./EvidenceCard";
import { safeUrl } from "./safeUrl";
import { StatusMarks } from "./StatusMarks";
import "./Lightbox.css";

export interface LightboxProps {
  run: RunView;
  items: BoardItem[]; // the board's order; ← → move through it
  itemId: string;
  onShow: (itemId: string) => void;
  onClose: () => void;
  // Absent when the shortlist cannot change (demo, approved, exported, still running).
  shortlist?: {
    operator: string;
    setOperator: (name: string) => void;
    keep: (itemId: string, keep: boolean) => Promise<void>;
    keepWithNote: (itemId: string, note: string) => Promise<void>;
  };
}

const flagged = (item: BoardItem) => item.attribution_status !== AttributionStatus.VERIFIED;

export function Lightbox({ run, items, itemId, onShow, onClose, shortlist }: LightboxProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const [details, setDetails] = useState(true);
  const [zoom, setZoom] = useState(false);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  const [noteOpen, setNoteOpen] = useState(false);
  const [askName, setAskName] = useState(false); // fixed when the form opens, not per keystroke
  const [intent, setIntent] = useState<"keep" | "drop">("keep"); // what the form will do
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();
  const noteId = useId();
  const nameId = useId();

  const found = items.findIndex((i) => i.record.id === itemId);
  const index = Math.max(0, found);
  const item = items[index];

  // Focus: in on open, back to where it was on close; the page behind does not scroll.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.body.style.overflow = overflow;
      opener?.focus?.();
    };
  }, []);

  // A new work starts unzoomed, with no open note.
  useEffect(() => {
    setZoom(false);
    setPan({ x: 0, y: 0 });
    setNoteOpen(false);
    setNote("");
    setError(null);
  }, [itemId]);

  if (found < 0 || !item) {
    return (
      <div className="rd-lightbox" role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={(e) => e.key === "Escape" && onClose()}>
        <div className="rd-lightbox-stage">
          <h2 id={titleId} className="rd-visually-hidden">
            Work not found
          </h2>
          <p role="alert">This board has no item {itemId}.</p>
          <button ref={closeRef} type="button" className="rd-lightbox-btn" onClick={onClose}>
            Close <kbd>Esc</kbd>
          </button>
        </div>
      </div>
    );
  }
  const { record } = item;
  const alt = [record.title, record.artist].filter(Boolean).join(", ") || `Artwork ${record.id}`;
  const recordUrl = safeUrl(record.record_url);

  function step(by: number) {
    if (items.length === 0) return;
    onShow(items[(index + by + items.length) % items.length].record.id);
  }

  async function run_(action: () => Promise<void>) {
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(`Not saved: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  function keep() {
    if (!shortlist || item.selected) return;
    if (!shortlist.operator.trim() || flagged(item)) {
      setAskName(!shortlist.operator.trim()); // a name is needed first; a flagged work also needs a note
      setIntent("keep");
      setNoteOpen(true);
      return;
    }
    void run_(() => shortlist.keep(item.record.id, true));
  }

  function drop() {
    if (!shortlist || !item.selected) return;
    if (!shortlist.operator.trim()) {
      setAskName(true);
      setIntent("drop");
      setNoteOpen(true);
      return;
    }
    void run_(() => shortlist.keep(item.record.id, false));
  }

  // After the note form closes, keys go back to the lightbox (the form's buttons are gone).
  function closeNote() {
    setNoteOpen(false);
    dialogRef.current?.focus();
  }

  function submitNote(event: FormEvent) {
    event.preventDefault();
    if (!shortlist) return;
    if (!shortlist.operator.trim()) {
      setError("Enter your name first: it is recorded with what you keep.");
      return;
    }
    if (intent === "drop") {
      void run_(async () => {
        await shortlist.keep(item.record.id, false);
        closeNote();
      });
      return;
    }
    if (flagged(item)) {
      if (!note.trim()) {
        setError("Keeping a work that needs a human check needs a note.");
        return;
      }
      void run_(async () => {
        await shortlist.keepWithNote(item.record.id, note.trim());
        closeNote();
      });
    } else {
      void run_(async () => {
        await shortlist.keep(item.record.id, true);
        closeNote();
      });
    }
  }

  function onKeyDown(event: React.KeyboardEvent) {
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes((event.target as HTMLElement).tagName);
    if (event.key === "Escape") {
      event.preventDefault();
      if (noteOpen) closeNote();
      else onClose();
      return;
    }
    if (event.key === "Tab") {
      const focusable = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>("button, a[href], input, textarea, [tabindex]:not([tabindex='-1'])") ?? [],
      ).filter((el) => !el.hasAttribute("disabled") && el.offsetParent !== null);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
      return;
    }
    if (typing || event.ctrlKey || event.metaKey || event.altKey) return;
    const key = event.key.toLowerCase();
    if (event.key === "ArrowRight") step(1);
    else if (event.key === "ArrowLeft") step(-1);
    else if (key === "z") setZoom((z) => !z);
    else if (key === "i") setDetails((d) => !d);
    else if (key === "k") keep();
    else if (key === "d") drop();
    else return;
    event.preventDefault();
  }

  function onPointerDown(event: PointerEvent<HTMLImageElement>) {
    if (!zoom) return;
    drag.current = { x: event.clientX - pan.x, y: event.clientY - pan.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function onPointerMove(event: PointerEvent<HTMLImageElement>) {
    if (drag.current) setPan({ x: event.clientX - drag.current.x, y: event.clientY - drag.current.y });
  }

  return (
    <div
      ref={dialogRef}
      className="rd-lightbox"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      tabIndex={-1}
      onKeyDown={onKeyDown}
    >
      <div className="rd-lightbox-stage">
        <div className="rd-lightbox-top">
          <span className="rd-lightbox-count">{`${index + 1} of ${items.length}`}</span>
          <span className="rd-lightbox-spacer" />
          {showsImage(item) && (
            <button type="button" className="rd-lightbox-btn" aria-pressed={zoom} onClick={() => setZoom((z) => !z)}>
              Zoom <kbd>Z</kbd>
            </button>
          )}
          <button type="button" className="rd-lightbox-btn" aria-pressed={details} onClick={() => setDetails((d) => !d)}>
            Details <kbd>I</kbd>
          </button>
          <button ref={closeRef} type="button" className="rd-lightbox-btn" onClick={onClose}>
            Close <kbd>Esc</kbd>
          </button>
        </div>

        <button type="button" className="rd-lightbox-nav rd-lightbox-nav--prev" aria-label="Previous work" onClick={() => step(-1)}>
          ‹
        </button>
        <div className="rd-lightbox-image">
          {showsImage(item) ? (
            <img
              src={safeUrl(record.image_url)}
              alt={alt}
              className={zoom ? "rd-lightbox-zoomed" : undefined}
              style={zoom ? { transform: `translate(${pan.x}px, ${pan.y}px) scale(2.2)` } : undefined}
              onClick={() => !zoom && setZoom(true)}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={() => (drag.current = null)}
              draggable={false}
            />
          ) : (
            <p className="rd-lightbox-noimage">
              No image shown: the source does not state this work is open.{" "}
              {recordUrl && <a href={recordUrl}>View the museum record</a>}
            </p>
          )}
        </div>
        <button type="button" className="rd-lightbox-nav rd-lightbox-nav--next" aria-label="Next work" onClick={() => step(1)}>
          ›
        </button>

        <div className="rd-lightbox-bottom">
          <StatusMarks item={item} />
          {shortlist && (
            <>
              <button type="button" className="rd-lightbox-btn" aria-pressed={item.selected} onClick={keep}>
                {item.selected ? "Kept" : "Keep"} <kbd>K</kbd>
              </button>
              <button type="button" className="rd-lightbox-btn" disabled={!item.selected} onClick={drop}>
                Take off the shortlist <kbd>D</kbd>
              </button>
            </>
          )}
        </div>

        {shortlist && noteOpen && (
          <form className="rd-lightbox-note" onSubmit={submitNote} aria-label="Keep this work">
            {askName && (
              <label htmlFor={nameId}>
                <span>Your name (recorded with what you keep)</span>
                <input id={nameId} value={shortlist.operator} onChange={(e) => shortlist.setOperator(e.target.value)} />
              </label>
            )}
            {intent === "keep" && flagged(item) && (
              <label htmlFor={noteId}>
                <span>Note (required to keep a work that needs a human check)</span>
                <input id={noteId} value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
            )}
            <span className="rd-lightbox-note-actions">
              <button type="submit" className="rd-lightbox-btn rd-lightbox-btn--primary">
                {intent === "drop" ? "Take off the shortlist" : flagged(item) ? "Keep with this note" : "Keep"}
              </button>
              <button type="button" className="rd-lightbox-btn" onClick={closeNote}>
                Cancel
              </button>
            </span>
          </form>
        )}
        {error && (
          <p className="rd-lightbox-error" role="alert">
            {error}
          </p>
        )}
      </div>

      {details ? (
        <aside className="rd-lightbox-panel" aria-label="Details">
          <ItemEvidence run={run} item={item} titleId={titleId} />
        </aside>
      ) : (
        <h2 id={titleId} className="rd-visually-hidden">
          {record.title ?? record.id}
        </h2>
      )}
    </div>
  );
}
