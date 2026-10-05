"""Stdlib-only setup envelope; extractable Qt setup keeps its libraries replaceable."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            target = (destination / entry.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("Unsafe setup archive path")
        bundle.extractall(destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract-to", type=Path, help="Extract replaceable setup without running or installing it")
    parser.add_argument("--silent", action="store_true")
    args = parser.parse_args()
    archive = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1] / "build")) / "setup.zip"
    if args.extract_to:
        extract(archive, args.extract_to)
        return 0
    with tempfile.TemporaryDirectory(prefix="sayrift-setup-") as temporary:
        target = Path(temporary) / "setup"
        extract(archive, target)
        env = os.environ.copy()
        # The child is a different frozen application, not a subprocess of this bundle.
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        return subprocess.call([str(target / "SayriftSetup.exe"), *(["--silent"] if args.silent else [])], env=env)


if __name__ == "__main__":
    raise SystemExit(main())
