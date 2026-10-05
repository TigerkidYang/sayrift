"""The extractable installer must not overwrite user folders or escape its destination."""

import importlib.util
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
