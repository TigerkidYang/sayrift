"""Public exports must not bring private history, recordings or working-copy state with them."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("public_export", Path(__file__).parents[1] / "tools/export_public.py")
public_export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public_export)


def run_git(root, *args, input=None):
    return subprocess.check_output(["git", "-C", str(root), *args], input=input)


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    run_git(root, "init", "-q")
    files = {
        "LICENSE": "MIT test fixture",
        "packaging/public/AGENTS.md": "Public instructions",
        "AGENTS.md": "Private development details",
        "src/app.py": "print('committed')",
        "docs/research/private.md": "Private research",
        "evals/asr/audio/example.ogg": "Private audio",
        "android/local.properties": "sdk.dir=private",
        "android/dev.json": "test configuration",
        "android/key.jks": "private key placeholder",
        "android/build/output.apk": "build",
        "README.md": "Public readme",
    }
    for name, data in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data, encoding="utf-8")
    run_git(root, "add", ".")
    run_git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
    return root


def test_export_reads_committed_allowlist_and_replaces_private_instructions(repository, tmp_path):
    (repository / "src/app.py").write_text("uncommitted private change")
    (repository / "src/untracked.py").write_text("untracked private file")
    destination = tmp_path / "public"
    public_export.export(repository, destination)
    assert (destination / "src/app.py").read_text() == "print('committed')"
    assert (destination / "AGENTS.md").read_text() == "Public instructions"
    assert not (destination / ".git").exists()
    assert not (destination / "docs/research").exists()
    assert not (destination / "evals/asr/audio").exists()
    assert not (destination / "src/untracked.py").exists()
    assert not (destination / "android").exists()
    manifest = json.loads((destination / "PUBLICATION.json").read_text())
    assert "src/app.py" in manifest["files"]


def test_export_refuses_existing_or_nested_destination(repository, tmp_path):
    destination = tmp_path / "occupied"
    destination.mkdir()
    (destination / "keep").write_text("unchanged")
    with pytest.raises(FileExistsError):
        public_export.export(repository, destination)
    with pytest.raises(ValueError):
        public_export.export(repository, repository / "nested")
    assert (destination / "keep").read_text() == "unchanged"


def test_export_rejects_tracked_symlinks_before_creating_output(repository, tmp_path):
    oid = run_git(repository, "hash-object", "-w", "--stdin", input=b"../../private").decode().strip()
    run_git(repository, "update-index", "--add", "--cacheinfo", "120000", oid, "src/linked")
    run_git(repository, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "link")
    with pytest.raises(ValueError, match="links"):
        public_export.export(repository, tmp_path / "public")
    assert not (tmp_path / "public").exists()
