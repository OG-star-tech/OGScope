"""配置目录与 Settings 集成测试 / Config catalog and Settings integration tests."""

from __future__ import annotations

import pytest

from ogscope.config import Settings
from ogscope.config_catalog import build_config_catalog


@pytest.mark.unit
def test_build_config_catalog_includes_new_preview_fields() -> None:
    catalog = build_config_catalog()
    keys = {
        entry["key"] for section in catalog["sections"] for entry in section["entries"]
    }
    assert "OGSCOPE_SHARED_PREVIEW_FPS" in keys
    assert "OGSCOPE_PREVIEW_JPEG_QUALITY" in keys
    assert "OGSCOPE_PREVIEW_ENCODER" in keys
    assert "OGSCOPE_CAMERA_TUNING_FILE" in keys
    assert "OGSCOPE_CAMERA_AUTO_EXPOSURE_MAX_US" in keys
    assert "OGSCOPE_CAMERA_NOISE_REDUCTION_MODE" in keys
    assert "OGSCOPE_SIMULATION_MODE" in keys
    assert "OGSCOPE_DEV_CAPTURES_DIR" in keys


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None),
        ("", None),
        ("auto", None),
        ("1", True),
        ("0", False),
        ("true", True),
        ("false", False),
    ],
)
def test_simulation_mode_tri_state(raw: str | None, expected: bool | None) -> None:
    settings = Settings(simulation_mode=raw)  # type: ignore[arg-type]
    assert settings.simulation_mode is expected


@pytest.mark.unit
def test_legacy_auto_exposure_ceiling_is_capped_at_one_second() -> None:
    """旧环境值不阻止启动且会收敛到 1 秒 / Legacy values boot and clamp to 1s."""
    settings = Settings(camera_auto_exposure_max_us=2_000_000)

    assert settings.camera_auto_exposure_max_us == 1_000_000
