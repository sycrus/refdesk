// S6 Approve and export (PRD 8A, 8B gates G4 and G5; issue 101). A summary of what the
// provenance pack will hold, the ConfirmDialog (acknowledgement and "Approving as"), then
// approval and the irreversible export, then the receipt. The API enforces every rule:
// approval only when every flagged item is decided, export only with an approval record,
// read-only afterwards. What the pack will hold comes from the API (GET /runs/{id}/pack),
// grouped as thumbnails (issue 233); the receipt reports what the API actually exported.
import { useEffect, useState } from "react";
import { ApiError, approveRun, exportRun, getPack, getRun } from "../api/client";
import type { BoardItem, ExportReceipt, PackSummary, RunView } from "../api/types";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { showsImage } from "../components/EvidenceCard";
import { Icon, type IconName } from "../components/Icon";
import { Lightbox } from "../components/Lightbox";
import { safeUrl } from "../components/safeUrl";
import { NOT_LEGAL_ADVICE, RightsStatus } from "../generated/wording";
import "./screens.css";

export interface ApproveScreenProps {
  runId: string;
  onBack: () => void;
  onRun?: (run: RunView) => void; // the stage panel follows this run (issue 229)
}

// The groups on this screen (issue 233). Each comes from the API's pack summary; the
// screen only lays them out. Marks follow the status marks: never colour alone.
const GROUPS = [
  { key: "open", title: RightsStatus.OPEN, note: "Attribution verified from record, and the source marks the rights as open.", icon: "check", tone: "ok" },
  { key: "reviewed", title: "Marked reviewed by you", note: "These needed a human check. You kept them at Verify with a note.", icon: "verify", tone: "accent" },
  { key: "reference", title: "Listed for reference", note: `${RightsStatus.PERMISSION_REQUIRED}: the pack lists the record and its link, never an image.`, icon: "lock", tone: "danger" },
] as const;

function Thumb({ item, icon, tone, label, onOpen }: { item: BoardItem; icon: IconName; tone: string; label: string; onOpen: () => void }) {
  const title = item.record.title ?? item.record.id;
  return (
    <li>
      <button type="button" className={`rd-thumb rd-thumb--${tone}`} onClick={onOpen} aria-label={`${title}: ${label}`} title={label}>
        {showsImage(item) ? (
          <img src={safeUrl(item.record.image_url)} alt="" loading="lazy" />
        ) : (
          <span className="rd-thumb-none">
            <Icon name="lock" />
          </span>
        )}
        <span className="rd-thumb-mark" aria-hidden="true">
          <Icon name={icon} />
        </span>
      </button>
    </li>
  );
}

function Receipt({ receipt }: { receipt: ExportReceipt }) {
  return (
    <section aria-labelledby="receipt-title">
      <h2 id="receipt-title">Receipt</h2>
      <p role="status">{receipt.notice}</p>
      <dl className="rd-facts">
        <dt>File</dt>
        <dd className="rd-mono">{receipt.file}</dd>
        <dt>Exported</dt>
        <dd>{receipt.exported_at}</dd>
        <dt>Approved by</dt>
        <dd>{receipt.approver}</dd>
        <dt>Run</dt>
        <dd className="rd-mono">{receipt.run_id}</dd>
        {Object.entries(receipt.versions).map(([name, version]) => (
          <div key={name} className="rd-facts-row">
            <dt>{name}</dt>
            <dd className="rd-mono">{version}</dd>
          </div>
        ))}
      </dl>
      <p className="rd-note">{receipt.not_legal_advice}</p>
    </section>
  );
}

