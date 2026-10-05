"""Build dist/sayrift-Setup-<version>.exe.

1. PyInstaller --onedir app (folder, no UPX: single-file + keyboard hook trips antivirus heuristics)
2. zip that folder into build/payload.zip
3. Build a replaceable --onedir Qt setup, inside a stdlib-only extractable envelope

Usage: uv run python tools/build_installer.py        (about 2 minutes; nothing is installed)
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from bundle_notices import collect
from windows_audio_artifact import verified_audio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from local_typeless import __version__  # noqa: E402

BUILD, DIST = ROOT / "build", ROOT / "dist"
ICON = ROOT / "src" / "local_typeless" / "assets" / "app.ico"
APP = DIST / "sayrift"


def version_file(name: str, description: str) -> Path:
    """Windows 'Details' tab: product name and version instead of blank fields."""
    parts = [*map(int, re.findall(r"\d+", __version__)), 0, 0, 0][:4]
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={tuple(parts)}, prodvers={tuple(parts)}),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('ProductName', 'Sayrift'),
    StringStruct('FileDescription', '{description}'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('ProductVersion', '{__version__}'),
    StringStruct('OriginalFilename', '{name}.exe'),
    StringStruct('LegalCopyright', ''),
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)"""
    path = BUILD / f"{name}.version.txt"
    path.write_text(text, encoding="utf-8")
    return path


def pyinstaller(*args: str) -> None:
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--noupx",
           "--icon", str(ICON), "--collect-data", "local_typeless", "--specpath", str(BUILD),
           "--exclude-module", "tkinter", *args]  # fmt: skip
    subprocess.run(cmd, check=True, cwd=ROOT)


def prepare_folder(folder: Path) -> None:
    """Remove unused optional native binaries and retain audit evidence beside each executable."""
    for candidate in (folder / "_internal" / "_sounddevice_data").rglob("*"):
        if candidate.is_file() and candidate.suffix in {".dll", ".dylib"} and candidate.name != "libportaudio64bit.dll":
            candidate.unlink()
    # This application uses raster Qt Widgets, not OpenGL/Quick widgets. Qt's offscreen
    # raster probe is checked after packaging; hardware OpenGL remains available.
    (folder / "_internal" / "PySide6" / "opengl32sw.dll").unlink(missing_ok=True)
    # Qt uses the Windows Schannel TLS backend. The optional OpenSSL plugin can
    # otherwise pull DLLs from unrelated software on the build machine's PATH.
    (folder / "_internal/PySide6/plugins/tls/qopensslbackend.dll").unlink(missing_ok=True)
    for filename in ("libcrypto-3-x64.dll", "libssl-3-x64.dll"):
        (folder / "_internal" / filename).unlink(missing_ok=True)
    # Windows 11 supplies these OS components. Do not redistribute System32 copies.
    for candidate in (folder / "_internal").glob("api-ms-win-*.dll"):
        candidate.unlink()
    (folder / "_internal/ucrtbase.dll").unlink(missing_ok=True)
    for metadata in (folder / "_internal").glob("*.dist-info"):
        for filename in ("direct_url.json", "uv_build.json", "uv_cache.json", "RECORD"):
            (metadata / filename).unlink(missing_ok=True)
    collect(folder / "licenses", ROOT)
    audio = folder / "_internal/_soundfile_data/libsndfile_x64.dll"
    if audio.is_file():
        replacement = verified_audio()
        shutil.copy2(replacement, audio)
        shutil.copytree(
            replacement.parent,
            folder / "licenses/audio-build",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("*.dll"),
        )
    shutil.copy2(ROOT / "docs" / "windows-library-replacement.md", folder / "licenses" / "LIBRARY-REPLACEMENT.md")


def archive_folder(folder: Path, output: Path) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(folder.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(folder))


def main() -> int:
    try:
        verified_audio()
    except (ValueError, OSError, KeyError):
        subprocess.run([sys.executable, str(ROOT / "tools/build_windows_audio.py")], check=True, cwd=ROOT)
        verified_audio()
    BUILD.mkdir(exist_ok=True)
    if APP.resolve().parent != DIST.resolve() or APP.is_symlink() or APP.is_junction():
        raise ValueError("Build output must stay inside this checkout's dist directory")
    shutil.rmtree(APP, ignore_errors=True)
    pyinstaller("--onedir", "--name", "sayrift", "--copy-metadata", "sayrift",
                "--runtime-hook", str(ROOT / "tools" / "windows_runtime_hook.py"),
                "--version-file", str(version_file("sayrift", "Sayrift voice dictation")),
                "--distpath", str(DIST), "--workpath", str(BUILD / "app"),
                str(ROOT / "packaging" / "app_entry.py"))  # fmt: skip

    prepare_folder(APP)
    payload = BUILD / "payload.zip"
    archive_folder(APP, payload)

    setup_name = f"sayrift-Setup-{__version__}"
    pyinstaller("--onedir", "--name", "SayriftSetup",
                "--runtime-hook", str(ROOT / "tools" / "windows_runtime_hook.py"),
                "--version-file", str(version_file(setup_name, "Sayrift Setup")),
                "--add-data", f"{payload};.", "--distpath", str(DIST), "--workpath", str(BUILD / "setup"),
                "--exclude-module", "numpy", "--exclude-module", "sounddevice", "--exclude-module", "soundfile",
                str(ROOT / "packaging" / "setup_main.py"))  # fmt: skip
    prepare_folder(DIST / "SayriftSetup")
    archive_folder(DIST / "SayriftSetup", BUILD / "setup.zip")
    pyinstaller("--onefile", "--name", setup_name,
                "--version-file", str(version_file(setup_name, "Sayrift Setup")),
                "--add-data", f"{BUILD / 'setup.zip'};.",
                "--distpath", str(DIST), "--workpath", str(BUILD / "envelope"),
                "--exclude-module", "PySide6", "--exclude-module", "shiboken6",
                "--exclude-module", "numpy", "--exclude-module", "sounddevice", "--exclude-module", "soundfile",
                str(ROOT / "tools" / "windows_setup_launcher.py"))  # fmt: skip
    setup = DIST / f"{setup_name}.exe"
    print(f"{setup}  ({setup.stat().st_size / 1e6:.0f} MB; app folder {payload.stat().st_size / 1e6:.0f} MB zipped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
