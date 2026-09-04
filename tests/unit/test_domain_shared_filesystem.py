from __future__ import annotations

from pathlib import Path

import pytest

from ogscope.config import Settings
from ogscope.domain.shared.filesystem import (
    dev_captures_storage_info,
    ensure_safe_basename,
    migrate_legacy_dev_captures,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "name",
    [
        "ok.txt",
        "VID_001.avi",
        "a-b_c.123",
    ],
)
def test_ensure_safe_basename_accepts_valid_names(name: str) -> None:
    assert ensure_safe_basename(name) == name


@pytest.mark.unit
@pytest.mark.parametrize(
    "name",
    [
        "",
        ".",
        "..",
        "../secret.txt",
        "..\\secret.txt",
        "foo/bar.txt",
        "foo\\bar.txt",
    ],
)
def test_ensure_safe_basename_rejects_invalid_names(name: str) -> None:
    with pytest.raises(ValueError):
        ensure_safe_basename(name)


@pytest.mark.unit
def test_settings_defaults_debug_captures_under_data_dir(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    settings = Settings(
        data_dir=data_dir,
        upload_dir=tmp_path / "uploads",
        dev_captures_dir=None,
        analysis_dir=tmp_path / "analysis",
        plate_solve_dir=tmp_path / "plate_solve",
    )

    assert settings.dev_captures_dir == data_dir / "dev_captures"
    assert settings.dev_captures_dir.is_dir()


@pytest.mark.unit
def test_settings_accepts_explicit_debug_capture_directory(tmp_path: Path) -> None:
    capture_dir = tmp_path / "volatile-or-external-captures"
    settings = Settings(
        data_dir=tmp_path / "data",
        upload_dir=tmp_path / "uploads",
        dev_captures_dir=capture_dir,
        analysis_dir=tmp_path / "analysis",
        plate_solve_dir=tmp_path / "plate_solve",
    )

    assert settings.dev_captures_dir == capture_dir
    assert capture_dir.is_dir()


@pytest.mark.unit
def test_storage_info_distinguishes_persistent_and_temporary(tmp_path: Path) -> None:
    persistent = dev_captures_storage_info(Path.cwd() / "data" / "dev_captures")
    temporary = dev_captures_storage_info(tmp_path / "captures")

    assert persistent["is_persistent"] is True
    assert persistent["persistence"] == "persistent"
    assert temporary["is_persistent"] is False
    assert temporary["persistence"] == "temporary"


@pytest.mark.unit
def test_migrate_legacy_captures_preserves_sources_and_existing_target(
    tmp_path: Path,
) -> None:
    legacy_tmp = tmp_path / "legacy-tmp"
    legacy_home = tmp_path / "legacy-home"
    target = tmp_path / "persistent"
    for directory in (legacy_tmp, legacy_home, target):
        directory.mkdir()
    (legacy_tmp / "IMG_1.jpg").write_bytes(b"from-tmp")
    (legacy_home / "IMG_2.jpg").write_bytes(b"from-home")
    (legacy_home / "IMG_1.jpg").write_bytes(b"home-conflict")
    (target / "IMG_1.jpg").write_bytes(b"persistent-wins")

    result = migrate_legacy_dev_captures(
        legacy_dirs=(legacy_tmp, legacy_home), target_dir=target
    )

    assert result["migrated"] == ["IMG_2.jpg"]
    assert result["skipped"] == ["IMG_1.jpg", "IMG_1.jpg"]
    assert result["errors"] == []
    assert (target / "IMG_1.jpg").read_bytes() == b"persistent-wins"
    assert (target / "IMG_2.jpg").read_bytes() == b"from-home"
    assert (legacy_tmp / "IMG_1.jpg").is_file()
    assert (legacy_home / "IMG_2.jpg").is_file()
