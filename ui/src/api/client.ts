// The API calls the screens use (issue 46 onwards). The API enforces every gate; this
// client only reports what it says. Errors carry the API's own message, never a guess.
import type {
  BoardRequest,
  ErrorReport,
  ExportReceipt,
  ReportAccepted,
  ReviewRequest,
  RunCreated,
  RunView,
} from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.message === "string") return body.message; // Problem
    if (typeof body?.reason === "string") return `${body.gate}: ${body.reason}`; // GateBlocked
    if (Array.isArray(body?.detail)) {
      // FastAPI validation error: name each field and what is wrong with it.
      return body.detail
        .map((d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`)
        .join("; ");
    }
  } catch {
    // not JSON
  }
  return `HTTP ${response.status}`;
}

export async function createBoard(request: BoardRequest): Promise<RunCreated> {
  const response = await fetch("/boards", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (response.status !== 202) throw new ApiError(response.status, await errorMessage(response));
  return response.json();
}

export async function getRun(runId: string): Promise<RunView> {
  const response = await fetch(`/runs/${encodeURIComponent(runId)}`);
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return response.json();
}

export async function reviewRun(runId: string, request: ReviewRequest): Promise<RunView> {
  const response = await fetch(`/runs/${encodeURIComponent(runId)}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return response.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return response.json();
}

export function approveRun(runId: string, approval: { approver: string; acknowledged: true }): Promise<RunView> {
  return post(`/runs/${encodeURIComponent(runId)}/approve`, approval);
}

export function exportRun(runId: string): Promise<ExportReceipt> {
  return post(`/runs/${encodeURIComponent(runId)}/export`, { format: "csv" });
}

export function reportError(report: ErrorReport): Promise<ReportAccepted> {
  return post("/reports", report);
}
