"""相机传感器识别单元测试 / Camera sensor detection unit tests."""

from __future__ import annotations

import subprocess

import pytest

from ogscope.platform.hardware import camera_sensors
from ogscope.platform.hardware.camera_sensors import (
    IMX327_PROFILE,
    SC230AI_PROFILE,
    detect_sensor,
    parse_sensor_entities,
    profile_for_entity,
)
from ogscope.platform.hardware.v4l2_camera import V4L2RawCamera

# 接 IMX327 时 media-ctl -p 的输出 / media-ctl -p with an IMX327
IMX327_GRAPH = """\
Media controller API version 6.12.0

Device topology
- entity 1: unicam (3 pads, 3 links, 0 routes)
            type V4L2 subdev subtype Unknown flags 0
            device node name /dev/v4l-subdev0
\tpad0: SINK
\t\t[stream:0 fmt:SRGGB12_1X12/1280x720 field:none colorspace:raw]
\t\t<- "imx327 10-001a":0 [ENABLED,IMMUTABLE]
\tpad1: SOURCE
\t\t-> "unicam-image":0 [ENABLED,IMMUTABLE]

- entity 5: imx327 10-001a (1 pad, 1 link, 0 routes)
            type V4L2 subdev subtype Sensor flags 0
            device node name /dev/v4l-subdev1
\tpad0: SOURCE
\t\t[stream:0 fmt:SRGGB12_1X12/1280x720 field:none colorspace:raw
\t\t crop.bounds:(0,0)/1945x1097
\t\t crop:(332,188)/1280x720]
\t\t-> "unicam":0 [ENABLED,IMMUTABLE]

- entity 9: unicam-image (1 pad, 1 link)
            type Node subtype V4L flags 1
            device node name /dev/video0
\tpad0: SINK
\t\t<- "unicam":1 [ENABLED,IMMUTABLE]
"""

# 换接 SC230AI 时的同一媒体图 / The same media graph with an SC230AI
SC230AI_GRAPH = (
    IMX327_GRAPH.replace("imx327 10-001a", "sc230ai 10-0030")
    .replace("SRGGB12_1X12/1280x720", "SBGGR10_1X10/1920x1080")
    .replace("/dev/v4l-subdev1", "/dev/v4l-subdev2")
)


# 一个 ISP 的媒体图：没有传感器 / An ISP's media graph: no sensor
ISP_GRAPH = """\
Device topology
- entity 1: bcm2835_isp0-output0 (1 pad, 1 link)
            type Node subtype V4L flags 0
            device node name /dev/video13
"""


@pytest.fixture(autouse=True)
def _no_other_media_devices(monkeypatch):
    """测试中不扫描本机的媒体设备 / Do not scan this machine's media devices."""
    monkeypatch.setattr(camera_sensors, "media_devices", lambda: [])


def _media_ctl(stdout: str, returncode: int = 0):
    calls: list[list[str]] = []

    def _run(command: list[str], **_kwargs) -> subprocess.CompletedProcess:
        calls.append(command)
        return subprocess.CompletedProcess(command, returncode, stdout, "")

    return _run, calls


@pytest.mark.unit
def test_only_sensor_entities_are_read_from_the_graph() -> None:
    assert parse_sensor_entities(IMX327_GRAPH) == [
        ("imx327 10-001a", "/dev/v4l-subdev1")
    ]
    assert parse_sensor_entities(SC230AI_GRAPH) == [
        ("sc230ai 10-0030", "/dev/v4l-subdev2")
    ]
    assert parse_sensor_entities("") == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "entity, profile",
    [
        ("imx327 10-001a", IMX327_PROFILE),
        ("imx290 10-001a", IMX327_PROFILE),
        ("sc230ai 10-0030", SC230AI_PROFILE),
        ("ov5647 10-0036", None),
    ],
)
def test_the_driver_name_picks_the_profile(entity, profile) -> None:
    assert profile_for_entity(entity) is profile


