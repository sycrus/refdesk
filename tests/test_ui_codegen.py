"""Design tokens and fixed wording generated for the UI (issue #42).

The UI's colours and status labels come from one source each: design/tokens.json and
src/refdesk/wording.py. These tests check the contrast the design system claims, and fail
CI when a committed generated file no longer matches its source.
"""

import re
from pathlib import Path

import pytest

from refdesk import wording
from refdesk.ui_codegen import (
    OUTPUTS,
    contrast_ratio,
    load_tokens,
    render_tokens_css,
    render_wording_ts,
)

ROOT = Path(__file__).resolve().parents[1]
TOKENS = load_tokens(ROOT / "design" / "tokens.json")
COLORS = {t["name"]: t["value"] for t in TOKENS["color"]["tokens"]}
THEMES = ("light", "dark")

# (foreground, background, minimum). design-system.md: text 4.5:1 on its ground in both
# themes, control borders and focus rings 3:1. Higher minimums are the ones tokens.json
# states for that token.
PAIRS = [
    ("ink", "paper", 4.5),
    ("ink", "card", 4.5),
    ("ink", "sunken", 4.5),
    ("ink-muted", "paper", 6.0),
    ("ink-muted", "card", 6.0),
    ("ink-muted", "sunken", 6.0),
    ("accent", "paper", 4.5),  # links
    ("accent", "card", 4.5),
    ("accent", "accent-soft", 4.5),
    ("on-accent", "accent", 4.5),
    ("ok", "ok-soft", 4.5),  # badge text on badge background
    ("warn", "warn-soft", 4.5),
    ("danger", "danger-soft", 4.5),
    ("ok", "card", 4.5),
    ("warn", "card", 4.5),
    ("danger", "card", 4.5),
    ("ok", "paper", 4.5),
    ("warn", "paper", 4.5),
    ("danger", "paper", 4.5),
    ("line-strong", "paper", 3.0),  # control borders
    ("line-strong", "card", 3.0),
    ("focus", "paper", 3.0),
    ("focus", "card", 3.0),
    ("on-scrim", "scrim", 4.5),  # the lightbox (issue 232)
]


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize(("fg", "bg", "minimum"), PAIRS)
def test_documented_pairs_meet_their_contrast(fg, bg, minimum, theme):
    assert contrast_ratio(COLORS[fg][theme], COLORS[bg][theme]) >= minimum


# Exact ratios stated in tokens.json usage notes; a token change must update the note.
STATED = [
    ("ink", "paper", "light", 15.7),
    ("on-accent", "accent", "light", 7.9),
    ("on-accent", "accent", "dark", 8.4),
    ("accent", "accent-soft", "light", 6.6),
    ("accent", "accent-soft", "dark", 6.6),
]


@pytest.mark.parametrize(("fg", "bg", "theme", "stated"), STATED)
def test_stated_ratios_match_the_tokens(fg, bg, theme, stated):
    assert contrast_ratio(COLORS[fg][theme], COLORS[bg][theme]) == pytest.approx(stated, abs=0.1)


def test_contrast_ratio_known_values():
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast_ratio("#FFFFFF", "#FFFFFF") == pytest.approx(1.0)
    assert contrast_ratio("#777777", "#FFFFFF") == pytest.approx(4.48, abs=0.01)


def test_css_defines_every_token_in_both_themes():
    css = render_tokens_css(TOKENS)
    light, dark = css.split("@media (prefers-color-scheme: dark)", 1)
    for name, value in COLORS.items():
        assert f"--color-{name}: {value['light']};" in light
        assert f"--color-{name}: {value['dark']};" in dark
    for group in ("spacing", "radius"):
        for token in TOKENS[group]["tokens"]:
            assert f"--{token['name']}: {token['value']};" in css


def test_dark_theme_follows_the_system_unless_light_is_forced_and_can_be_forced():
    css = render_tokens_css(TOKENS)
    assert ':root:not([data-theme="light"])' in css
    assert ':root[data-theme="dark"]' in css


def test_wording_ts_carries_every_label_verbatim():
    ts = render_wording_ts(wording)
    for enum in (wording.RightsStatus, wording.AttributionStatus, wording.StopReason):
        for member in enum:
            assert f"{member.name}: {_js(member.value)}" in ts
    for reason in wording.StopReason:
        assert f"{reason.value}: {_js(reason.banner)}" in ts
    assert f"export const EXPORTED = {_js(wording.EXPORTED)};" in ts
    assert f"export const NOT_LEGAL_ADVICE = {_js(wording.NOT_LEGAL_ADVICE)};" in ts


@pytest.mark.parametrize("output", OUTPUTS, ids=lambda o: o.path)
def test_committed_generated_files_are_current(output):
    # Regenerate with: uv run python scripts/generate_ui.py
    committed = (ROOT / output.path).read_text(encoding="utf-8")
    assert committed == output.render(ROOT), f"{output.path} is stale"


HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
# Comments are stripped before the scan: "#158" in a comment is an issue reference, not a
# colour, and it failed this test twice (#146, #158). Line comments must start a line or
# follow whitespace, so "https://..." inside a string is not cut.
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT = re.compile(r"(^|\s)//[^\n]*", re.MULTILINE)


def hex_colours(text: str) -> list[str]:
    code = LINE_COMMENT.sub(r"\1", BLOCK_COMMENT.sub("", text))
    return HEX.findall(code)


@pytest.mark.parametrize(
    "text",
    [
        "/* S2 kill switch (#158): cancel */ .a { color: var(--x); }",
        "/*\n * issue #146\n */",
        "// Report form (#146)\nconst a = 1;",
        "const x = 1; // see #abc",
        'const u = "https://example.org/a"; // #158',
    ],
)
def test_hex_scan_ignores_issue_references_in_comments(text):
    assert hex_colours(text) == []


@pytest.mark.parametrize(
    "text",
    [
        ".a { color: #fff; }",
        "/* note */ .a { background: #1a2b3c; }",
        'const c = "#158";',
        "const style = { color: '#abcdef' }; // fine comment",
    ],
)
def test_hex_scan_still_catches_colours_in_code(text):
    assert hex_colours(text) != []


def test_ui_source_has_no_hardcoded_hex_colours():
    # CLAUDE.md: colours come from tokens only. Generated files are the one exception.
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "ui" / "src").rglob("*")
        if path.suffix in {".css", ".ts", ".tsx"}
        and "generated" not in path.parts
        and hex_colours(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def _js(text: str) -> str:
    import json

    return json.dumps(text, ensure_ascii=False)


# --- Fonts and the type scale (issue #228) ---------------------------------------------

SCALE = {s["name"] for g in TOKENS["type"]["groups"] for s in g["styles"]}


def test_every_font_face_is_self_hosted_and_its_file_and_licence_are_committed():
    """No font request to a third party: each src is a path under ui/public."""
    css = render_tokens_css(TOKENS)
    for font in TOKENS["type"]["fonts"]:
        assert font["src"].startswith("/fonts/"), font["src"]
        assert (ROOT / "ui" / "public" / font["src"].lstrip("/")).is_file()
        licence = font["license"].split(", ")[-1]
        assert (ROOT / licence).is_file(), licence
        assert f"font-family: \"{font['family']}\";" in css
        assert f"url(\"{font['src']}\") format(\"woff2\")" in css
    assert "http" not in css


def test_the_wordmark_has_its_own_style_and_nothing_else_uses_the_logo_family():
    assert "logo" in SCALE
    uses = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "ui" / "src").rglob("*.css")
        if "generated" not in path.parts
        and "--type-logo-family" in path.read_text(encoding="utf-8")
    ]
    assert uses and all("rd-app-brand" in (ROOT / u).read_text(encoding="utf-8") for u in uses)


FONT_SIZE = re.compile(r"font-size\s*:\s*([^;}]+)")
ALLOWED = re.compile(r"^var\(--type-([a-z0-9-]+)-size\)$")


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        (".a { font-size: var(--type-body-size); }", True),
        (".a { font-size: 13px; }", False),
        (".a { font-size: var(--type-huge-size); }", False),
        (".a { font: 400 16px/24px serif; }", False),
        (".a { font-size: inherit; }", True),
    ],
)
def test_the_type_scale_check_itself(text, ok):
    assert (type_scale_offences(text) == []) is ok


def type_scale_offences(text: str) -> list[str]:
    """Font sizes outside the token scale: a size must be var(--type-<style>-size) for a
    style in tokens.json (or inherit). The `font` shorthand with a size is refused too."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    bad = []
    for value in FONT_SIZE.findall(text):
        value = value.strip()
        m = ALLOWED.match(value)
        if value != "inherit" and not (m and m.group(1) in SCALE):
            bad.append(value)
    bad += re.findall(r"\bfont\s*:\s*[^;}]*\d+px[^;}]*", text)
    return bad


def test_ui_css_uses_only_the_type_scale():
    offenders = {
        path.relative_to(ROOT).as_posix(): type_scale_offences(path.read_text(encoding="utf-8"))
        for path in (ROOT / "ui" / "src").rglob("*.css")
        if "generated" not in path.parts
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_every_ui_stylesheet_has_balanced_braces():
    """An unclosed rule makes the browser swallow every rule after it, including whole
    stylesheets bundled later, with no error anywhere (a merge did this once, #234)."""
    unbalanced = {}
    for path in (ROOT / "ui" / "src").rglob("*.css"):
        text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        if text.count("{") != text.count("}"):
            unbalanced[path.relative_to(ROOT).as_posix()] = text.count("{") - text.count("}")
    assert unbalanced == {}
