// S6 Approve and export (PRD 8A, 8B gates G4 and G5; issue 101). A summary of what the
// provenance pack will hold, the ConfirmDialog (acknowledgement and "Approving as"), then
// approval and the irreversible export, then the receipt. The API enforces every rule:
// approval only when every flagged item is decided, export only with an approval record,
// read-only afterwards. The summary here mirrors the API's pack rule for display; the
// receipt reports what the API actually exported.
import { useEffect, useState } from "react";
import { ApiError, approveRun, exportRun, getRun } from "../api/client";
import type { BoardItem, ExportReceipt, RunView } from "../api/types";
import { Button } from "../components/Button";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { AttributionStatus, NOT_LEGAL_ADVICE, RightsStatus } from "../generated/wording";
import "./screens.css";

export interface ApproveScreenProps {
  runId: string;
  onBack: () => void;
}

// The same rule as `pack_items` in src/refdesk/boards.py.
export function packPreview(items: BoardItem[]) {
  const included: BoardItem[] = [];
  let excludedUnverified = 0;
  for (const item of items) {
    const kept = item.review?.decision === "keep";
    if (item.review?.decision === "drop") continue;
    if (item.record.rights.status === RightsStatus.UNVERIFIED && !kept) {
      excludedUnverified += 1;
    } else if (item.attribution_status === AttributionStatus.VERIFIED || kept) {
      included.push(item);
    }
  }
  const countsByStatus: Record<string, number> = {};
  for (const item of included) {
    countsByStatus[item.record.rights.status] = (countsByStatus[item.record.rights.status] ?? 0) + 1;
  }
  const reviewed = included
    .filter((item) => item.review)
    .map((item) => ({ id: item.record.id, title: item.record.title ?? item.record.id, note: item.review?.note ?? "" }));
  return { included, excludedUnverified, countsByStatus, reviewed };
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

export function ApproveScreen({ runId, onBack }: ApproveScreenProps) {
  const [run, setRun] = useState<RunView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getRun(runId)
      .then(setRun)
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, [runId]);

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
  const preview = packPreview(run.items);
  const approved = g4?.state === "passed";

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
          <section aria-labelledby="pack-title">
            <h2 id="pack-title">What the provenance pack will hold</h2>
            <ul className="rd-dialog-counts">
              {Object.entries(preview.countsByStatus).map(([status, count]) => (
                <li key={status}>
                  {status}: {count}
                </li>
              ))}
            </ul>
            <p>
              {preview.included.length} {preview.included.length === 1 ? "item" : "items"} in the pack.
              {preview.excludedUnverified > 0 && ` ${preview.excludedUnverified} unverified left out.`}
            </p>
            <p className="rd-note">{NOT_LEGAL_ADVICE}</p>
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
              {`Approve and export ${preview.included.length} ${preview.included.length === 1 ? "item" : "items"}`}
            </Button>
          )}
          <ConfirmDialog
            open={dialogOpen}
            itemCount={preview.included.length}
            countsByStatus={preview.countsByStatus}
            reviewed={preview.reviewed}
            excludedUnverified={preview.excludedUnverified}
            runId={runId}
            onConfirm={(approval) => void onConfirm(approval)}
            onCancel={() => setDialogOpen(false)}
          />
        </>
      )}
    </section>
  );
}
