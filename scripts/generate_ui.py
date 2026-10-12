"""Write the UI's generated files: design tokens as CSS and the fixed wording as TypeScript.

Both come from a single source (design/tokens.json, src/refdesk/wording.py); a test fails
if a committed file is stale. Usage: uv run python scripts/generate_ui.py
"""

from pathlib import Path

from refdesk.ui_codegen import OUTPUTS

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    for output in OUTPUTS:
        path = ROOT / output.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(output.render(ROOT).encode("utf-8"))  # LF on every OS
        print(f"wrote {output.path}")
