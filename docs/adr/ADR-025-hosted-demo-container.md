# ADR-025: Hosted demo as a container on recorded runs

- **Status:** proposed (draft by Claude, 2026-10-31). Joe chose a container host over Vercel, and Render as the host (2026-10-31). The remaining reasoning cells are his.
- **Date:** 2026-10-31

## Context
[ADR-024](ADR-024-rescope-for-applied-ai-roles.md) adds a hosted, read-only demo for applied AI and FDE reviewers. The demo makes no paid calls and needs no GPU. It runs the API and UI on the mock LLM, and serves recorded runs through the existing replay (`docs/architecture.md`, Replay). The PRD rules still apply: approval and export are never public, museum images load only from the source's own host, and nothing is shown as verified unless it is.

The API keeps run state in SQLite and the index in memory (PRD 13A). On a host whose filesystem is lost on restart, the demo store must be read-only, baked into the image, and safe to lose.

## Decision
Ship the #167 Docker image with a read-only demo profile (bundled snapshot store, recorded runs, mock LLM, approval and export disabled), and host it on a **Render free web service** (Joe, 2026-10-31). The same image is the "a customer can run it" artifact in `reproduce.md`.

## Options considered
| Option | Why not chosen |
|---|---|
| Vercel: static UI plus FastAPI as a serverless function | Joe chose a container host on 2026-10-31. **[Joe]** reasoning |
| Static showcase only (pre-baked boards, no API) | **[Joe]** |
| Screen recording only | **[Joe]** |
| Render free web service | Chosen. Joe: "I don't want any surprise charges"; a cold start of about a minute is acceptable. Facts: no card needed; when the free hours run out, Render suspends free services until next month instead of billing; spins down after 15 min idle, up to about a minute to wake; ephemeral filesystem |
| Fly.io | **[Joe]**. Facts: per third-party sources, no lasting free allowance for new accounts, trial only |
| Railway | **[Joe]**. Facts: per third-party sources, a one-time trial credit, then a $5/month Hobby plan |
| Google Cloud Run | Joe: not just the card on file; he does not want any chance of a surprise charge, and a budget alert only notifies, it does not stop spending. Facts: the largest monthly free allowance; scales to zero; wakes in seconds; needs a billing account with a card |

## Consequences
- Easier: one image for the demo and for local or customer runs; the demo runs the real code paths.
- Harder: the demo's store and recorded runs are frozen at build time. A new demo means a new image.
- Harder: a reviewer waits up to about a minute on the first visit after 15 idle minutes. The demo link says so, and a screen recording sits next to it.
- Harder: the free instance is small. Third-party sources say 512 MB and 0.1 CPU (not confirmed in Render's docs). The image must fit: no torch, no CLIP model at runtime; the demo serves recorded runs.
- Easier: no card, so no bill. The worst case is suspension until the next month.
- Locked in: approval and export are disabled in the demo profile by configuration and by a test, not by hiding buttons (PRD 8B: the API enforces gates).
- **[Joe]** anything else.

## Evidence
Free-tier facts checked 2026-10-31 from provider docs and third-party comparisons. Recheck before deploying:
- Render free tier: https://render.com/docs/free
- Cloud Run pricing: https://cloud.google.com/run/pricing
- Side-by-side free tiers (checked September 2026): https://flaviocopes.com/hosting-free-tiers/

No measurement of refdesk's cold-start time or memory use on Render yet. #167's image build and a test deploy will supply both. If the demo does not fit in the free instance, this ADR is reopened, not paid around.

## Revisit trigger
Render changes its free tier or asks for a card; the demo does not fit in the free instance; cold starts lose reviewers (they leave before the page loads); or the demo needs live model calls.