@pytest.mark.unit
def test_detection_reads_the_configured_media_device() -> None:
    run, calls = _media_ctl(SC230AI_GRAPH)
    found = detect_sensor("/dev/media3", run=run)
    assert calls == [["media-ctl", "-d", "/dev/media3", "-p"]]
    assert found is not None and found.profile is SC230AI_PROFILE
    assert found.entity == "sc230ai 10-0030" and found.subdev == "/dev/v4l-subdev2"
    assert found.media_device == "/dev/media3"


def _graphs(by_device: dict[str, str]):
    calls: list[str] = []

    def _run(command: list[str], **_kwargs) -> subprocess.CompletedProcess:
        device = command[2]
        calls.append(device)
        return subprocess.CompletedProcess(command, 0, by_device.get(device, ""), "")

    return _run, calls


@pytest.mark.unit
def test_the_sensor_is_found_on_whichever_media_device_has_it(monkeypatch) -> None:
    # ISP 先探测并占用了 media0/media1 / The ISPs probed first and took
    # media0 and media1
    monkeypatch.setattr(
        camera_sensors,
        "media_devices",
        lambda: ["/dev/media0", "/dev/media1", "/dev/media2"],
    )
    run, calls = _graphs(
        {
            "/dev/media0": ISP_GRAPH,
            "/dev/media1": ISP_GRAPH,
            "/dev/media2": IMX327_GRAPH,
        }
    )
    found = detect_sensor("/dev/media0", run=run)
    assert found is not None and found.media_device == "/dev/media2"
    assert calls == ["/dev/media0", "/dev/media1", "/dev/media2"]


@pytest.mark.unit
def test_the_configured_media_device_is_read_first(monkeypatch) -> None:
    monkeypatch.setattr(
        camera_sensors, "media_devices", lambda: ["/dev/media0", "/dev/media2"]
    )
    run, calls = _graphs({"/dev/media0": SC230AI_GRAPH, "/dev/media2": IMX327_GRAPH})
    found = detect_sensor("/dev/media2", run=run)
    assert found.profile is IMX327_PROFILE and calls == ["/dev/media2"]


@pytest.mark.unit
def test_the_camera_follows_the_sensor_to_its_media_device(monkeypatch) -> None:
    monkeypatch.setattr(
        camera_sensors, "media_devices", lambda: ["/dev/media0", "/dev/media2"]
    )
    run, _ = _graphs({"/dev/media0": ISP_GRAPH, "/dev/media2": IMX327_GRAPH})
    monkeypatch.setattr(subprocess, "run", run)
    camera = V4L2RawCamera({"v4l2_media_device": "/dev/media0"})
    camera._detect_sensor()
    assert camera.media_device == "/dev/media2"
    assert camera.sensor_subdev == "/dev/v4l-subdev1"
    assert camera.get_camera_info()["sensor_detection"]["media_device"] == "/dev/media2"


@pytest.mark.unit
@pytest.mark.parametrize(
    "graph, code", [("", 0), (IMX327_GRAPH.replace("imx327", "ov5647"), 0), ("", 1)]
)
def test_no_known_sensor_detects_nothing(graph, code) -> None:
    run, _ = _media_ctl(graph, code)
    assert detect_sensor("/dev/media0", run=run) is None


@pytest.mark.unit
def test_the_camera_adopts_the_sc230ai_it_finds(monkeypatch) -> None:
    run, _ = _media_ctl(SC230AI_GRAPH)
    monkeypatch.setattr(subprocess, "run", run)
    camera = V4L2RawCamera({})
    assert camera.sensor_profile is IMX327_PROFILE
    camera._detect_sensor()
    assert camera.sensor_entity == "sc230ai 10-0030"
    assert camera.sensor_subdev == "/dev/v4l-subdev2"
    assert camera.media_bus_format == "SBGGR10_1X10"
    assert camera.pixel_format == "BG10"
    assert camera.bayer_pattern == "BGGR"
    assert camera.driver_name == "v4l2-sc230ai-software-ae"
    info = camera.get_camera_info()
    assert info["sensor"] == "SC230AI"
    assert info["sensor_detection"]["state"] == "detected"
    assert info["optics"]["sensor"]["model"] == "SC230AI"


