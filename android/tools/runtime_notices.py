"""Generate public Android notices from Gradle's resolved artifacts and reviewed evidence.

Build-time generation is offline. Refresh is an explicit maintainer operation; review its
diff, including additional native/data licenses, before accepting a new dependency set.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import gzip
import hashlib
import io
import json
import re
import shutil
import struct
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ANDROID = Path(__file__).resolve().parents[1]
EVIDENCE = ANDROID / "notices"
LEGAL_NAME = re.compile(r"^(?:licen[sc]e|notice|copying|copyright|third[-_ ]?party|al2\.0|lgpl)(?:$|[._-])", re.I)
LEGAL_TEXT = re.compile(r"copyright|licensed under|permission is hereby|redistribution and use", re.I)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def artifact_rows(path: Path) -> list[dict]:
    rows = {}
    for item in json.loads(path.read_text(encoding="utf-8-sig")):
        if item["coordinate"].startswith("Sayrift:"):
            continue
        file = Path(item["file"])
        row = {"coordinate": item["coordinate"], "artifact": file.name, "sha256": digest(file.read_bytes())}
        rows[(row["coordinate"], row["artifact"], row["sha256"])] = row
    return sorted(rows.values(), key=lambda row: (row["coordinate"], row["artifact"], row["sha256"]))


def embedded_notices(data: bytes, prefix: str = "") -> dict[str, bytes]:
    result = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in sorted(archive.namelist()):
            if name.endswith("/"):
                continue
            if LEGAL_NAME.match(name.rsplit("/", 1)[-1]) and not name.endswith((".class", ".kt", ".java")):
                result[prefix + name] = archive.read(name)
            if name.endswith(".jar"):
                result.update(embedded_notices(archive.read(name), prefix + name + "!/"))
    return result


def source_headers(data: bytes) -> bytes:
    headers: dict[str, list[str]] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name in sorted(archive.namelist()):
            if not name.endswith((".kt", ".java", ".cpp", ".h", ".c")):
                continue
            text = archive.read(name).decode("utf-8")
            for comment in re.findall(r"/\*.*?\*/|(?://[^\n]*\n)+", text, re.S):
                if LEGAL_TEXT.search(comment):
                    headers.setdefault(comment, []).append(name)
    return "\n\n".join(
        "Source files:\n" + "\n".join(names) + "\n\n" + header for header, names in sorted(headers.items())
    ).encode("utf-8")


def fetch(url: str, cache: Path) -> bytes:
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / hashlib.sha256(url.encode()).hexdigest()
    if not target.exists():
        with urllib.request.urlopen(url, timeout=90) as response:
            data = response.read()
        if not data:
            raise ValueError(f"Empty upstream evidence: {url}")
        target.write_bytes(data)
    return target.read_bytes()


def refresh(inventory: Path, cache: Path) -> None:
    artifacts = artifact_rows(inventory)
    evidence: dict[str, bytes] = {}

    def save(name: str, data: bytes) -> str:
        evidence[name] = data
        return name

    def module(coordinate: str) -> dict:
        group, artifact, version = coordinate.split(":")
        repository = (
            "https://dl.google.com/dl/android/maven2/"
            if group.startswith("androidx.")
            else "https://repo.maven.apache.org/maven2/"
        )
        base = repository + group.replace(".", "/") + f"/{artifact}/{version}/{artifact}-{version}"
        pom, sources = fetch(base + ".pom", cache), fetch(base + "-sources.jar", cache)
        doc = ET.fromstring(pom)
        ns = {"p": "http://maven.apache.org/POM/4.0.0"}
        licenses = [
            {"name": node.findtext("p:name", namespaces=ns), "url": node.findtext("p:url", namespaces=ns)}
            for node in doc.findall("p:licenses/p:license", ns)
        ]
        parents = []
        for _ in range(8):
            if licenses:
                break
            parent = doc.find("p:parent", ns)
            if parent is None:
                break
            pg, pa, pv = [parent.findtext(f"p:{key}", namespaces=ns) for key in ("groupId", "artifactId", "version")]
            url = repository + pg.replace(".", "/") + f"/{pa}/{pv}/{pa}-{pv}.pom"
            parent_data = fetch(url, cache)
            parents.append(
                {"url": url, "sha256": digest(parent_data), "file": save(f"parents/{pg}_{pa}_{pv}.pom", parent_data)}
            )
            doc = ET.fromstring(parent_data)
            licenses = [
                {"name": node.findtext("p:name", namespaces=ns), "url": node.findtext("p:url", namespaces=ns)}
                for node in doc.findall("p:licenses/p:license", ns)
            ]
        if not licenses:
            raise ValueError(f"Review inherited/missing POM license: {coordinate}")
        key = coordinate.replace(":", "_")
        files = [save(f"modules/{key}/pom.xml", pom)]
        headers = source_headers(sources)
        if headers:
            files.append(save(f"modules/{key}/SOURCE-NOTICES.txt", headers))
        for name, data in embedded_notices(sources).items():
            files.append(save(f"modules/{key}/source-{digest(name.encode())[:16]}.txt", data))
        return {
            "coordinate": coordinate,
            "licenses": licenses,
            "evidence": sorted(files),
            "parent_poms": parents,
            "pom": {"url": base + ".pom", "sha256": digest(pom)},
            "sources": {"url": base + "-sources.jar", "sha256": digest(sources)},
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        modules = list(pool.map(module, sorted({row["coordinate"] for row in artifacts})))
    supplements = json.loads((EVIDENCE / "supplements.json").read_text(encoding="utf-8"))
    for item in supplements:
        data = fetch(item["url"], cache)
        if item.get("encoding") == "base64":
            data = base64.b64decode(data)
        if digest(data) != item["sha256"]:
            raise ValueError(f"Upstream evidence hash changed: {item['url']}")
        save(item["file"], data)
    manifest = {
        "schema": 1,
        "configuration": "releaseRuntimeClasspath",
        "artifacts": artifacts,
        "modules": modules,
        "supplements": supplements,
        "files": {name: digest(data) for name, data in sorted(evidence.items())},
    }
    for name, data in evidence.items():
        target = EVIDENCE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (EVIDENCE / "manifest.json").write_bytes(json_bytes(manifest))
    print(f"Collected {len(modules)} modules and {len(evidence)} evidence files; review before committing.")


def public_suffix_source(data: bytes) -> bytes:
    """Recover the complete rule data used by OkHttp, including exception markers."""
    raw = io.BytesIO(gzip.decompress(data))
    sections = []
    for _ in range(2):
        size = struct.unpack(">I", raw.read(4))[0]
        section = raw.read(size)
        if len(section) != size:
            raise ValueError("Truncated OkHttp public suffix data")
        sections.append(section)
    if raw.read():
        raise ValueError("Unexpected OkHttp public suffix format")
    return (
        b"// Public Suffix List rule data distributed by OkHttp 4.12.0.\n"
        b"// Mozilla Public License 2.0; see upstream/MPL-2.0.txt and embedded NOTICE.\n"
        b"// Losslessly decoded rules; comments absent in upstream compressed data.\n"
        + sections[0]
        + b"".join(b"!" + line + b"\n" for line in sections[1].splitlines())
    )


def generate(inventory: Path, output: Path, zip_path: Path) -> None:
    manifest = json.loads((EVIDENCE / "manifest.json").read_text(encoding="utf-8"))
    actual = artifact_rows(inventory)
    if actual != manifest["artifacts"]:
        raise ValueError("Runtime dependencies differ from reviewed notices. Run refresh and review the evidence diff.")
    files = {"Sayrift-LICENSE.txt": (ANDROID.parent / "LICENSE").read_bytes()}
    for name, sha in manifest["files"].items():
        data = (EVIDENCE / name).read_bytes()
        if digest(data) != sha:
            raise ValueError(f"Reviewed evidence changed: {name}")
        files[name] = data
    embedded = []
    native = []
    for row in json.loads(inventory.read_text(encoding="utf-8-sig")):
        if row["coordinate"] not in {a["coordinate"] for a in actual}:
            continue
        archive_data = Path(row["file"]).read_bytes()
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            for name in sorted(archive.namelist()):
                if name.endswith(".so"):
                    entry = {"coordinate": row["coordinate"], "entry": name, "sha256": digest(archive.read(name))}
                    if entry not in native:
                        native.append(entry)
        for name, data in embedded_notices(archive_data).items():
            path = f"embedded/{row['coordinate'].replace(':', '_')}/{digest(name.encode())[:16]}.txt"
            files[path] = data
            entry = {"coordinate": row["coordinate"], "entry": name, "file": path, "sha256": digest(data)}
            if entry not in embedded:
                embedded.append(entry)
        if row["coordinate"] == "com.squareup.okhttp3:okhttp:4.12.0":
            with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
                files["upstream/public_suffix_list.dat"] = public_suffix_source(
                    archive.read("okhttp3/internal/publicsuffix/publicsuffixes.gz")
                )
    public = {**manifest, "embedded": sorted(embedded, key=lambda item: (item["coordinate"], item["entry"]))}
    public["native_libraries"] = sorted(native, key=lambda item: (item["coordinate"], item["entry"]))
    public["files"] = {name: digest(data) for name, data in sorted(files.items())}
    files["inventory.json"] = json_bytes(public)
    files["README.txt"] = (EVIDENCE / "README.txt").read_bytes()
    lines = [files["README.txt"].decode("utf-8"), "\nRESOLVED RUNTIME ARTIFACTS\n"]
    lines.extend(f"{row['coordinate']}  {row['artifact']}  SHA-256 {row['sha256']}" for row in actual)
    for name, data in sorted(files.items()):
        if name.lower().endswith((".txt", ".md")) and name != "README.txt":
            lines.extend([f"\n\n===== {name} =====\n", data.decode("utf-8")])
    files["THIRD_PARTY_NOTICES.txt"] = "\n".join(lines).encode("utf-8")
    # Remove stale output only inside this task's dedicated generated directory.
    target = output.resolve() / "third_party"
    if not target.is_relative_to((ANDROID / "app/build").resolve()):
        raise ValueError("Generated assets must remain under android/app/build")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name, data in sorted(files.items()):
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo("third_party/" + name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compresslevel=9)
    print(f"Verified {len(actual)} artifacts; generated {len(files)} public files and reproducible notice ZIP.")


def verify_apk(apk: Path, notices_zip: Path) -> None:
    with zipfile.ZipFile(notices_zip) as expected, zipfile.ZipFile(apk) as actual:
        names = {"assets/" + name for name in expected.namelist()}
        packaged = {
            name for name in actual.namelist() if name.startswith("assets/third_party/") and not name.endswith("/")
        }
        if names != packaged:
            raise ValueError("APK third_party asset list does not match the notice ZIP")
        for name in expected.namelist():
            if expected.read(name) != actual.read("assets/" + name):
                raise ValueError(f"APK notice bytes differ: {name}")
    print(f"Verified {len(names)} APK notice assets against the companion ZIP.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("generate", "refresh", "verify-apk"))
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--zip", type=Path)
    parser.add_argument("--apk", type=Path)
    parser.add_argument("--cache", type=Path, default=ANDROID / "build/notices-downloads")
    args = parser.parse_args()
    if args.command == "verify-apk":
        if args.apk is None or args.zip is None:
            parser.error("verify-apk requires --apk and --zip")
        verify_apk(args.apk, args.zip)
        return
    if args.inventory is None:
        parser.error("generate/refresh requires --inventory")
    if args.command == "refresh":
        refresh(args.inventory, args.cache)
    else:
        if args.output is None or args.zip is None:
            parser.error("generate requires --output and --zip")
        generate(args.inventory, args.output, args.zip)


if __name__ == "__main__":
    main()
