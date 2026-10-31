# refdesk

Given a creative brief, refdesk finds public-domain paintings from open museum collections, explains why each fits in the brief's own terms, and records for each one where it came from, what rights flag the museum gives it, and when that was checked. It runs local-first, and uses a cloud model only under a spend cap.

The project has two goals, judged separately (PRD Section 3): a **product hypothesis** (this workflow beats the alternatives for small studios) and a **demonstration** of designing, evaluating, governing and running an AI system. It is also a learning project, so judgement calls (golden labels, ADR reasoning, decision costs) stay with the owner.

**Status (28 October 2026):** M1 and M2 are done (except named periods, #64). M3 is built end to end: rationales as checked claims, review, approval, export with a provenance pack, and "This is wrong" reports. Only the rationale eval on `golden-v1` (#102) is left, and that waits for golden-v1 itself (#15). Its two blind passes are done; the review pass is parked while the usability test (#147) runs first. Nothing here is a product claim yet: every eval so far uses a synthetic golden set.

## What works today

- **Data:** the Met's European Paintings slice, **2,588 records** (2,308 open, 280 permission required; 0 unverified), each with a rights record read from the museum's own `isPublicDomain` flag, the raw API response, and resumable, idempotent ingest. Images cached for **open works only** (2,308).
- **Retrieval:** a metadata-only baseline (Jaccard over field-named attributes) and a CLIP similarity baseline (OpenCLIP + exact FAISS), behind one interface. In reproduction mode every retriever returns open works only.
- **Evaluation:** a golden-set validator, capped recall@k, MRR and an open-rights share, seeded bootstrap intervals, run manifests with a config hash, paired comparison of two runs, and a gate policy (a tripwire only, so far).
- **Models:** one LLM client for every provider (keep-local, budget, approval and price checks before any request; no silent fallback), a mock LLM server with scripted failures, and a GPU `ModelManager` that keeps one model loaded at a time.
- **Rationales:** for each item, the generator (local `qwen3.5:9b`) writes claims that each name a record field, plus one sentence on fit. Plain code checks every claim against the record, then `phi4` checks each one; any failure makes the item "Needs human check" and names the claim. A fit sentence that may state a fact gets an opinion flag (ADR-022).
- **API and UI:** a board runs from a brief (S1 to S3), with item detail (S4), review of flagged items (S5), approval and export of a provenance pack CSV (S6), and "This is wrong" reports (S8). The API enforces every gate; the UI only shows them. Only raising the budget cap is still a 501. A `/design` page shows every component, checked with axe in CI.
- **Evaluation:** besides retrieval, a rationale eval (verifier pass rates, `eval-rationales`) and probes that screened the judge. For `golden-v1`, a local labelling page, phi4's check of Claude's proposals, and a trust report that must pass before the set is frozen (ADR-018).

## Decisions so far

| Area | Decision | ADR |
|---|---|---|
| Decision model | Kev-4B behind one decision contract: serve the base model first, fine-tune only if it wins by a significant margin | 001 |
| Golden sets | Synthetic v0 for the harness; v1 proposed by Claude, checked by phi4, every label reviewed by the owner after a blind subset | 018 |
| CI | GitHub Actions PR tier now; self-hosted nightly later, while private | 019 |
| Generators | Local `qwen3.5:9b`; cloud `deepseek-flash`; reserve `deepseek-v4-pro` | 020 |
| Judge | Local `phi4`, one claim at a time; never the generator's family (Granite Guardian dropped after a harder probe) | 021, 022 |

The owner has still to write the reasoning sections of the ADRs (#12).

## Quick start (PowerShell or WSL2)

Run the steps in order. Each one builds on the one before. Run `uv run python -m refdesk --help` to see every command.

1. **Install.** Installs the Python dependencies. Add `--extra embed` to get PyTorch and OpenCLIP as well (GPU, about 3 GB). Only step 5 needs them.
   ```
   uv sync
   ```
2. **Test.** Runs the test suite offline. It needs no data or keys.
   ```
   uv run pytest -q
   ```
3. **Ingest.** Fetches the Met's European Paintings records into the SQLite store under `data/`. Each record keeps its raw response and a rights record read from the Met's `isPublicDomain` flag. This takes about 45 minutes at 1 request/s. It is resumable, so you can stop and re-run it. Use `--limit N` for a quick partial run, and `stats` to see the counts.
   ```
   uv run python -m refdesk ingest met
   uv run python -m refdesk stats
   ```
4. **Cache images.** Downloads images from the Met's own image host into `data/images/`, for open works only.
   ```
   uv run python -m refdesk images met
   ```
5. **Embed.** Builds the CLIP + FAISS similarity index from the cached images, in `data/index/met-clip`. It needs `--extra embed` and the GPU. Skip this step if you only use the `jaccard` retriever.
   ```
   uv run python -m refdesk embed met
   ```
6. **Evaluate.** Scores a retriever against the golden set (synthetic `golden-v0` by default). It writes a report named with the config hash and prints that hash.
   ```
   uv run python -m refdesk eval --retriever jaccard
   ```
7. **Compare.** Gives a paired comparison of two or more eval runs, by the hashes from step 6. Add `--write` to save the comparison as a report.
   ```
   uv run python -m refdesk compare <hashA> <hashB>
   ```
8. **Mock LLM.** Starts the local mock LLM server, the default generator and judge for boards (`config/retrieval.yaml`, `api.reasoning`). Keep it running for step 9. Its answers are deterministic, and it can script failures (`--script ok,429`). For real models (Ollama, `qwen3.5:9b` and `phi4`), set `REFDESK_GENERATOR_TIER=local-small` and `REFDESK_JUDGE_TIER=auto` rather than editing the config; set both, or the judge stays the mock. You do not need the mock server then. `REFDESK_GENERATOR_TIER=none` gives retrieval-only boards. The variables can live in `.env` (see `.env.example`), loaded per command with `uv run --env-file .env ...`; refdesk itself never reads `.env`. Don't set `UV_ENV_FILE` globally: `pytest` would then use the real models.
   ```
   uv run python -m refdesk.llm.mock_server --port 8100
   ```
9. **UI and API.** Builds the static UI once, then starts the API, which serves both the UI and the endpoints at http://localhost:8000. Restart the API after the first build. Set `REFDESK_RETRIEVER=jaccard` if you skipped step 5.
   ```
   cd ui; npm install; npm run build; cd ..
   uv run uvicorn refdesk.api.app:app --port 8000
   ```
   With Ollama instead of the mocks (step 8): `uv run --env-file .env uvicorn refdesk.api.app:app --port 8000`.

Copy `.env.example` to `.env` for API keys (DeepSeek). Paid calls also need a budget in `config/budgets.yaml` and an explicit `--approve`. Before committing: `uv run python scripts/verify.py` (frozen golden files, `.env`, secrets). Kev runs in WSL2 through `scripts/kev.ps1`.

## Where things are

| Path | What |
|---|---|
| [`docs/prd.md`](docs/prd.md) | The working spec (v0.3) |
| [`docs/architecture.md`](docs/architecture.md) | What is built and how it connects |
| [`docs/adr/`](docs/adr/) | Decisions |
| [`docs/data-sources.md`](docs/data-sources.md) | Licences, rights flags, rate limits, drift |
| [`docs/eval-gate-policy.md`](docs/eval-gate-policy.md) | Metric definitions, noise, gates |
| [`evals/`](evals/README.md) | Golden sets, labelling files and reports |
| [`docs/usability/`](docs/usability/README.md) | Usability test protocol, observation sheet and report template |
| [`docs/ai-assist-log.md`](docs/ai-assist-log.md) | Defects introduced by AI assistance, and how they were caught |
| [`design/`](design/) | Design tokens, brand book and component specs for the UI |
| `config/` | Providers and tiers, budgets, measured model VRAM |
| `src/refdesk/` | The code |

Work items are GitHub Issues; see [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md).

## Rights

refdesk records what each museum states. It is not legal advice. Only collections whose terms and machine-readable flags confirm open use are ingested; permission-required collections (including Singapore national collections) are not scraped. Images are fetched only for works the source marks as open, and only from the source's own image host.
