"""Web 配置 env 文件读写辅助 / Helpers for Web-managed env config files."""

from __future__ import annotations

import grp
import os
import subprocess
from pathlib import Path

CONFIG_WRITE_SCRIPT = Path("/usr/local/bin/ogscope-config-write")
CONFIG_SUDOERS = Path("/etc/sudoers.d/ogscope-config")
CONFIG_FILE_MODE = "640"


def config_file_group(path: Path) -> str:
    """读取目标文件属组，供 chown 使用 / Group name for chown on target file."""
    if path.exists():
        try:
            return grp.getgrgid(path.stat().st_gid).gr_name
        except KeyError:
            pass
    return os.environ.get("USER", "ogscope")


def config_write_access() -> dict[str, bool]:
    """评估 sudo 写入能力 / Assess sudo-backed config write access."""
    via_sudo = CONFIG_WRITE_SCRIPT.is_file() and CONFIG_SUDOERS.is_file()
    return {
        "writable_via_sudo": via_sudo,
    }


def read_config_file_payload(path: Path) -> dict:
    """读取配置文件内容与写入能力 / Read config file and write capability flags."""
    exists = path.exists()
    access = config_write_access()
    if not exists:
        parent_writable = os.access(path.parent, os.W_OK)
        return {
            "path": str(path),
            "exists": False,
            "writable": parent_writable or access["writable_via_sudo"],
            **access,
            "content": "",
            "error": "file not found",
        }
    try:
        content = path.read_text(encoding="utf-8")
        direct = os.access(path, os.W_OK)
        writable = direct or access["writable_via_sudo"]
        return {
            "path": str(path),
            "exists": True,
            "writable": writable,
            "writable_direct": direct,
            "writable_via_sudo": access["writable_via_sudo"],
            "content": content,
            "error": None,
        }
    except OSError as exc:
        return {
            "path": str(path),
            "exists": True,
            "writable": access["writable_via_sudo"],
            **access,
            "content": "",
            "error": str(exc),
        }


def write_config_file(path: Path, content: str) -> None:
    """写入 env 配置文件（必要时 sudo）/ Write env config, using sudo helper when needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(content, encoding="utf-8")
        return
    except OSError:
        pass

    if not CONFIG_WRITE_SCRIPT.is_file():
        raise RuntimeError(
            "failed to write config file; install ogscope-config-write via install.sh "
            "or ogscope-network-init.sh ensure-config"
        )

    group = config_file_group(path)
    proc = subprocess.run(
        [
            "sudo",
            "-n",
            str(CONFIG_WRITE_SCRIPT),
            str(path),
            CONFIG_FILE_MODE,
            group,
        ],
        input=content,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(
            "failed to write config file via sudo; run "
            "sudo ./scripts/ogscope-network-init.sh ensure-config "
            f"({detail})"
        )
