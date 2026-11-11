"""V4L2 相机传感器识别与配置 / V4L2 camera sensor detection and profiles.

OGScope 支持多种 RAW 传感器；设备上实际接的是哪一个，由媒体图中的传感器实体决定。
本模块从媒体图读出实际探测到的传感器，并给出对应的 RAW 格式、Bayer 排列与光学参数。
支持更多传感器只需在 SENSOR_PROFILES 中加一项。
OGScope supports several RAW sensors; which one a device has is decided by
the sensor entity in its media graph. This module reads which sensor actually
probed and returns its RAW format, Bayer order and optics. Supporting another
sensor takes one more entry in SENSOR_PROFILES.
"""

from __future__ import annotations

import glob
import logging
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from ogscope.camera_optics import (
    IMX327_16MM_F14_OPTICS,
    SC230AI_16MM_F14_OPTICS,
    CameraOpticsProfile,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SensorProfile:
    """一种传感器的 RAW 链路参数 / RAW pipeline parameters of one sensor."""

    model: str
    # 驱动给子设备起的名字（媒体图实体名的第一个词）/ Names the driver gives its
    # subdev (the first word of the media-graph entity name)
    entity_names: tuple[str, ...]
    media_bus_format: str
    pixel_format: str
    bit_depth: int
    bayer_pattern: str
    # 传感器模式的有效区域 / Active area of the sensor mode
    active_width: int
    active_height: int
    gain_db_per_step: float
    optics: CameraOpticsProfile


IMX327_PROFILE = SensorProfile(
    model="IMX327",
    entity_names=("imx327", "imx290", "imx462"),
    media_bus_format="SRGGB10_1X10",
    pixel_format="RG10",
    bit_depth=10,
    bayer_pattern="RGGB",
    active_width=1920,
    active_height=1080,
    gain_db_per_step=0.3,
    optics=IMX327_16MM_F14_OPTICS,
)

SC230AI_PROFILE = SensorProfile(
    model="SC230AI",
    entity_names=("sc230ai",),
    media_bus_format="SBGGR10_1X10",
    pixel_format="BG10",
    bit_depth=10,
    bayer_pattern="BGGR",
    # 驱动只有 1080p 模式；native 采样居中裁成输出尺寸，像元尺度不变
    # The driver has only a 1080p mode; native sampling centre-crops it to the
    # output size at the same pixel scale
    active_width=1920,
    active_height=1080,
    gain_db_per_step=0.3,
    optics=SC230AI_16MM_F14_OPTICS,
)

SENSOR_PROFILES: tuple[SensorProfile, ...] = (IMX327_PROFILE, SC230AI_PROFILE)


@dataclass(frozen=True, slots=True)
class DetectedSensor:
    """媒体图中探测到的传感器 / A sensor found in the media graph."""

    profile: SensorProfile
    entity: str
    subdev: str | None
    media_device: str


_ENTITY_RE = re.compile(r"^- entity \d+: (?P<name>.+?) \(\d+ pads?")
_SUBTYPE_RE = re.compile(r"type V4L2 subdev subtype (?P<subtype>\w+)")
_NODE_RE = re.compile(r"device node name (?P<node>\S+)")


def parse_sensor_entities(media_graph: str) -> list[tuple[str, str | None]]:
    """从 media-ctl -p 输出读出传感器实体及其子设备节点。

    Read the sensor entities and their subdev nodes from media-ctl -p output.
    """
    sensors: list[tuple[str, str | None]] = []
    name: str | None = None
    is_sensor = False
    node: str | None = None

    def _flush() -> None:
        if name is not None and is_sensor:
            sensors.append((name, node))

    for line in media_graph.splitlines():
        stripped = line.strip()
        entity = _ENTITY_RE.match(stripped)
        if entity:
            _flush()
            name, is_sensor, node = entity.group("name"), False, None
            continue
        subtype = _SUBTYPE_RE.search(stripped)
        if subtype:
            is_sensor = subtype.group("subtype") == "Sensor"
            continue
        found = _NODE_RE.search(stripped)
        if found and name is not None:
            node = found.group("node")
    _flush()
    return sensors


def profile_for_entity(entity: str) -> SensorProfile | None:
    """按实体名匹配传感器配置 / Match a sensor profile by entity name."""
    driver = entity.split()[0].lower() if entity.strip() else ""
    return next((p for p in SENSOR_PROFILES if driver in p.entity_names), None)


def media_devices() -> list[str]:
    """本机的媒体设备，按编号排序 / This system's media devices, by number."""

    def _number(path: str) -> int:
        digits = re.sub(r"\D", "", path)
        return int(digits) if digits else 0

    return sorted(glob.glob("/dev/media*"), key=_number)


def _read_graph(
    media_device: str, runner: Callable[..., subprocess.CompletedProcess]
) -> str | None:
    try:
        result = runner(
            ["media-ctl", "-d", media_device, "-p"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning(
            "读取媒体图 %s 失败 / Media graph %s unreadable: %s",
            media_device,
            media_device,
            exc,
        )
        return None
    if result.returncode != 0:
        logger.warning(
            "读取媒体图 %s 失败 / Media graph %s unreadable: %s",
            media_device,
            media_device,
            (result.stderr or "").strip() or f"media-ctl exit {result.returncode}",
        )
        return None
    return result.stdout or ""


def detect_sensor(
    media_device: str,
    run: Callable[..., subprocess.CompletedProcess] | None = None,
    candidates: list[str] | None = None,
) -> DetectedSensor | None:
    """读出实际探测到的已知传感器 / Return the known sensor that probed.

    先查配置的媒体设备，再查本机其他媒体设备：媒体设备编号取决于驱动探测顺序，
    其他驱动（如 ISP）可能先占用配置的编号。
    The configured media device is read first, then this system's other
    media devices: media device numbers follow the drivers' probe order, and
    another driver (an ISP, say) can take the configured number first.

    都没有已知传感器时返回 None，调用方保留配置值。
    Returns None when none has a known sensor; the caller then keeps its
    configured values.
    """
    runner = run or subprocess.run
    others = media_devices() if candidates is None else candidates
    for device in [media_device, *(d for d in others if d != media_device)]:
        graph = _read_graph(device, runner)
        if graph is None:
            continue
        for entity, node in parse_sensor_entities(graph):
            profile = profile_for_entity(entity)
            if profile is not None:
                return DetectedSensor(
                    profile=profile, entity=entity, subdev=node, media_device=device
                )
            logger.warning(
                "%s 上的未知传感器 %s / Unknown sensor %s on %s",
                device,
                entity,
                entity,
                device,
            )
    return None