export function ApproveScreen({ runId, onBack, onRun }: ApproveScreenProps) {
  const [run, setRun] = useState<RunView | null>(null);
  useEffect(() => {
    if (run) onRun?.(run); // the stage panel follows approval and export (issue 229)
  }, [run, onRun]);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pack, setPack] = useState<PackSummary | null>(null);
  const [viewing, setViewing] = useState<string | null>(null); // a thumbnail in the lightbox

  useEffect(() => {
    getRun(runId)
      .then(setRun)
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, [runId]);

  // The pack follows the run: fetched again whenever the run changes (approval, export).
  useEffect(() => {
    if (!run || run.export) return;
    getPack(runId)
      .then(setPack)
      .catch((err) => setError(`What the pack will hold did not load: ${err instanceof ApiError ? err.message : String(err)}`));
  }, [runId, run]);

  if (!run) {
    return error ? (
      <p className="rd-error" role="alert">
        {error}
      </p>
    ) : (
      <p role="status">Loading…</p>
    );
  }

  const g4 = run.gates.find((gate) => gate.id === "G4");
  const g5 = run.gates.find((gate) => gate.id === "G5");
  const approved = g4?.state === "passed";
  const byId = new Map(run.items.map((item) => [item.record.id, item]));
  const items = (ids: string[]) => ids.map((id) => byId.get(id)).filter((item): item is BoardItem => item !== undefined);
  const included = pack ? [...items(pack.open), ...items(pack.reviewed), ...items(pack.reference)] : [];
  const countsByStatus: Record<string, number> = {};
  for (const item of included) {
    countsByStatus[item.record.rights.status] = (countsByStatus[item.record.rights.status] ?? 0) + 1;
  }
  const reviewed = pack
    ? items(pack.reviewed).map((item) => ({ id: item.record.id, title: item.record.title ?? item.record.id, note: item.review?.note ?? "" }))
    : [];
  const excludedUnverified = pack ? pack.left_out.filter((w) => w.reason === "Rights unverified, not reviewed").length : 0;
  const count = pack?.included ?? 0;
  const shown = [...included, ...(pack ? items(pack.left_out.map((w) => w.record_id)) : [])];

  async function doExport() {
    setBusy(true);
    setError(null);
    try {
      await exportRun(runId);
      setRun(await getRun(runId));
    } catch (err) {
      // A failed export leaves the board unlocked: G5 stays active and export can be retried.
      setError(err instanceof ApiError ? err.message : String(err));
      setRun(await getRun(runId).catch(() => run));
    } finally {
      setBusy(false);
    }
  }

  async function onConfirm(approval: { approver: string; acknowledged: true }) {
    setDialogOpen(false);
    setBusy(true);
    setError(null);
    try {
      setRun(await approveRun(runId, approval));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setBusy(false);
      return;
    }
    await doExport();
  }

  return (
    <section className="rd-screen rd-detail" aria-labelledby="approve-title">
      <a
        className="rd-back"
        href={`?run=${encodeURIComponent(runId)}`}
        onClick={(event) => {
          event.preventDefault();
          onBack();
        }}
      >
        Back to the board
      </a>
      <h1 id="approve-title" className="rd-screen-title">
        Approve and export
      </h1>
      {run.export ? (
        <Receipt receipt={run.export} />
      ) : (
        <>
          {g4 && <p role="status">{approved ? g5?.status_text : g4.status_text}</p>}
          <section aria-labelledby="pack-title" className="rd-pack">
            <h2 id="pack-title">What the provenance pack will hold</h2>
            {!pack ? (
              <p role="status">Loading what the pack will hold…</p>
            ) : (
              <>
                <p>
                  <strong>{`${count} ${count === 1 ? "work goes" : "works go"} into the export.`}</strong>
                  {pack.left_out.length > 0 && ` ${pack.left_out.length} left out.`}
                </p>
                {GROUPS.map((group) => {
                  const list = items(pack[group.key]);
                  return (
                    <section key={group.key} className="rd-pack-group" aria-label={`${group.title}: ${list.length}`}>
                      <h3 className={`rd-pack-head rd-pack-head--${group.tone}`}>
                        <span className="rd-pack-icon" aria-hidden="true">
                          <Icon name={group.icon} />
                        </span>
                        {group.title}
                        <span className="rd-pack-count">{list.length}</span>
                      </h3>
                      <p className="rd-note">{group.note}</p>
                      {list.length > 0 ? (
                        <ul className="rd-thumbs">
                          {list.map((item) => (
                            <Thumb key={item.record.id} item={item} icon={group.icon} tone={group.tone} label={group.title} onOpen={() => setViewing(item.record.id)} />
                          ))}
                        </ul>
                      ) : (
                        <p className="rd-note">None.</p>
                      )}
                    </section>
                  );
                })}
                <section className="rd-pack-group" aria-label={`Left out: ${pack.left_out.length}`}>
                  <h3 className="rd-pack-head rd-pack-head--muted">
                    <span className="rd-pack-icon" aria-hidden="true">
                      <Icon name="dash" />
                    </span>
                    Left out
                    <span className="rd-pack-count">{pack.left_out.length}</span>
                  </h3>
                  <p className="rd-note">Not in the export. Each says why.</p>
                  {pack.left_out.length > 0 ? (
                    <ul className="rd-thumbs rd-thumbs--out">
                      {pack.left_out.map((w) => {
                        const item = byId.get(w.record_id);
                        return item ? (
                          <Thumb key={w.record_id} item={item} icon="dash" tone="muted" label={w.reason} onOpen={() => setViewing(w.record_id)} />
                        ) : null;
                      })}
                    </ul>
                  ) : (
                    <p className="rd-note">None.</p>
                  )}
                </section>
                <p className="rd-note">{NOT_LEGAL_ADVICE}</p>
              </>
            )}
          </section>
          {error && (
            <p className="rd-error" role="alert">
              {error}
            </p>
          )}
          {approved ? (
            <Button variant="primary" onClick={() => void doExport()} disabledReason={busy ? "Exporting…" : undefined}>
              Export provenance pack
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={() => setDialogOpen(true)}
              disabledReason={
                g4?.state !== "active" ? `Approval is not open yet: ${g4?.status_text}` : busy ? "Working…" : undefined
              }
            >
              {`Approve and export ${count} ${count === 1 ? "item" : "items"}`}
            </Button>
          )}
          <ConfirmDialog
            open={dialogOpen}
            itemCount={count}
            countsByStatus={countsByStatus}
            reviewed={reviewed}
            excludedUnverified={excludedUnverified}
            runId={runId}
            onConfirm={(approval) => void onConfirm(approval)}
            onCancel={() => setDialogOpen(false)}
          />
          {viewing && (
            <Lightbox run={run} items={shown} itemId={viewing} onShow={setViewing} onClose={() => setViewing(null)} />
          )}
        </>
      )}
    </section>
  );
}
