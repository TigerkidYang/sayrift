"""Export a reviewed, allowlisted Git snapshot without copying private history or local state.

Usage: uv run python tools/export_public.py --output <new-directory> [--ref HEAD]
The destination must not exist. This tool never creates a remote, commits or pushes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath

ROOT_FILES = {
    ".gitattributes",
    ".gitignore",
    ".python-version",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "README.zh-CN.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "config.example.toml",
    "pyproject.toml",
    "uv.lock",
}
PREFIXES = ("src/", "android/", "tests/", "licenses/", ".github/", "packaging/public/")
DOCS = {
    "architecture.md",
    "compatibility.md",
    "manual-tests.md",
    "models.md",
    "product-spec.md",
    "references.md",
    "typeless-features.md",
    "release-notes.md",
    "binary-release.md",
    "windows-binary-evidence.md",
    "windows-native-inventory.json",
    "windows-library-replacement.md",
    "windows-audio-build.md",
    "windows-audio-build-report.json",
    "history-retention.md",
    "android-cancellation.md",
    "android-history-privacy.md",
    "images/windows-home.png",
}
TOOLS = {
    "android_emu.sh",
    "android_mock_openrouter.py",
    "bench_ask.py",
    "bench_asr.py",
    "bench_polish.py",
    "build_installer.py",
    "build_windows_audio.py",
    "collect_windows_source_notices.py",
    "prepare_windows_sources.py",
    "verify_windows_bundle.py",
    "windows_runtime_hook.py",
    "windows_setup_launcher.py",
    "windows_audio_artifact.py",
    "windows-sources.json",
    "windows-audio-sources.json",
    "libsndfile-opus-only.json",
    "bundle_notices.py",
    "e2e_dictation.py",
    "export_public.py",
    "make_icon.py",
    "ui_preview.py",
    "ui_smoke.py",
}
EXACT = {"packaging/app_entry.py", "packaging/setup_main.py", "evals/README.md", "evals/asr/samples.tsv"}
EXACT |= {"docs/" + name for name in DOCS} | {"tools/" + name for name in TOOLS}
EXACT |= {"evals/ask/cases.jsonl", "evals/polish/cases.jsonl"}
BLOCKED_PARTS = {".git", ".venv", "__pycache__", ".gradle", "build", "dist"}
BLOCKED_NAMES = {"local.properties", "key.properties", "signing.properties", "dev.json", "config.toml", ".env"}
BLOCKED_SUFFIXES = {
    ".ogg",
    ".wav",
    ".mp3",
    ".flac",
    ".sqlite",
    ".db",
    ".keystore",
    ".jks",
    ".log",
    ".apk",
    ".aab",
    ".p12",
    ".pfx",
    ".pem",
    ".sqlite-wal",
    ".sqlite-shm",
    ".db-wal",
    ".db-shm",
}


def public_path(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        return False
    if set(path.parts) & BLOCKED_PARTS or path.name in BLOCKED_NAMES or path.suffix in BLOCKED_SUFFIXES:
        return False
    if path.name.startswith(".env.") and path.name != ".env.example":
        return False
    return name in ROOT_FILES or name in EXACT or name.startswith(PREFIXES)


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args])


def snapshot(root: Path, ref: str) -> dict[str, tuple[str, bytes]]:
    commit = git(root, "rev-parse", "--verify", ref + "^{commit}").decode().strip()
    files = {}
    for entry in git(root, "ls-tree", "-rz", commit).split(b"\0"):
        if not entry:
            continue
        attributes, raw_name = entry.split(b"\t", 1)
        mode, kind, oid = attributes.decode().split()
        name = raw_name.decode("utf-8")
        if not public_path(name):
            continue
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"Public snapshots cannot contain links or submodules: {name}")
        files[name] = mode, git(root, "cat-file", "blob", oid)
    template = "packaging/public/AGENTS.md"
    if template not in files or "LICENSE" not in files:
        raise ValueError("Commit the public AGENTS template and project license before exporting")
    files["AGENTS.md"] = files[template]
    return files


def export(root: Path, destination: Path, ref: str = "HEAD") -> int:
    root, destination = root.resolve(), destination.resolve()
    if destination == root or root in destination.parents:
        raise ValueError("Export outside the development checkout")
    if destination.exists():
        raise FileExistsError("Use a new destination; exports never overwrite or delete existing files")
    files = snapshot(root, ref)
    destination.mkdir(parents=True)
    manifest = {}
    for name, (mode, data) in sorted(files.items()):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o755 if mode == "100755" else 0o644)
        manifest[name] = hashlib.sha256(data).hexdigest()
    (destination / "PUBLICATION.json").write_text(
        json.dumps({"format": 1, "files": manifest}, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ref", default="HEAD")
    args = parser.parse_args()
    count = export(Path(__file__).resolve().parents[1], args.output, args.ref)
    print(f"Exported {count} tracked public files to {args.output.resolve()}; no Git history copied.")


if __name__ == "__main__":
    main()
