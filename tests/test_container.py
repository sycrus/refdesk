"""Static checks on the container image definition (issue #167, PRD 13A, ADR-025).

The image is built and scanned in CI (.github/workflows/container.yml), not here: these
tests catch the mistakes that would leak or bloat an image before any build runs.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
IGNORE = [
    line.strip()
    for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
]


def instructions(name: str) -> list[str]:
    joined = re.sub(r"\\\n\s*", " ", DOCKERFILE)  # continuation lines into one
    return re.findall(rf"^{name}\s+(.+)$", joined, flags=re.MULTILINE)


def test_runs_as_a_numeric_non_root_user():
    users = instructions("USER")
    assert users, "no USER instruction"
    assert users[-1].strip() not in {"0", "root"}
    assert users[-1].strip().split(":")[0].isdigit()


def stages() -> list[str]:
    return [m.split()[-1] for m in instructions("FROM") if " AS " in m.upper()]


def test_base_images_are_pinned_to_exact_versions():
    for image in instructions("FROM"):
        ref = image.split()[0]
        if ref in stages() or ref == "${REFDESK_IMAGE}":
            continue  # an earlier stage of this file, not a base image
        assert ":" in ref and not ref.endswith(":latest"), ref
        tag = ref.rsplit(":", 1)[1]
        assert re.search(r"\d+\.\d+", tag), f"{ref} is not pinned to a version"


def test_build_context_is_an_allowlist():
    # Everything is excluded first, then only what the build needs is let back in, so
    # .env, data/, runs/ and model weights can never reach the build context.
    assert IGNORE[0] == "*"
    allowed = {line[1:].rstrip("/") for line in IGNORE if line.startswith("!")}
    assert not allowed & {".env", "data", "runs", "models", ".git"}
    assert not any(a.startswith((".env", "data", "runs")) for a in allowed)


def test_nothing_secret_or_derived_is_copied():
    for copy in instructions("COPY"):
        assert not re.search(r"(^|\s)(\.env|data/|runs/|\.)(\s|$)", copy), copy


def test_no_torch_in_the_image():
    # The free host has about 512 MB (ADR-025): no embed extra, so CLIP cannot load and
    # the image must name a retriever that needs no torch.
    assert "--extra embed" not in DOCKERFILE and "--all-extras" not in DOCKERFILE
    assert re.search(r"REFDESK_RETRIEVER=jaccard", DOCKERFILE)


def test_has_a_healthcheck_on_healthz():
    assert any("/healthz" in h for h in instructions("HEALTHCHECK"))


def test_the_default_image_is_the_full_profile_and_demo_is_opt_in():
    # Render passes environment variables as build arguments; REFDESK_IMAGE=demo picks
    # the demo stage. Without it, the image is the normal runtime.
    assert re.search(r"^ARG REFDESK_IMAGE=runtime$", DOCKERFILE, flags=re.MULTILINE)
    assert instructions("FROM")[-1].split()[0] == "${REFDESK_IMAGE}"
    assert {"runtime", "demo"} <= set(stages())


def test_the_demo_stage_sets_the_read_only_profile():
    demo = DOCKERFILE.split("FROM runtime AS demo", 1)[1].split("FROM ", 1)[0]
    assert "REFDESK_PROFILE=demo" in demo
    assert "REFDESK_AUTO_RESUME=0" in demo


def test_demo_images_are_fetched_at_build_not_copied_from_the_repo():
    # The bundle holds URLs and hashes; images never enter git or the build context.
    assert "!demo/" in IGNORE
    allowed = [line for line in IGNORE if line.startswith("!")]
    assert not any(line.startswith("!data") or "images" in line for line in allowed)
