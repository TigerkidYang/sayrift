"""Build dist/sayrift-Setup-<version>.exe.

1. PyInstaller --onedir app (folder, no UPX: single-file + keyboard hook trips antivirus heuristics)
2. zip that folder into build/payload.zip
3. PyInstaller --onefile setup program with the payload inside

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


def main() -> int:
    BUILD.mkdir(exist_ok=True)
    if APP.resolve().parent != DIST.resolve() or APP.is_symlink() or APP.is_junction():
        raise ValueError("Build output must stay inside this checkout's dist directory")
    shutil.rmtree(APP, ignore_errors=True)
    pyinstaller("--onedir", "--name", "sayrift", "--copy-metadata", "sayrift",
                "--version-file", str(version_file("sayrift", "Sayrift voice dictation")),
                "--distpath", str(DIST), "--workpath", str(BUILD / "app"),
                str(ROOT / "packaging" / "app_entry.py"))  # fmt: skip

    # Editable-install/cache records contain this developer's checkout and environment paths.
    for metadata in (APP / "_internal").glob("*.dist-info"):
        for filename in ("direct_url.json", "uv_build.json", "uv_cache.json", "RECORD"):
            (metadata / filename).unlink(missing_ok=True)

    collect(APP / "licenses", ROOT)

    payload = BUILD / "payload.zip"
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(APP.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(APP))

    setup_name = f"sayrift-Setup-{__version__}"
    pyinstaller("--onefile", "--name", setup_name,
                "--version-file", str(version_file(setup_name, "Sayrift Setup")),
                "--add-data", f"{payload};.", "--distpath", str(DIST), "--workpath", str(BUILD / "setup"),
                "--exclude-module", "numpy", "--exclude-module", "sounddevice", "--exclude-module", "soundfile",
                str(ROOT / "packaging" / "setup_main.py"))  # fmt: skip
    setup = DIST / f"{setup_name}.exe"
    print(f"{setup}  ({setup.stat().st_size / 1e6:.0f} MB; app folder {payload.stat().st_size / 1e6:.0f} MB zipped)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
