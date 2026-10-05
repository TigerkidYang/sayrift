"""Refresh checked-in native notices from the separately downloaded source archives."""

from __future__ import annotations

import json
import posixpath
import tarfile
from pathlib import Path


def collect(archive: Path, output: Path) -> None:
    selected = {}
    referenced = set()
    with tarfile.open(archive, "r|*") as bundle:
        for member in bundle:
            name = Path(member.name).name.lower()
            if not member.isfile():
                continue
            if name == "qt_attribution.json" or (
                name.startswith(("license", "copying", "copyright", "notice", "authors"))
                and Path(name).suffix not in {".cpp", ".h", ".py", ".cmake", ".png", ".jpg"}
                and member.size < 500_000
            ):
                content = bundle.extractfile(member).read().decode("utf-8", errors="replace")
                selected[member.name] = content
                if name == "qt_attribution.json":
                    data = json.loads(content, strict=False)
                    for item in data if isinstance(data, list) else [data]:
                        files = item.get("LicenseFile", [])
                        for filename in files if isinstance(files, list) else [files]:
                            referenced.add(posixpath.normpath(posixpath.join(posixpath.dirname(member.name), filename)))
    missing = referenced - selected.keys()
    if missing:
        with tarfile.open(archive, "r|*") as bundle:
            for member in bundle:
                if member.name in missing and member.isfile():
                    selected[member.name] = bundle.extractfile(member).read().decode("utf-8", errors="replace")
        if remaining := referenced - selected.keys():
            raise ValueError(f"Missing referenced license files: {remaining}")
    output.write_text(
        "\n\n".join(f"SOURCE FILE: {name}\n{content}" for name, content in sorted(selected.items())), encoding="utf-8"
    )


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    destination = root / "licenses/windows"
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("qtbase", "qtsvg", "qtimageformats", "pyside-setup"):
        archive = root / "dist/sources" / f"{name}-everywhere-src-6.11.2.tar.xz"
        collect(archive, destination / f"{name}-notices.txt")
