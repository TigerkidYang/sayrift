"""Fail closed when packaging lacks the audio DLL built from this checkout's recipe."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verified_audio(directory: Path | None = None) -> Path:
    directory = directory or ROOT / "dist/windows-audio"
    dll = directory / "libsndfile_x64.dll"
    report_path = directory / "build-report.json"
    if not dll.is_file() or not report_path.is_file():
        raise ValueError("Build the pinned DLL first: .venv/Scripts/python.exe tools/build_windows_audio.py")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report["dll_sha256"] != digest(dll):
        raise ValueError("Rebuilt audio DLL checksum does not match build report")
    if report["recipe_sha256"] != digest(ROOT / "tools/build_windows_audio.py"):
        raise ValueError("Audio build recipe changed; rebuild the DLL")
    if report["patch_sha256"] != digest(ROOT / "tools/libsndfile-opus-only.json"):
        raise ValueError("Audio source patch changed; rebuild the DLL")
    if report["sources"] != json.loads((ROOT / "tools/windows-audio-sources.json").read_text()):
        raise ValueError("Audio source manifest changed; rebuild the DLL")
    data = dll.read_bytes()
    for marker in ("C:/Users/", "C:\\Users\\", str(ROOT), ROOT.as_posix()):
        if marker.lower().encode() in data.lower() or marker.lower().encode("utf-16-le") in data.lower():
            raise ValueError("Rebuilt audio DLL contains a private build path")
    return dll
