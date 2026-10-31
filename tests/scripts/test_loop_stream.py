"""Tests for scripts/loop_stream.py: live step lines and the stream log (issue #185)."""

import io
import json
import sys

import loop_stream
import pytest


def _j(event: dict) -> str:
    return json.dumps(event) + "\n"


TOOL_USE = _j({
    "type": "assistant",
    "session_id": "s-1",
    "message": {"content": [{
        "type": "tool_use", "id": "t1", "name": "Edit",
        "input": {"file_path": "src/refdesk/loop.py", "old_string": "a", "new_string": "b"},
    }]},
})  # fmt: skip
BASH_USE = _j({
    "type": "assistant",
    "message": {"content": [{
        "type": "tool_use", "id": "t2", "name": "Bash",
        "input": {"command": "uv run pytest -q", "description": "Run tests"},
    }]},
})  # fmt: skip
TOOL_RESULT_OK = _j({
    "type": "user",
    "message": {"content": [{"type": "tool_result", "tool_use_id": "t2", "content": "861 passed"}]},
})
TOOL_RESULT_ERR = _j({
    "type": "user",
    "message": {"content": [{
        "type": "tool_result", "tool_use_id": "t2", "is_error": True,
        "content": [{"type": "text", "text": "Exit code 1\n3 failed"}],
    }]},
})  # fmt: skip
FINAL = _j({
    "type": "result", "subtype": "success", "is_error": False, "num_turns": 7,
    "result": "All criteria met.", "session_id": "s-1",
})  # fmt: skip


@pytest.fixture
def fmt():
    return loop_stream.StreamFormatter(155)


class TestOneLinePerEvent:
    def test_tool_use_is_one_line_naming_tool_and_file(self, fmt):
        assert fmt.line(TOOL_USE) == ["[#155] Edit src/refdesk/loop.py"]

    def test_bash_tool_use_shows_the_command(self, fmt):
        assert fmt.line(BASH_USE) == ["[#155] Bash uv run pytest -q"]

    def test_tool_result_is_one_line_named_after_its_tool_use(self, fmt):
        fmt.line(BASH_USE)
        assert fmt.line(TOOL_RESULT_OK) == ["[#155]   Bash ok"]

    def test_failed_tool_result_is_one_line_with_the_error(self, fmt):
        fmt.line(BASH_USE)
        [line] = fmt.line(TOOL_RESULT_ERR)
        assert line.startswith("[#155]   Bash error: Exit code 1")
        assert "\n" not in line

    def test_final_result_is_one_line_and_keeps_the_message_and_session(self, fmt):
        [line] = fmt.line(FINAL)
        assert line == "[#155] done: success, 7 turns, session s-1"
        assert fmt.final == "All criteria met."
        assert fmt.session_id == "s-1"

    def test_init_records_the_session_id(self, fmt):
        init = _j({"type": "system", "subtype": "init", "session_id": "s-9", "model": "m"})
        assert fmt.line(init) == ["[#155] session s-9 started (m)"]
        assert fmt.session_id == "s-9"

    def test_long_commands_are_clipped_to_one_line(self, fmt):
        cmd = "echo " + "x" * 500 + "\nsecond line"
        use = _j({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": cmd}}
        ]}})  # fmt: skip
        [line] = fmt.line(use)
        assert "\n" not in line and len(line) <= loop_stream.WIDTH + len("[#155] ")


class TestNothingDropped:
    def test_unknown_event_type_is_shown(self, fmt):
        [line] = fmt.line(_j({"type": "stream_event", "event": {"x": 1}}))
        assert line.startswith("[#155] ? stream_event")

    def test_unknown_block_type_is_shown(self, fmt):
        event = _j({"type": "assistant", "message": {"content": [{"type": "image"}]}})
        assert fmt.line(event) == ["[#155] ? assistant block image"]

    def test_unknown_system_subtype_is_shown(self, fmt):
        assert fmt.line(_j({"type": "system", "subtype": "compact_boundary"})) == [
            "[#155] system compact_boundary"
        ]

    @pytest.mark.parametrize("raw", ["not json\n", "{truncated", "[1, 2]\n", '"a string"\n'])
    def test_malformed_lines_are_shown_and_do_not_raise(self, fmt, raw):
        [line] = fmt.line(raw)
        assert line.startswith("[#155] ? unparsed line:")

    def test_odd_shapes_inside_a_known_type_do_not_raise(self, fmt):
        assert fmt.line(_j({"type": "assistant", "message": None})) == [
            "[#155] assistant (no content)"
        ]

    def test_blank_lines_are_ignored(self, fmt):
        assert fmt.line("\n") == []


def _fake_claude(tmp_path, body: str) -> list[str]:
    script = tmp_path / "fake_claude.py"
    script.write_text(body, encoding="utf-8")
    return [sys.executable, str(script)]


def test_replay_formats_a_saved_stream():
    out = io.StringIO()
    assert loop_stream.replay([TOOL_USE, "oops\n", FINAL], 155, out=out) == 0
    assert out.getvalue().splitlines() == [
        "[#155] Edit src/refdesk/loop.py",
        "[#155] ? unparsed line: oops",
        "[#155] done: success, 7 turns, session s-1",
    ]


class TestRun:
    def test_streams_saves_jsonl_final_message_and_session(self, tmp_path):
        lines = [TOOL_USE, "garbage\n", BASH_USE, TOOL_RESULT_OK, FINAL]
        cmd = _fake_claude(tmp_path, f"import sys\nsys.stdout.write({''.join(lines)!r})\n")
        out = io.StringIO()
        paths = {k: tmp_path / f"loop.{k}" for k in ("jsonl", "txt", "session")}
        code = loop_stream.run(
            cmd, 155, paths["jsonl"], paths["txt"], paths["session"], timeout_s=60, out=out
        )
        assert code == 0
        shown = out.getvalue().splitlines()
        assert shown == [
            "[#155] Edit src/refdesk/loop.py",
            "[#155] ? unparsed line: garbage",
            "[#155] Bash uv run pytest -q",
            "[#155]   Bash ok",
            "[#155] done: success, 7 turns, session s-1",
        ]
        assert paths["jsonl"].read_text(encoding="utf-8") == "".join(lines)
        assert paths["txt"].read_text(encoding="utf-8") == "All criteria met."
        assert paths["session"].read_text(encoding="utf-8") == "s-1"

    def test_passes_through_the_command_exit_code(self, tmp_path):
        cmd = _fake_claude(tmp_path, "import sys\nsys.exit(3)\n")
        code = loop_stream.run(
            cmd, 1, tmp_path / "j", tmp_path / "t", None, timeout_s=60, out=io.StringIO()
        )
        assert code == 3
        assert (tmp_path / "t").read_text(encoding="utf-8") == "(no final result event)\n"

    def test_timeout_kills_the_command_and_exits_124(self, tmp_path):
        body = (
            "import sys, time\n"
            f"sys.stdout.write({TOOL_USE!r}); sys.stdout.flush()\n"
            "time.sleep(60)\n"
        )
        out = io.StringIO()
        code = loop_stream.run(
            _fake_claude(tmp_path, body), 7, tmp_path / "j", tmp_path / "t", None,
            timeout_s=1.5, out=out,
        )  # fmt: skip
        assert code == loop_stream.TIMEOUT_EXIT
        shown = out.getvalue().splitlines()
        assert shown[0] == "[#7] Edit src/refdesk/loop.py"  # streamed before the kill
        assert shown[-1].startswith("[#7] killed: timeout")
