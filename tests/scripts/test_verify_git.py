"""End-to-end: run verify.main() against real staged changes in a throwaway git repo."""

import subprocess

import pytest

import verify

GOLDEN = "evals/golden/golden-v1.jsonl"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "test")
    (tmp_path / "evals/golden").mkdir(parents=True)
    (tmp_path / GOLDEN).write_text('{"id": 1}\n')
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "freeze golden-v1")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_clean_change_passes(repo):
    (repo / "notes.md").write_text("hello\n")
    git(repo, "add", "-A")
    assert verify.main([]) == 0


def test_modified_frozen_file_fails(repo):
    (repo / GOLDEN).write_text('{"id": 2}\n')
    git(repo, "add", "-A")
    assert verify.main([]) == 1


def test_deleted_frozen_file_fails(repo):
    git(repo, "rm", "-q", GOLDEN)
    assert verify.main([]) == 1


def test_renamed_frozen_file_fails(repo):
    git(repo, "mv", GOLDEN, "evals/golden/renamed.jsonl")
    assert verify.main([]) == 1


def test_new_golden_version_passes(repo):
    (repo / "evals/golden/golden-v2.jsonl").write_text('{"id": 1}\n')
    git(repo, "add", "-A")
    assert verify.main([]) == 0


def test_staged_env_fails(repo):
    (repo / ".env").write_text("GLM_API_KEY=\n")
    git(repo, "add", "-A")
    assert verify.main([]) == 1
