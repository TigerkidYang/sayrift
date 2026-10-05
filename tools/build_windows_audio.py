"""Build pinned x64 libsndfile with static Ogg/Opus and the Windows dynamic UCRT."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
OUTPUT = ROOT / "dist/windows-audio"
TOOLCHAIN = "llvm-mingw-20260922-ucrt-x86_64"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def patch_source(source: Path) -> str:
    patches = json.loads((TOOLS / "libsndfile-opus-only.json").read_text())
    diff = []
    for name, edits in patches.items():
        path = source / name
        original = text = path.read_text(encoding="utf-8")
        for edit in edits:
            if text.count(edit["old"]) != edit["count"]:
                raise ValueError(f"Unexpected source while patching {name}")
            text = text.replace(edit["old"], edit["new"])
        path.write_text(text, encoding="utf-8", newline="\n")
        diff.extend(difflib.unified_diff(original.splitlines(True), text.splitlines(True), f"a/{name}", f"b/{name}"))
    return "".join(diff)


def main() -> None:
    recipe_hash = digest(Path(__file__))
    patch_hash = digest(TOOLS / "libsndfile-opus-only.json")
    for package, expected in {"cmake": "3.31.6", "ninja": "1.11.1.4"}.items():
        if version(package) != expected:
            raise RuntimeError(f"Install build tools: uv pip install cmake==3.31.6 ninja==1.11.1.4 ({package})")
    build = ROOT / "build/windows-audio"
    # This dedicated tree contains only generated files. Never reuse another worktree's build cache.
    if build.exists():
        if build.resolve().parent != (ROOT / "build").resolve() or build.is_symlink() or build.is_junction():
            raise ValueError("Unsafe audio build directory")
        shutil.rmtree(build)
    build.mkdir(parents=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((TOOLS / "windows-audio-sources.json").read_text())
    sources = ROOT / "dist/sources"
    sources.mkdir(parents=True, exist_ok=True)
    toolchains = ROOT / "build/toolchains"
    for entry in manifest:
        archive = sources / entry["file"]
        if not archive.is_file() or digest(archive) != entry["sha256"]:
            temporary = archive.with_suffix(archive.suffix + ".part")
            with urllib.request.urlopen(entry["url"], timeout=120) as response, temporary.open("wb") as stream:
                shutil.copyfileobj(response, stream)
            if digest(temporary) != entry["sha256"]:
                raise ValueError(f"Source checksum mismatch: {archive.name}")
            temporary.replace(archive)
        if archive.suffix == ".zip":
            # Extract verified compiler bytes on each run, so changed cache files cannot affect the build.
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(toolchains)
        else:
            with tarfile.open(archive) as bundle:
                bundle.extractall(build / "src", filter="data")
    diff = patch_source(build / "src/libsndfile-1.2.2")
    (OUTPUT / "libsndfile-opus-only.patch").write_text(diff, encoding="utf-8", newline="\n")
    compiler = toolchains / TOOLCHAIN / "bin"
    cmake = Path(sys.prefix) / "Lib/site-packages/cmake/data/bin/cmake.exe"
    ninja = Path(sys.prefix) / "Scripts/ninja.exe"
    prefix = build / "prefix"
    env = os.environ.copy()
    env["PATH"] = str(compiler) + os.pathsep + str(ninja.parent) + os.pathsep + env["PATH"]
    commands = []

    def run(*args: str) -> None:
        command = [str(cmake), *args]
        commands.append(command)
        subprocess.run(command, check=True, env=env)

    common = [
        "-G",
        "Ninja",
        f"-DCMAKE_MAKE_PROGRAM={ninja.as_posix()}",
        f"-DCMAKE_C_COMPILER={(compiler / 'x86_64-w64-mingw32-clang.exe').as_posix()}",
        f"-DCMAKE_CXX_COMPILER={(compiler / 'x86_64-w64-mingw32-clang++.exe').as_posix()}",
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_INSTALL_PREFIX={prefix.as_posix()}",
        "-DBUILD_TESTING=OFF",
        "-DCMAKE_C_FLAGS=-ffile-prefix-map=" + build.as_posix() + "=.",
        "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,--no-insert-timestamp",
    ]
    for name, directory, options in [
        ("ogg", "ogg-1.3.5", ["-DBUILD_SHARED_LIBS=OFF"]),
        ("opus", "opus-1.5.2", ["-DBUILD_SHARED_LIBS=OFF", "-DOPUS_BUILD_PROGRAMS=OFF", "-DOPUS_BUILD_TESTING=OFF"]),
        (
            "sndfile",
            "libsndfile-1.2.2",
            [
                "-DBUILD_SHARED_LIBS=ON",
                "-DENABLE_EXTERNAL_LIBS=ON",
                "-DENABLE_MPEG=OFF",
                "-DENABLE_EXPERIMENTAL=OFF",
                "-DBUILD_PROGRAMS=OFF",
                "-DBUILD_EXAMPLES=OFF",
                "-DENABLE_CPACK=OFF",
                "-DCMAKE_DISABLE_FIND_PACKAGE_Vorbis=TRUE",
                "-DCMAKE_DISABLE_FIND_PACKAGE_FLAC=TRUE",
                "-DCMAKE_DISABLE_FIND_PACKAGE_mp3lame=TRUE",
                "-DCMAKE_DISABLE_FIND_PACKAGE_mpg123=TRUE",
                "-DCMAKE_DISABLE_FIND_PACKAGE_Speex=TRUE",
                "-DENABLE_STATIC_RUNTIME=OFF",
                f"-DCMAKE_PREFIX_PATH={prefix.as_posix()}",
            ],
        ),
    ]:
        target = build / name
        run("-S", str(build / "src" / directory), "-B", str(target), *common, *options)
        run("--build", str(target), "--parallel", "4")
        run("--install", str(target))
    dll = OUTPUT / "libsndfile_x64.dll"
    shutil.copy2(prefix / "bin/libsndfile.dll", dll)
    shutil.copy2(toolchains / TOOLCHAIN / "LICENSE.TXT", OUTPUT / "llvm-mingw-LICENSE.txt")
    report = {
        "dll_sha256": digest(dll),
        "dll_bytes": dll.stat().st_size,
        "sources": manifest,
        "recipe_sha256": recipe_hash,
        "patch_sha256": patch_hash,
        "cmake": version("cmake"),
        "ninja": version("ninja"),
        "cmake_exe_sha256": digest(cmake),
        "ninja_exe_sha256": digest(ninja),
        "commands": [
            [arg.replace(str(ROOT), "<checkout>").replace(ROOT.as_posix(), "<checkout>") for arg in command]
            for command in commands
        ],
    }
    if recipe_hash != digest(Path(__file__)) or patch_hash != digest(TOOLS / "libsndfile-opus-only.json"):
        raise RuntimeError("Audio recipe changed during compilation; rerun the build")
    (OUTPUT / "build-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    kit = ROOT / "dist/sayrift-windows-audio-source.zip"
    with zipfile.ZipFile(kit, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in manifest:
            if entry["file"].endswith(".zip"):
                continue  # Compiler is an upstream build tool, fetched by verified URL when rebuilding.
            archive.write(sources / entry["file"], "dist/sources/" + entry["file"])
        for name in ("build_windows_audio.py", "windows-audio-sources.json", "libsndfile-opus-only.json"):
            archive.write(TOOLS / name, "tools/" + name)
        archive.write(ROOT / "docs/windows-audio-build.md", "docs/windows-audio-build.md")
        for name in (
            "libsndfile-1.2.2-notices.txt",
            "libsndfile-embedded-notices.txt",
            "ogg-v1.3.5-notices.txt",
            "opus-v1.5.2-notices.txt",
            "llvm-mingw-LICENSE.txt",
            "mingw-w64-runtime-COPYING.txt",
        ):
            archive.write(ROOT / "licenses/windows" / name, "licenses/windows/" + name)
        for path in OUTPUT.iterdir():
            if path.is_file():
                archive.write(path, "dist/windows-audio/" + path.name)
    print(f"Built {dll}: {report['dll_sha256']}")


if __name__ == "__main__":
    main()
