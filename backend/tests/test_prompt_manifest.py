"""Prompt text cannot change without a version bump. [AI-06]"""
from __future__ import annotations

import pytest

from infrastructure.ai.prompt_manifest import ManifestError, check, load_manifest, refresh
from infrastructure.ai.prompts_fs import FilePromptStore

PROMPT = '---\nversion: {v}\nowner: product\nchangelog:\n  - "1: first"\n{extra}---\n{body}\n'


def write(directory, body="Be brief.", version=1, extra=""):
    text = PROMPT.format(v=version, body=body, extra=extra)
    (directory / "agent.md").write_bytes(text.encode("utf-8"))  # bytes: LF on every platform


def fresh(directory):
    return FilePromptStore(directory)


def recorded(directory):
    return refresh(fresh(directory), {"prompts": {}})


def test_the_shipped_prompts_and_manifest_agree():
    assert check(FilePromptStore(), load_manifest()) == []


def test_editing_the_words_without_bumping_the_version_fails(tmp_path):
    write(tmp_path)
    manifest = recorded(tmp_path)
    write(tmp_path, body="Be very brief.")
    [problem] = check(fresh(tmp_path), manifest, tmp_path)
    assert "text changed but `version: 1` did not" in problem


def test_a_bump_that_is_not_recorded_fails_until_refreshed(tmp_path):
    write(tmp_path)
    manifest = recorded(tmp_path)
    write(tmp_path, body="Be very brief.", version=2, extra='  - "2: shorter"\n')
    [problem] = check(fresh(tmp_path), manifest, tmp_path)
    assert "version 2 is not in the manifest" in problem
    assert check(fresh(tmp_path), refresh(fresh(tmp_path), manifest), tmp_path) == []


def test_refresh_will_not_hide_an_unversioned_edit(tmp_path):
    write(tmp_path)
    manifest = recorded(tmp_path)
    write(tmp_path, body="Sneaky.")
    with pytest.raises(ManifestError, match="bump the version"):
        refresh(fresh(tmp_path), manifest)


def test_a_version_needs_a_changelog_line(tmp_path):
    write(tmp_path)
    manifest = recorded(tmp_path)
    write(tmp_path, body="Be very brief.", version=2)
    problems = check(fresh(tmp_path), refresh(fresh(tmp_path), manifest), tmp_path)
    assert problems == ["agent: the changelog has no line for version 2"]


def test_going_back_to_an_older_version_number_fails(tmp_path):
    write(tmp_path, version=2, extra='  - "2: second"\n')
    manifest = recorded(tmp_path)
    write(tmp_path, body="Earlier words.", version=1)
    manifest = refresh(fresh(tmp_path), manifest)
    assert any("older than a recorded version" in p for p in check(fresh(tmp_path), manifest, tmp_path))


def test_a_new_prompt_file_must_be_recorded_and_a_deleted_one_removed(tmp_path):
    write(tmp_path)
    manifest = recorded(tmp_path)
    (tmp_path / "other.md").write_text(PROMPT.format(v=1, body="x", extra=""), encoding="utf-8")
    assert check(fresh(tmp_path), manifest, tmp_path) == ["other: has no entry in the manifest — run scripts/prompt-manifest.py --refresh"]
    (tmp_path / "other.md").unlink()
    (tmp_path / "agent.md").unlink()
    assert check(fresh(tmp_path), manifest, tmp_path) == ["agent: is in the manifest but has no prompt file"]


def test_line_endings_do_not_change_the_hash(tmp_path):
    write(tmp_path)
    lf = recorded(tmp_path)
    (tmp_path / "agent.md").write_bytes((tmp_path / "agent.md").read_bytes().replace(b"\n", b"\r\n"))
    assert check(fresh(tmp_path), lf, tmp_path) == []
