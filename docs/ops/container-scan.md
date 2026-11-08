# Container scan and triage (issue #167)

The image is scanned in CI on every change (`.github/workflows/container.yml`, Trivy 0.58.1, HIGH and CRITICAL, report only; each run's summary holds the full table). This file records the triage. The relevance column is Claude Code's assessment from how the image is used; **the residual-risk call is Joe's** (CLAUDE.md).

## Scans

| Date | Commit | Base | OS | Findings (HIGH / CRITICAL) | Python dependencies | Image | Memory after start |
|---|---|---|---|---|---|---|---|
| 2026-11-08 | `cfe545a` | `python:3.12.12-slim-bookworm` | Debian 12.13 | 83 (74 / 9) | 0 | 93 MB | 51 MiB of 512 MiB |
| 2026-11-08 | `1c2bc68` | same, plus `apt-get upgrade` in the runtime stage | Debian 12.15 | 42 (40 / 2) | 0 | 111 MB | not recorded (format) |

The first scan's findings were all in Debian base packages; Debian security updates fixed 41 of them. **None of the remaining 42 has a fix in Debian 12 today**: 33 affected (no fix yet), 7 fix deferred, 1 will not fix. Python packages (numpy, faiss-cpu, fastapi, pydantic, uvicorn and the rest) have no HIGH or CRITICAL findings.

## Remaining findings, by component

How the image runs: one `uvicorn` process as UID 10001, no shell entry point, no systemd, no mount or terminal programs invoked; the only input is HTTP requests to the API.

| Component (packages) | Findings | Example | Used by refdesk at run time? | Assessment (proposed) |
|---|---|---|---|---|
| SQLite (`libsqlite3-0`) | 6, incl. **CRITICAL** CVE-2025-7458 (integer overflow, affected) and CVE-2026-11822 (FTS5, fix deferred) | | **Yes**: Python's `sqlite3` links it; the store and runs live in SQLite | Exploits need attacker-controlled SQL, schema or database files. refdesk runs only parameterised queries and its own fixed schema, uses no FTS5 and no extensions, and never opens a database it did not create. Low. The most relevant group: recheck on every scan |
| zlib (`zlib1g`) | 3, incl. **CRITICAL** CVE-2023-45853 (will not fix) | CVE-2023-45853 is in minizip, which `zlib1g` does not ship; one HIGH is titled for webpack-dev-middleware, a likely scanner mismatch | Indirectly (Python's `zlib`) | No untrusted compressed input in the API. Low |
| util-linux (`util-linux`, `util-linux-extra`, `mount`, `bsdutils`, `libblkid1`, `libmount1`, `libsmartcols1`, `libuuid1`) | 24 rows, one CVE (CVE-2026-53613, `mount` TOCTOU) and others | | No: `mount` is never run; the process has no capabilities | Not reachable from the API |
| systemd libraries (`libsystemd0`, `libudev1`) | CVE-2026-16742 (systemd-homed local privilege escalation, fix deferred) | | No: no systemd or homed in the container | Not reachable |
| ncurses (`libncursesw6`, `libtinfo6`, `ncurses-base`) | CVE-2025-69720 | | No terminal UI | Not reachable |
| `perl-base` | CVE-2026-9538 (Archive::Tar DoS, fix deferred) | | No Perl at run time | Not reachable |
| `gzip`, `libacl1` | gzip information disclosure; libacl symlink traversal (both fix deferred) | | No | Not reachable |

## Options to reduce the rest (not done; Joe's call)

1. **Debian 13 base** (`python:3.12.x-slim-trixie`): newer packages; likely fewer findings. Needs a pinned patch version and a rescan.
2. **Distroless or a minimal base** without util-linux, perl, ncurses and gzip: removes most unreachable findings outright; harder to debug (no shell).
3. **Keep as is and rescan**: the `apt-get upgrade` picks up Debian fixes on every rebuild.

## Revisit

On every scan: any new finding in SQLite, zlib, OpenSSL or Python packages; any finding whose status changes to `fixed` (rebuild). Before the demo goes public on Render (ADR-025).
