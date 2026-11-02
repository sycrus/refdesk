# ADR-025: Two-level demo: hosted recorded runs, live sessions on the owner's machine

- **Status:** accepted (two-level decision and Joe's reasoning added 2026-11-02). Joe chose a container host over Vercel, and Render as the host (2026-10-31).
- **Date:** 2026-10-31

## Context
[ADR-024](ADR-024-rescope-for-applied-ai-roles.md) adds a hosted, read-only demo for applied AI and FDE reviewers. The demo makes no paid calls and needs no GPU. It runs the API and UI on the mock LLM, and serves recorded runs through the existing replay (`docs/architecture.md`, Replay). The PRD rules still apply: approval and export are never public, museum images load only from the source's own host, and nothing is shown as verified unless it is.

The API keeps run state in SQLite and the index in memory (PRD 13A). On a host whose filesystem is lost on restart, the demo store must be read-only, baked into the image, and safe to lose.

## Decision
Two levels (Joe, 2026-11-02):

1. **Public demo, recorded runs.** Ship the #167 Docker image with a read-only demo profile (bundled snapshot store, recorded runs, mock LLM, approval and export disabled), and host it on a **Render free web service** (Joe, 2026-10-31). Every recorded board shows its run ID, config hash and trace in the audit view, and `reproduce.md` rebuilds and replays it, so the output can be checked, not just viewed. The same image is the "a customer can run it" artifact in `reproduce.md`.
2. **Live sessions on Joe's machine.** For raters, usability participants and interested clients: the full system (CLIP retrieval, local generator and judge on the GPU), run on Joe's PC in person or by screen-share (as planned for #147). Usage data is collected only here, with the participant's consent (problem statement Section 8). Approval and export follow the normal gates.

Joe's reasoning: the generator and judge chosen earlier (ADR-020, ADR-022) are both local, by design (local first), so a fully live public demo would need a different, paid model. Recorded runs are also more predictable: the corpus behind them is retrieved and versioned, so what a reviewer sees is reproducible.

## Options considered
| Option | Why not chosen |
|---|---|
| Vercel: static UI plus FastAPI as a serverless function | Joe chose a container host on 2026-10-31. Joe's words, 2026-11-02: a container host so that clients can access a working demo, not a recorded one. Each board runs as a background task, writing to SQLite; Vercel's serverless functions don't support this. |
| Static showcase only (pre-baked boards, no API) | Joe's words, 2026-11-02: I want an actual working prototype, partly also to collect more usage data, so the API is necessary. |
| Screen recording only | Joe's words, 2026-11-02: recordings can be faked and are not good proof of technical ability. |
| Render free web service | Chosen. Joe: "I don't want any surprise charges, and more generous free tiers"; a cold start of about a minute is acceptable. Facts: no card needed; when the free hours run out, Render suspends free services until next month instead of billing; spins down after 15 min idle, up to about a minute to wake; ephemeral filesystem |
| Fly.io | Facts: per third-party sources, no lasting free allowance for new accounts, trial only |
| Railway | Facts: per third-party sources, a one-time trial credit, then a $5/month Hobby plan |
| Partly live public demo: live metadata-only search, recorded rationales | Joe's words, 2026-11-02: the strongest features are only evident when the search is live. Metadata search is what this project is trying to improve upon, the differentiator only shows up in live demos.  |
| Fully live public demo: paid host with more memory and a paid model behind a spend cap and rate limit | Joe, 2026-11-02: the chosen generator and judge are local by design (ADR-020, ADR-022); a public live demo would need a paid model and reopen the no-card decision. |
| Google Cloud Run | Joe: not just the card on file; he does not want any chance of a surprise charge, and a budget alert only notifies, it does not stop spending. Facts: the largest monthly free allowance; scales to zero; wakes in seconds; needs a billing account with a card |

## Consequences
- Easier: one image for the demo and for local or customer runs; the demo runs the real code paths.
- Harder: the demo's store and recorded runs are frozen at build time. A new demo means a new image.
- Harder: a reviewer waits up to about a minute on the first visit after 15 idle minutes. The demo link says so, and a screen recording sits next to it.
- Harder: the free instance is small. Third-party sources say 512 MB and 0.1 CPU (not confirmed in Render's docs). The image must fit: no torch, no CLIP model at runtime; the demo serves recorded runs.
- Easier: no card, so no bill. The worst case is suspension until the next month.
- Locked in: approval and export are disabled in the demo profile by configuration and by a test, not by hiding buttons (PRD 8B: the API enforces gates).
- Easier: usage data comes only from people who agreed to it, in live sessions, never from anonymous visitors to the public demo.
- Harder: live sessions need Joe's PC, Ollama and the GPU free at the time (one GPU-heavy job at a time, CLAUDE.md). They are scheduled, not on demand.

## Evidence
Free-tier facts checked 2026-10-31 from provider docs and third-party comparisons. Recheck before deploying:
- Render free tier: https://render.com/docs/free
- Cloud Run pricing: https://cloud.google.com/run/pricing
- Side-by-side free tiers (checked September 2026): https://flaviocopes.com/hosting-free-tiers/

No measurement of refdesk's cold-start time or memory use on Render yet. #167's image build and a test deploy will supply both. If the demo does not fit in the free instance, this ADR is reopened, not paid around.

## Revisit trigger
Render changes its free tier or asks for a card; the demo does not fit in the free instance; cold starts lose reviewers (they leave before the page loads); or the demo needs live model calls; or live sessions become frequent enough that hosting the full system is worth paying for.
