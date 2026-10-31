"""Live step view and full stream log for the build loop (docs/build-loop.md, issue #185).

`claude -p` prints only the final message, so `runs/loop-issue-<n>.txt` used to show the
conclusion and none of the steps. The runner now starts Claude Code through this script
with `--output-format stream-json --verbose`, which emits one JSON event per line:

- `system` (subtype `init` carries `session_id` and `model`),
- `assistant` (message content blocks: `text`, `thinking`, `tool_use`),
- `user` (content blocks: `tool_result`, with `is_error`),
- `result` (final message in `result`, plus `subtype`, `num_turns`, `session_id`).

What this script does, and what breaks without it:

- Prints one line per step as it happens, e.g. `[#155] Edit src/refdesk/loop.py`.
  Without it Joe sees nothing until the run ends.
- Saves every raw line to the `.jsonl` file and the final message to the `.txt` file, so a
  run can be reviewed afterwards. Unknown event types are shown, not dropped; malformed lines
  are shown and the stream carries on (a formatter bug must never kill a run).
- Writes the session ID to a file, so the runner can log it and `claude --resume <id>`
  reopens the run.
- Enforces the wall-clock timeout (`Start-Job` gave this for free): on timeout it kills the
  whole process tree and exits 124.

The formatting is plain, tested Python, like the picker and loop_git.py. Event shapes follow
the Claude Code / Agent SDK stream-json format; check them against the installed version.

Usage (the runner calls this; the prompt is read from a file to avoid PowerShell quoting):
  uv run python scripts/loop_stream.py --issue N --prompt-file P --jsonl J --final T \
      --session-out S --timeout-minutes 30 -- claude -p --output-format stream-json --verbose

The prompt is appended as the last argument of the command.

Exit codes: 124 timeout, otherwise the command's own exit code.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

TIMEOUT_EXIT = 124
WIDTH = 120


def _clip(text: str, width: int = WIDTH) -> str:
    """One line, at most `width` characters."""
    line = " ".join(str(text).split())
    return line if len(line) <= width else line[: width - 3] + "..."


def _tool_summary(name: str, tool_input: object) -> str:
    """`Edit src/x.py`, `Bash uv run pytest -q`: the tool and its most telling argument."""
    if not isinstance(tool_input, dict):
        return _clip(f"{name} {tool_input}")
    for key in ("command", "file_path", "path", "pattern", "url", "query", "description"):
        value = tool_input.get(key)
        if value:
            return _clip(f"{name} {value}")
    return _clip(f"{name} {json.dumps(tool_input, ensure_ascii=False)}")


def _result_text(content: object) -> str:
    if isinstance(content, list):
        parts = [c.get("text", "") for c in content if isinstance(c, dict)]
        return " ".join(p for p in parts if p)
    return "" if content is None else str(content)


class StreamFormatter:
    """Turns stream-json lines into step lines. Remembers tool-use IDs to name results."""

    def __init__(self, issue: int | str):
        self.tag = f"[#{issue}]"
        self.tools: dict[str, str] = {}
        self.session_id: str | None = None
        self.final: str | None = None

    def line(self, raw: str) -> list[str]:
        """Format one raw stream line. Never raises."""
        raw = raw.strip()
        if not raw:
            return []
        try:
            event = json.loads(raw)
        except ValueError:
            return [f"{self.tag} ? unparsed line: {_clip(raw, 80)}"]
        if not isinstance(event, dict):
            return [f"{self.tag} ? unparsed line: {_clip(raw, 80)}"]
        try:
            return self.event(event)
        except Exception as exc:  # a formatter bug must not stop the stream
            kind = event.get("type")
            return [f"{self.tag} ? could not format {kind!r} ({exc}): {_clip(raw, 80)}"]

    def event(self, event: dict) -> list[str]:
        kind = event.get("type")
        if event.get("session_id"):
            self.session_id = event["session_id"]
        if kind == "system":
            subtype = event.get("subtype", "?")
            if subtype == "init":
                model = event.get("model", "?")
                return [f"{self.tag} session {event.get('session_id')} started ({model})"]
            return [f"{self.tag} system {subtype}"]
        if kind in ("assistant", "user"):
            content = (event.get("message") or {}).get("content")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            if not isinstance(content, list):
                return [f"{self.tag} {kind} (no content)"]
            return [self.block(kind, b) for b in content if isinstance(b, dict)]
        if kind == "result":
            self.final = event.get("result") or ""
            self.session_id = event.get("session_id") or self.session_id
            status = "error" if event.get("is_error") else "done"
            return [
                f"{self.tag} {status}: {event.get('subtype', '?')}, "
                f"{event.get('num_turns', '?')} turns, session {self.session_id}"
            ]
        return [f"{self.tag} ? {kind}: {_clip(json.dumps(event, ensure_ascii=False), 80)}"]

    def block(self, kind: str, block: dict) -> str:
        btype = block.get("type")
        if btype == "tool_use":
            summary = _tool_summary(block.get("name", "?"), block.get("input"))
            self.tools[block.get("id", "")] = summary
            return f"{self.tag} {summary}"
        if btype == "tool_result":
            name = self.tools.get(block.get("tool_use_id", ""), "tool").split(" ", 1)[0]
            if block.get("is_error"):
                return f"{self.tag}   {name} error: {_clip(_result_text(block.get('content')), 80)}"
            return f"{self.tag}   {name} ok"
        if btype == "text":
            who = "says" if kind == "assistant" else "user"
            return f"{self.tag} {who}: {_clip(block.get('text', ''), 100)}"
        if btype == "thinking":
            return f"{self.tag} (thinking)"
        return f"{self.tag} ? {kind} block {btype}"


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the command and its children (claude.cmd -> node on Windows)."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        proc.kill()


def run(
    command: list[str],
    issue: int | str,
    jsonl: Path,
    final: Path,
    session_out: Path | None,
    timeout_s: float,
    out=None,
) -> int:
    """Run `command`, stream its stdout through the formatter, enforce the timeout."""
    out = out or sys.stdout
    fmt = StreamFormatter(issue)
    exe = shutil.which(command[0]) or command[0]
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [exe, *command[1:]],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        encoding="utf-8",
        errors="replace",
    )
    timed_out = threading.Event()

    def on_timeout() -> None:
        timed_out.set()
        _kill_tree(proc)

    timer = threading.Timer(timeout_s, on_timeout)
    timer.start()
    try:
        with jsonl.open("w", encoding="utf-8") as raw_log:
            for raw in proc.stdout:
                raw_log.write(raw)
                raw_log.flush()
                for text in fmt.line(raw):
                    print(text, file=out, flush=True)
        code = proc.wait()
    finally:
        timer.cancel()
    if timed_out.is_set():
        print(f"{fmt.tag} killed: timeout after {timeout_s / 60:g} min", file=out, flush=True)
        code = TIMEOUT_EXIT
    message = fmt.final if fmt.final is not None else "(no final result event)\n"
    final.write_text(message, encoding="utf-8")
    if session_out is not None:
        session_out.write_text(fmt.session_id or "", encoding="utf-8")
    return code


def replay(lines, issue: int | str, out=None) -> int:
    """Format a saved `.jsonl` stream, for review after a run."""
    out = out or sys.stdout
    fmt = StreamFormatter(issue)
    for raw in lines:
        for text in fmt.line(raw):
            print(text, file=out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--issue", required=True)
    parser.add_argument("--replay", action="store_true", help="format a saved stream from stdin")
    parser.add_argument("--prompt-file", type=Path, help="appended as the command's last argument")
    parser.add_argument("--jsonl", type=Path)
    parser.add_argument("--final", type=Path)
    parser.add_argument("--session-out", type=Path)
    parser.add_argument("--timeout-minutes", type=float)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    # The Windows console is often cp1252: never crash on a character from the stream.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    if args.replay:
        return replay(sys.stdin, args.issue)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command given after --")
    if args.jsonl is None or args.final is None or args.timeout_minutes is None:
        parser.error("--jsonl, --final and --timeout-minutes are required to run a command")
    if args.prompt_file:
        command = [*command, args.prompt_file.read_text(encoding="utf-8")]
    return run(
        command, args.issue, args.jsonl, args.final, args.session_out, args.timeout_minutes * 60
    )


if __name__ == "__main__":
    sys.exit(main())
