// Museum data is untrusted input (CLAUDE.md), including its URLs. Only http(s) URLs are
// rendered as links or images; anything else (javascript:, data:, relative paths) is
// dropped, so a hostile record cannot run script or load from an unexpected place.
export function safeUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}
