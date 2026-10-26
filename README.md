# refdesk

Given a creative brief, refdesk finds public-domain paintings from open museum collections, explains why each fits in the brief's own terms, and records for each one where it came from, what rights flag the museum gives it, and when that was checked. It runs local-first, and uses a cloud model only under a spend cap.

The project has two goals, judged separately (PRD Section 3): a **product hypothesis** (this workflow beats the alternatives for small studios) and a **demonstration** of designing, evaluating, governing and running an AI system. It is also a learning project, so judgement calls (golden labels, ADR reasoning, decision costs) stay with the owner.

**Status (12 October 2026):** M1 (ingest and baselines) is done; M2 (similarity, LLM plumbing, UI) is in progress. Nothing here is a product claim yet: every eval so far uses a synthetic golden set.

## What works today

- **Data:** the Met's European Paintings slice, **2,588 records** (2,308 open, 280 permission required; 0 unverified), each with a rights record read from the museum's own `isPublicDomain` flag, the raw API response, and resumable, idempotent ingest. Images cached for **open works only** (2,308).
- **Retrieval:** a metadata-only baseline (Jaccard over field-named attributes) and a CLIP similarity baseline (OpenCLIP + exact FAISS), behind one interface. In reproduction mode every retriever returns open works only.
- **Evaluation:** a golden-set validator, capped recall@k, MRR and an open-rights share, seeded bootstrap intervals, run manifests with a config hash, paired comparison of two runs, and a gate policy (a tripwire only, so far).
- **Models:** one LLM client for every provider (keep-local, budget, approval and price checks before any request; no silent fallback), a mock LLM server with scripted failures, and a GPU `ModelManager` that keeps one model loaded at a time.
- **API:** a FastAPI contract skeleton (`docs/api/openapi.json`), endpoints returning 501 until built.

## Decisions so far

| Area | Decision | ADR |
|---|---|---|
| Decision model | Fine-tune Kev-4B (local in WSL2 first, Modal fallback under budget) | 001 |
| Golden sets | Synthetic v0 for the harness; hand-labelled v1 for claims | 018 |
| CI | GitHub Actions PR tier now; self-hosted nightly later, while private | 019 |
| Generators | Local `qwen3.5:9b`; cloud `deepseek-flash`; reserve `deepseek-v4-pro` | 020 |
| Judge | Local `phi4`, one claim at a time; never the generator's family (Granite Guardian dropped after a harder probe) | 021, 022 |

Reasoning sections in the ADRs are still to be written by the owner.

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
8. **Mock LLM (optional).** Starts the local mock LLM server, which is the default instead of paid providers. Its answers are deterministic, and it can script failures (`--script ok,429`).
   ```
   uv run python -m refdesk.llm.mock_server --port 8100
   ```
9. **UI and API.** Builds the static UI once, then starts the API, which serves both the UI and the endpoints at http://localhost:8000. Restart the API after the first build. Set `REFDESK_RETRIEVER=jaccard` if you skipped step 5.
   ```
   cd ui; npm install; npm run build; cd ..
   uv run uvicorn refdesk.api.app:app --port 8000
   ```

Copy `.env.example` to `.env` for API keys (DeepSeek). Paid calls also need a budget in `config/budgets.yaml` and an explicit `--approve`. Before committing: `uv run python scripts/verify.py` (frozen golden files, `.env`, secrets). Kev runs in WSL2 through `scripts/kev.ps1`.

## Where things are

| Path | What |
|---|---|
| [`docs/prd.md`](docs/prd.md) | The working spec (v0.3) |
| [`docs/architecture.md`](docs/architecture.md) | What is built and how it connects |
| [`docs/adr/`](docs/adr/) | Decisions |
| [`docs/data-sources.md`](docs/data-sources.md) | Licences, rights flags, rate limits, drift |
| [`docs/eval-gate-policy.md`](docs/eval-gate-policy.md) | Metric definitions, noise, gates |
| [`evals/`](evals/README.md) | Golden sets and reports |
| [`docs/ai-assist-log.md`](docs/ai-assist-log.md) | Defects introduced by AI assistance, and how they were caught |
| [`design/`](design/) | Design tokens, brand book and component specs for the UI |
| `config/` | Providers and tiers, budgets, measured model VRAM |
| `src/refdesk/` | The code |

Work items are GitHub Issues; see [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md).

## Rights

refdesk records what each museum states. It is not legal advice. Only collections whose terms and machine-readable flags confirm open use are ingested; permission-required collections (including Singapore national collections) are not scraped. Images are fetched only for works the source marks as open, and only from the source's own image host.
