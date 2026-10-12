// The two API calls the board screens use (issue #46). The API enforces every gate; this
// client only reports what it says. Errors carry the API's own message, never a guess.
import type { BoardRequest, RunCreated, RunView } from "./types";

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