@pytest.mark.unit
def test_the_camera_keeps_the_imx327_it_finds(monkeypatch) -> None:
    run, _ = _media_ctl(IMX327_GRAPH)
    monkeypatch.setattr(subprocess, "run", run)
    camera = V4L2RawCamera({})
    camera._detect_sensor()
    assert camera.sensor_entity == "imx327 10-001a"
    assert camera.sensor_subdev == "/dev/v4l-subdev1"
    assert (camera.media_bus_format, camera.pixel_format, camera.bayer_pattern) == (
        "SRGGB10_1X10",
        "RG10",
        "RGGB",
    )
    assert camera.get_camera_info()["sensor"] == "IMX327"


@pytest.mark.unit
def test_disabled_detection_keeps_the_configured_sensor(monkeypatch) -> None:
    run, calls = _media_ctl(SC230AI_GRAPH)
    monkeypatch.setattr(subprocess, "run", run)
    camera = V4L2RawCamera(
        {
            "v4l2_sensor_auto_detect": False,
            "v4l2_sensor_entity": "imx327 10-001a",
            "v4l2_bayer_pattern": "RGGB",
        }
    )
    camera._detect_sensor()
    assert calls == []
    assert camera.sensor_entity == "imx327 10-001a" and camera.bayer_pattern == "RGGB"
    assert camera.get_camera_info()["sensor_detection"]["state"] == "disabled"


@pytest.mark.unit
def test_an_unreadable_graph_keeps_the_configured_sensor(monkeypatch) -> None:
    run, _ = _media_ctl("", 1)
    monkeypatch.setattr(subprocess, "run", run)
    camera = V4L2RawCamera({"v4l2_sensor_entity": "sc230ai 10-0030"})
    camera._detect_sensor()
    # 配置的实体名本身就能选出配置 / The configured entity alone picks the profile
    assert camera.sensor_profile is SC230AI_PROFILE
    assert camera.get_camera_info()["sensor_detection"]["state"] == "configured"


# 为 IMX327 的 12 位 720p 模式写的部署配置 / A deployment configured for
# the IMX327's 12-bit 720p mode
CONFIGURED_IMX327_720P = {
    "v4l2_sensor_entity": "imx327 10-001a",
    "v4l2_sensor_subdev": "/dev/v4l-subdev1",
    "v4l2_media_bus_format": "SRGGB12_1X12",
    "v4l2_pixel_format": "RG12",
    "v4l2_bit_depth": 12,
    "v4l2_bayer_pattern": "RGGB",
    "v4l2_active_width": 1280,
    "v4l2_active_height": 720,
}


@pytest.mark.unit
def test_the_configured_sensor_keeps_its_configured_mode(monkeypatch) -> None:
    run, _ = _media_ctl(IMX327_GRAPH)
    monkeypatch.setattr(subprocess, "run", run)
    camera = V4L2RawCamera(dict(CONFIGURED_IMX327_720P))
    camera._detect_sensor()
    assert (camera.media_bus_format, camera.pixel_format, camera.bit_depth) == (
        "SRGGB12_1X12",
        "RG12",
        12,
    )
    assert (camera.active_width, camera.active_height) == (1280, 720)
    assert camera._sensor_detection["settings"] == "configured"


@pytest.mark.unit
def test_another_sensor_gets_its_own_mode_not_the_configured_one(monkeypatch) -> None:
    run, _ = _media_ctl(SC230AI_GRAPH)
    monkeypatch.setattr(subprocess, "run", run)
    camera = V4L2RawCamera(dict(CONFIGURED_IMX327_720P))
    camera._detect_sensor()
    assert (camera.media_bus_format, camera.pixel_format, camera.bit_depth) == (
        "SBGGR10_1X10",
        "BG10",
        10,
    )
    assert camera.white_level == 1023 and camera.bayer_pattern == "BGGR"
    # 驱动唯一的 1080p 模式；输出仍居中裁成 1280x720 / The driver's only 1080p
    # mode; the output is still centre-cropped to 1280x720
    assert (camera.active_width, camera.active_height) == (1920, 1080)
    assert (camera.capture_width, camera.capture_height) == (1920, 1080)
    assert (camera.width, camera.height) == (1280, 720)
    assert camera._sensor_detection["settings"] == "sensor_profile"
