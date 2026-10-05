"""Explicit release preparation: fetch pinned upstream assets, outside ordinary CI builds."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    destination = root / "dist" / "sources"
    destination.mkdir(parents=True, exist_ok=True)
    manifest = root / "tools" / "windows-sources.json"
    for entry in json.loads(manifest.read_text(encoding="utf-8")):
        target = destination / entry["file"]
        if target.is_file():
            with target.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() == entry["sha256"]:
                    continue
        temporary = target.with_suffix(target.suffix + ".part")
        with urllib.request.urlopen(entry["url"], timeout=120) as response, temporary.open("wb") as stream:
            while block := response.read(1024 * 1024):
                stream.write(block)
        with temporary.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
                raise ValueError(f"Source checksum mismatch: {target.name}")
        temporary.replace(target)
        print(f"Verified {target.name}", flush=True)
    (destination / "windows-sources.json").write_bytes(manifest.read_bytes())


if __name__ == "__main__":
    main()
