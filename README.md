# refdesk

A rights-checked, explained art-reference workflow built from open museum collections (CC0 and public domain only).

Status: early scaffold (M0). The working spec is [`docs/prd.md`](docs/prd.md); decisions are in [`docs/adr/`](docs/adr/); work items are GitHub Issues.

## Develop (PowerShell or WSL2)

```
uv sync
uv run pytest -q
uv run python scripts/verify.py          # after git add: frozen golden files, .env, secrets
```

Kev (the decision model) runs in WSL2; see `scripts/kev.ps1`.
