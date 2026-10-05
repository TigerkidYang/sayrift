"""Offline release checks in isolated folders; never register/install or launch the main UI."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pefile

from local_typeless.win.install import replace_payload


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def native_inventory(folder: Path) -> list[dict]:
    rows = []
    for path in sorted(folder.rglob("*")):
        if path.suffix.lower() not in {".dll", ".pyd", ".exe"}:
            continue
        with pefile.PE(str(path), fast_load=True) as pe:
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
            rows.append(
                {
                    "file": path.relative_to(folder).as_posix(),
                    "sha256": digest(path),
                    "machine": hex(pe.FILE_HEADER.Machine),
                    "imports": [entry.dll.decode() for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", [])],
                }
            )
    return rows


def probe(executable: Path, output: Path) -> dict:
    subprocess.run([str(executable), "--library-probe", str(output)], check=True, timeout=60)
    return json.loads(output.read_text(encoding="utf-8"))


def patch_version(library: Path, original: bytes, replacement: bytes) -> None:
    data = library.read_bytes()
    if original not in data or len(original) != len(replacement):
        raise ValueError(f"Expected version marker missing in {library.name}")
    library.write_bytes(data.replace(original, replacement))


def verify(installer: Path, output: Path) -> None:
    report = {"installer": installer.name, "sha256": digest(installer)}
    with tempfile.TemporaryDirectory(prefix="sayrift-bundle-check-") as temporary:
        root = Path(temporary).resolve()
        setup = root / "setup"
        subprocess.run([str(installer), "--extract-to", str(setup)], check=True, timeout=120)
        assert (setup / "licenses" / "LIBRARY-REPLACEMENT.md").is_file()
        report["setup_native"] = native_inventory(setup)
        report["setup_original"] = probe(setup / "SayriftSetup.exe", root / "setup-original.json")
        patch_version(setup / "_internal/PySide6/Qt6Core.dll", b"6.11.2\0", b"6.11.9\0")
        report["setup_modified"] = probe(setup / "SayriftSetup.exe", root / "setup-modified.json")
        assert report["setup_modified"]["qt"] == "6.11.9"

        app = root / "Sayrift"
        payload = setup / "_internal/payload.zip"
        replace_payload(app, payload, lambda _: None)
        assert (app / "licenses" / "LIBRARY-REPLACEMENT.md").is_file()
        report["app_native"] = native_inventory(app)
        audio_build = json.loads((app / "licenses/audio-build/build-report.json").read_text(encoding="utf-8"))
        audio_path = "_internal/_soundfile_data/libsndfile_x64.dll"
        audio_pe = next(entry for entry in report["app_native"] if entry["file"] == audio_path)
        assert audio_pe["sha256"] == audio_build["dll_sha256"]
        assert all(
            name.lower() == "kernel32.dll" or name.lower().startswith("api-ms-win-crt-") for name in audio_pe["imports"]
        )
        report["rebuilt_audio_sha256"] = audio_pe["sha256"]
        assert not any("asio" in x["file"].lower() or "opengl32sw" in x["file"].lower() for x in report["app_native"])
        assert all(x["machine"] == "0x8664" for x in report["app_native"])
        report["app_original"] = probe(app / "sayrift.exe", root / "app-original.json")
        assert report["app_original"]["ca_count"] > 0
        assert report["app_original"]["pcm_roundtrip"]
        assert report["app_original"]["ogg_subtypes"] == ["OPUS"]
        assert not {"FLAC", "MP3"}.intersection(report["app_original"]["audio_formats"])
        patch_version(app / "_internal/PySide6/Qt6Core.dll", b"6.11.2\0", b"6.11.9\0")
        patch_version(app / "_internal/_soundfile_data/libsndfile_x64.dll", b"libsndfile-1.2.2", b"libsndfile-1.2.9")
        report["app_modified"] = probe(app / "sayrift.exe", root / "app-modified.json")
        assert report["app_modified"]["qt"] == "6.11.9"
        assert report["app_modified"]["sndfile"] == "1.2.9"
        assert report["app_modified"]["frames"] == 1600
        # Exercise the same replacement transaction used by upgrades, with unrelated files preserved.
        (app / "unrelated.txt").write_text("preserve", encoding="utf-8")
        replace_payload(app, payload, lambda _: None)
        assert (app / "unrelated.txt").read_text() == "preserve"
        with zipfile.ZipFile(payload) as archive:
            assert set(Path(name).parts[0] for name in archive.namelist()) <= {"sayrift.exe", "_internal", "licenses"}
        report["payload_install_and_upgrade"] = "passed; isolated folder, no registry or shortcuts"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Verified: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("installer", type=Path)
    parser.add_argument("--output", type=Path, default=Path("dist/windows-verification.json"))
    args = parser.parse_args()
    verify(args.installer.resolve(), args.output)
