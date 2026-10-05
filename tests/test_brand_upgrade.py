"""Upgrade continuity without touching real registry entries, shortcuts or user data."""

import importlib.util
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from local_typeless import config
from local_typeless.ui import uninstall
from local_typeless.win import install, shortcut


def test_renamed_app_reuses_old_config_and_accepts_both_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delenv("SAYRIFT_CONFIG", raising=False)
    monkeypatch.delenv("LOCAL_TYPELESS_CONFIG", raising=False)
    old = tmp_path / "local-typeless" / "config.toml"
    old.parent.mkdir()
    old.write_text('dictionary = ["Existing term"]', encoding="utf-8")
    assert config.load().dictionary == ["Existing term"]
    assert config.config_dir() == old.parent
    legacy_override = tmp_path / "legacy.toml"
    monkeypatch.setenv("LOCAL_TYPELESS_CONFIG", str(legacy_override))
    assert config.config_path() == legacy_override
    renamed_override = tmp_path / "sayrift.toml"
    monkeypatch.setenv("SAYRIFT_CONFIG", str(renamed_override))
    assert config.config_path() == renamed_override


@pytest.mark.parametrize("folder,exe", [("local-typeless", "local-typeless.exe"), ("Sayrift", "sayrift.exe")])
def test_setup_replaces_legacy_payload_without_deleting_unrelated_files(tmp_path, monkeypatch, folder, exe):
    spec = importlib.util.spec_from_file_location(
        "sayrift_setup_test", Path(__file__).parents[1] / "packaging" / "setup_main.py"
    )
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    target = tmp_path / folder
    (target / "_internal").mkdir(parents=True)
    (target / exe).write_bytes(b"old")
    (target / "_internal" / "old.dll").write_bytes(b"old")
    (target / "my-notes.txt").write_text("keep me")
    payload = tmp_path / "payload.zip"
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("sayrift.exe", b"new")
        archive.writestr("_internal/new.dll", b"new")
    monkeypatch.setattr(setup, "payload", lambda: payload)
    monkeypatch.setattr(setup, "quit_running", lambda: True)
    registered = []
    monkeypatch.setattr(install, "register", lambda *args, **kwargs: registered.append(args))
    worker = setup.Worker(target, True, setup._EN)
    errors = []
    worker.finished.connect(errors.append)
    worker.run()
    assert errors == [""]
    assert registered[0][0] == target
    assert (target / "sayrift.exe").read_bytes() == b"new"
    assert not (target / "local-typeless.exe").exists()
    assert not (target / "_internal" / "old.dll").exists()
    assert (target / "my-notes.txt").read_text() == "keep me"


def test_shortcut_cleanup_is_scoped_to_the_old_app_name(tmp_path, monkeypatch):
    monkeypatch.setattr(shortcut, "_folder", lambda csidl: tmp_path / str(csidl))
    for p in shortcut.locations("local-typeless") + shortcut.locations("Sayrift"):
        p.parent.mkdir(exist_ok=True)
        p.touch()
    shortcut.remove_legacy()
    assert not any(p.exists() for p in shortcut.locations("local-typeless"))
    assert all(p.exists() for p in shortcut.locations("Sayrift"))


def test_uninstall_remembers_custom_location_before_unregister(tmp_path, monkeypatch):
    target = tmp_path / "custom" / "local-typeless"
    registry = {"location": target}
    removed = []
    monkeypatch.setattr(uninstall, "QApplication", SimpleNamespace(instance=lambda: object()))
    monkeypatch.setattr(uninstall, "quit_running", lambda: True)
    monkeypatch.setattr(install, "installed_dir", lambda: registry.get("location"))
    monkeypatch.setattr(install, "unregister", registry.clear)
    monkeypatch.setattr(install, "remove_dir_after_exit", removed.append)
    monkeypatch.setattr(uninstall.sys, "frozen", True, raising=False)
    monkeypatch.setattr(uninstall.sys, "executable", str(target / "sayrift.exe"))
    assert uninstall.run(quiet=True) == 0
    assert removed == [target]


def test_cleanup_rejects_parent_directories_and_another_install(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        install.validate_install_dir(tmp_path)
    monkeypatch.setattr(install.sys, "executable", str(tmp_path / "Sayrift" / "sayrift.exe"))
    with pytest.raises(ValueError):
        install.remove_dir_after_exit(tmp_path / "other" / "Sayrift")


def test_incomplete_archive_does_not_touch_the_old_install(tmp_path):
    target = tmp_path / "Sayrift"
    target.mkdir()
    old = target / "sayrift.exe"
    old.write_bytes(b"working app")
    payload = tmp_path / "bad.zip"
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("sayrift.exe", b"incomplete")
    with pytest.raises(ValueError, match="incomplete"):
        install.replace_payload(target, payload, lambda _: None)
    assert old.read_bytes() == b"working app"


def test_failed_payload_move_restores_the_previous_install(tmp_path, monkeypatch):
    target = tmp_path / "local-typeless"
    (target / "_internal").mkdir(parents=True)
    (target / "local-typeless.exe").write_bytes(b"working app")
    (target / "_internal" / "old.dll").write_bytes(b"old")
    payload = tmp_path / "new.zip"
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("sayrift.exe", b"new")
        archive.writestr("_internal/new.dll", b"new")
    original = Path.replace

    def fail_new_payload(source, destination):
        if source.name == "_internal" and source.parent.name == "new":
            raise PermissionError("simulated sharing violation")
        return original(source, destination)

    monkeypatch.setattr(Path, "replace", fail_new_payload)
    with pytest.raises(PermissionError):
        install.replace_payload(target, payload, lambda _: None)
    assert (target / "local-typeless.exe").read_bytes() == b"working app"
    assert (target / "_internal" / "old.dll").read_bytes() == b"old"
    assert not (target / "sayrift.exe").exists()


def test_failed_rollback_preserves_the_previous_files_for_recovery(tmp_path, monkeypatch):
    target = tmp_path / "Sayrift"
    target.mkdir()
    (target / "sayrift.exe").write_bytes(b"working app")
    payload = tmp_path / "new.zip"
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("sayrift.exe", b"new")
        archive.writestr("_internal/new.dll", b"new")
    original = Path.replace

    def fail_new_payload_and_rollback(source, destination):
        if (source.name == "_internal" or source.parent == target) and (
            source.parent.name == "new" or Path(destination).parent.name == "new"
        ):
            raise PermissionError("simulated lock during replacement and rollback")
        return original(source, destination)

    monkeypatch.setattr(Path, "replace", fail_new_payload_and_rollback)
    with pytest.raises(RuntimeError, match="preserved"):
        install.replace_payload(target, payload, lambda _: None)
    backups = list(tmp_path.glob(".sayrift-setup-*/previous/sayrift.exe"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"working app"


def test_archive_path_escape_is_rejected_before_replacement(tmp_path):
    target = tmp_path / "Sayrift"
    target.mkdir()
    (target / "sayrift.exe").write_bytes(b"working app")
    payload = tmp_path / "bad.zip"
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("../../outside.txt", b"untrusted")
    with pytest.raises(ValueError):
        install.replace_payload(target, payload, lambda _: None)
    assert (target / "sayrift.exe").read_bytes() == b"working app"
    assert not (tmp_path / "outside.txt").exists()
