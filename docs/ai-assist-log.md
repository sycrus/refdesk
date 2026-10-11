# AI-assist defect log

Log every defect an AI assistant introduced, and how it was caught (CLAUDE.md, definition of done).

| Date | Issue | What the AI got wrong | How it was caught | Fix |
|---|---|---|---|---|
| 2026-10-11 | setup (pre-tracker) | `scripts/kev.ps1 status` used nested double quotes inside a `wsl ... bash -lc '...'` argument; Windows PowerShell 5.1 mangled them (`syntax error: unexpected end of file`) | Smoke test of the wrapper before commit | Removed nested double quotes; comment added |
| 2026-10-11 | setup (pre-tracker) | `scripts/kev.ps1 stop` ran `pkill -f kev.serve`, which matched its own shell's command line and killed itself (exit 15) | Smoke test of the wrapper before commit | Pattern `python -m [k]ev.serve`; comment added |
