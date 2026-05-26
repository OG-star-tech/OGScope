"""配置 env 文件读写辅助测试 / Tests for config env file helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from ogscope.web.api.system import config_files as mod


@pytest.mark.unit
def test_read_config_file_payload_marks_sudo_writable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_path = tmp_path / "ogscope.env"
    env_path.write_text("OGSCOPE_PORT=8000\n", encoding="utf-8")
    monkeypatch.setattr(mod, "CONFIG_WRITE_SCRIPT", tmp_path / "write.sh")
    monkeypatch.setattr(mod, "CONFIG_SUDOERS", tmp_path / "sudoers")
    mod.CONFIG_WRITE_SCRIPT.write_text("#!/bin/sh\n", encoding="utf-8")
    mod.CONFIG_SUDOERS.write_text("ogscope ALL=(ALL) NOPASSWD: /usr/local/bin/ogscope-config-write\n")

    payload = mod.read_config_file_payload(env_path)

    assert payload["exists"] is True
    assert payload["writable_via_sudo"] is True
    assert payload["writable"] is True


@pytest.mark.unit
def test_read_config_file_payload_not_writable_without_sudoers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    env_path = tmp_path / "ogscope.env"
    env_path.write_text("OGSCOPE_PORT=8000\n", encoding="utf-8")
    monkeypatch.setattr(mod, "CONFIG_WRITE_SCRIPT", tmp_path / "missing-write.sh")
    monkeypatch.setattr(mod, "CONFIG_SUDOERS", tmp_path / "missing-sudoers")
    monkeypatch.setattr(mod.os, "access", lambda _path, _mode: False)

    payload = mod.read_config_file_payload(env_path)

    assert payload["writable_via_sudo"] is False
    assert payload["writable"] is False
