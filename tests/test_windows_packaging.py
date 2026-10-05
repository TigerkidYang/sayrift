"""The extractable installer must not overwrite user folders or escape its destination."""

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "windows_setup_launcher", Path(__file__).resolve().parents[1] / "tools/windows_setup_launcher.py"
)
launcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(launcher)


def test_extract_preserves_replaceable_libraries(tmp_path):
    archive = tmp_path / "setup.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("SayriftSetup.exe", b"executable")
        bundle.writestr("_internal/PySide6/Qt6Core.dll", b"library")
        bundle.writestr("licenses/LIBRARY-REPLACEMENT.md", "instructions")
    target = tmp_path / "setup"
    launcher.extract(archive, target)
    library = target / "_internal/PySide6/Qt6Core.dll"
    library.write_bytes(b"replacement")
    assert library.read_bytes() == b"replacement"


def test_extract_refuses_existing_destination(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    with pytest.raises(FileExistsError):
        launcher.extract(tmp_path / "unused.zip", target)


@pytest.mark.parametrize("member", ["../escape.txt", "_internal/../../escape.txt"])
def test_extract_rejects_path_traversal(tmp_path, member):
    archive = tmp_path / "setup.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr(member, "unsafe")
    with pytest.raises(ValueError, match="Unsafe"):
        launcher.extract(archive, tmp_path / "setup")
    assert not (tmp_path / "escape.txt").exists()


@pytest.fixture
def audio_artifact(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "windows_audio_artifact", Path(__file__).resolve().parents[1] / "tools/windows_audio_artifact.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("build_windows_audio.py", "libsndfile-opus-only.json", "windows-audio-sources.json"):
        (tools / name).write_text("[]", encoding="utf-8")
    directory = tmp_path / "audio"
    directory.mkdir()
    dll = directory / "libsndfile_x64.dll"
    dll.write_bytes(b"rebuilt DLL")
    report = {
        "dll_sha256": hashlib.sha256(dll.read_bytes()).hexdigest(),
        "recipe_sha256": module.digest(tools / "build_windows_audio.py"),
        "patch_sha256": module.digest(tools / "libsndfile-opus-only.json"),
        "sources": [],
    }
    (directory / "build-report.json").write_text(json.dumps(report), encoding="utf-8")
    return module, directory


def test_verified_audio_requires_report(audio_artifact):
    module, directory = audio_artifact
    assert module.verified_audio(directory).is_file()
    (directory / "build-report.json").unlink()
    with pytest.raises(ValueError, match="Build the pinned DLL"):
        module.verified_audio(directory)


def test_verified_audio_rejects_tampering(audio_artifact):
    module, directory = audio_artifact
    (directory / "libsndfile_x64.dll").write_bytes(b"wheel DLL")
    with pytest.raises(ValueError, match="checksum"):
        module.verified_audio(directory)


def test_verified_audio_rejects_stale_recipe(audio_artifact):
    module, directory = audio_artifact
    (module.ROOT / "tools/build_windows_audio.py").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="recipe changed"):
        module.verified_audio(directory)
