"""Collect installed dependency notices for the Windows build; not a license-compliance certification."""

from __future__ import annotations

import json
import shutil
import sys
from importlib.metadata import distributions
from pathlib import Path


def collect(destination: Path, root: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    inventory = []
    for dist in sorted(distributions(), key=lambda d: d.metadata.get("Name", "").lower()):
        name = dist.metadata.get("Name", "unknown")
        copied = []
        for entry in dist.files or []:
            path = Path(str(entry))
            # Include license subtrees (including vendored licenses), but not executable library code.
            if not any(
                part.lower() in {"licenses", "licensing"} for part in path.parts
            ) and not path.name.lower().startswith(("license", "copying", "notice", "authors")):
                continue
            if path.suffix.lower() in {".py", ".pyc", ".dll", ".so", ".exe"} or ".." in path.parts:
                continue
            source = Path(dist.locate_file(entry))
            if not source.is_file():
                continue
            target = destination / "python" / name / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target.relative_to(destination).as_posix())
        inventory.append(
            {
                "name": name,
                "version": dist.version,
                "declared_license": dist.metadata.get("License-Expression") or dist.metadata.get("License"),
                "notice_files": copied,
            }
        )
    # This is a conservative build-environment inventory; it includes development tools too.
    (destination / "python-inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, destination / "Python-LICENSE.txt")
    notices = root / "THIRD_PARTY_NOTICES.md"
    if notices.is_file():
        shutil.copy2(notices, destination / notices.name)
    project_license = root / "LICENSE"
    if project_license.is_file():
        shutil.copy2(project_license, destination / "Sayrift-LICENSE.txt")
    if (root / "licenses").is_dir():
        shutil.copytree(root / "licenses", destination / "licenses", dirs_exist_ok=True)


if __name__ == "__main__":
    collect(Path(sys.argv[1]), Path(__file__).resolve().parents[1])
