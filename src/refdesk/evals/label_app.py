"""Local page for the golden-v1 blind pass (issue #138, supports #15; ADR-018).

Shows one candidate at a time, the brief beside the work's cached image and record fields,
and writes Joe's label to the sheet's `relevant`, `grade` and `note` columns as soon as it
is given. It records labels; it never proposes one.

What keeps the pass blind: rows go to the page without rank, retriever or image URL, and
`runs/labelling-v1/pool-sources.jsonl` is never read. Without this page the pass still
works in the CSV, but each of ~270 images has to be opened by hand.

Images come from the local cache only (`data/images`, built by `refdesk images met`), and
only for records the store marks Open: no network fetch, so the image rule in CLAUDE.md
holds without a host check here. A work with no cached image shows its record link.

Each save re-reads the sheet and checks the row still holds the same candidate, so an
edit in a spreadsheet or a rebuilt pool is not overwritten by a stale page (409).

Run (PowerShell or WSL2), then open http://127.0.0.1:8200:
    uv run python -m refdesk.evals.label_app            # pass 1: blind-sheet.csv
    uv run python -m refdesk.evals.label_app --pass2    # pass 2, a day later
--pass2 creates blind-sheet-pass2.csv with the label columns cleared (so pass-1 labels are
never shown), or resumes it if it exists.

From another device (e.g. over Tailscale): `--host <this PC's address>`. Off localhost the
server needs a token, printed at startup as part of the URL; the first visit stores it in
a cookie. Without it, anyone who can reach the address could read the sheet and change
labels.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import secrets
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from refdesk.schema import RightsStatus
from refdesk.store import Store

ROOT = Path(__file__).resolve().parents[3]
SHEET = ROOT / "evals" / "labelling" / "v1" / "blind-sheet.csv"
PASS2 = SHEET.with_name("blind-sheet-pass2.csv")
PAGE = Path(__file__).with_name("label_page.html")
LABELS = ("relevant", "grade", "note")
# What the page may see. Not image_url (images come from /image/<index>) and nothing
# about how the candidate was found.
SHOWN = (
    "draft_id", "brief", "usage_mode", "candidate", "title", "artist", "date", "medium",
    "subjects", "record_url", *LABELS,
)  # fmt: skip
MAX_NOTE = 500
COOKIE = "refdesk_label_token"


class LabelError(ValueError):
    pass


def read_sheet(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_sheet(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    """Atomic: a crash mid-write never leaves a half-written sheet. LF line endings, as
    the pool builder writes them, so a label shows as a one-line diff."""
    partial = path.with_name(path.name + ".part")
    with partial.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    partial.replace(path)


def apply_label(row: dict[str, str], relevant: str, grade: str, note: str) -> dict[str, str]:
    """The row with new labels, using the sheet's rules (README step 2). Relevant `y` with
    no grade yet is allowed: the page saves y, then the grade."""
    if relevant not in ("", "y", "n"):
        raise LabelError(f"relevant must be y or n, not {relevant!r}")
    if grade not in ("", "1", "2"):
        raise LabelError(f"grade must be 1 or 2, not {grade!r}")
    if grade and relevant != "y":
        raise LabelError("a grade is only given when relevant is y")
    note = " ".join(note.split())
    if len(note) > MAX_NOTE:
        raise LabelError(f"note is longer than {MAX_NOTE} characters")
    return row | {"relevant": relevant, "grade": grade, "note": note}


def start_pass2(sheet: Path, out: Path) -> None:
    """Copy the pass-1 rows, in the same order, with the label columns cleared."""
    if out.exists():
        raise FileExistsError(f"{out.name} exists; pass 2 is never restarted over itself")
    fields, rows = read_sheet(sheet)
    write_sheet(out, fields, [r | dict.fromkeys(LABELS, "") for r in rows])


class Label(BaseModel):
    candidate: str
    relevant: str = ""
    grade: str = ""
    note: str = ""


def _view(index: int, row: dict[str, str]) -> dict[str, str | int]:
    return {"index": index} | {k: row.get(k, "") for k in SHOWN}


def create_app(sheet: Path, db: Path, images: Path, token: str | None = None) -> FastAPI:
    app = FastAPI(title="refdesk blind labelling")
    lock = threading.Lock()
    images = images.resolve()

    if token is not None:

        @app.middleware("http")
        async def require_token(request: Request, call_next):
            given = request.query_params.get("t") or request.cookies.get(COOKIE) or ""
            if not secrets.compare_digest(given, token):
                return PlainTextResponse("token missing or wrong: use the URL printed at startup",
                                         status_code=401)  # fmt: skip
            response = await call_next(request)
            if request.query_params.get("t"):
                response.set_cookie(COOKIE, token, httponly=True, samesite="strict")
            return response

    def candidate(index: int) -> str:
        rows = read_sheet(sheet)[1]
        if not 0 <= index < len(rows):
            raise HTTPException(404, "no such row")
        return rows[index]["candidate"]

    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        return PAGE.read_text(encoding="utf-8")

    @app.get("/api/rows")
    def rows() -> dict:
        _, data = read_sheet(sheet)
        return {"sheet": sheet.name, "rows": [_view(i, r) for i, r in enumerate(data)]}

    @app.put("/api/rows/{index}")
    def label(index: int, body: Label) -> dict:
        with lock:
            fields, data = read_sheet(sheet)
            if not 0 <= index < len(data):
                raise HTTPException(404, "no such row")
            if data[index]["candidate"] != body.candidate:
                raise HTTPException(409, "the sheet changed: reload the page")
            try:
                data[index] = apply_label(data[index], body.relevant, body.grade, body.note)
            except LabelError as error:
                raise HTTPException(422, str(error)) from error
            write_sheet(sheet, fields, data)
        return _view(index, data[index])

    @app.get("/image/{index}")
    def image(index: int) -> FileResponse:
        record_id = candidate(index)
        with Store(db) as store:
            record, cached = store.get_record(record_id), store.get_image(record_id)
        if record is None or record.rights.status is not RightsStatus.OPEN:
            raise HTTPException(404, "not an open work")
        if cached is None:
            raise HTTPException(404, "no cached image")
        path = (images / cached["path"]).resolve()
        if not path.is_relative_to(images) or not path.is_file():
            raise HTTPException(404, "no cached image")
        if hashlib.sha256(path.read_bytes()).hexdigest() != cached["sha256"]:
            raise HTTPException(404, "cached image does not match its recorded hash")
        return FileResponse(path)

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="refdesk golden-v1 blind labelling page")
    parser.add_argument("--pass2", action="store_true", help="label blind-sheet-pass2.csv")
    parser.add_argument("--sheet", help="another sheet (e.g. a scratch copy for trying the page)")
    parser.add_argument("--host", default="127.0.0.1", help="e.g. this PC's Tailscale address")
    parser.add_argument("--port", type=int, default=8200)
    parser.add_argument("--db", default=str(ROOT / "data" / "refdesk.sqlite"))
    parser.add_argument("--images", default=str(ROOT / "data" / "images"))
    args = parser.parse_args()
    sheet = Path(args.sheet) if args.sheet else SHEET
    if args.pass2 and not args.sheet:
        if not PASS2.exists():
            start_pass2(SHEET, PASS2)
            print(f"created {PASS2.name} with the label columns cleared")
        sheet = PASS2
    token = None if args.host == "127.0.0.1" else secrets.token_urlsafe(16)
    query = f"/?t={token}" if token else ""
    print(f"labelling {sheet.name} at http://{args.host}:{args.port}{query}")
    app = create_app(sheet, Path(args.db), Path(args.images), token)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
