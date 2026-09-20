# V4L2 RAW Backend - Zero2W Board Validation (192.168.0.41)

板端验证记录：在真实 Zero2W (IP 192.168.0.41) 上验证 `feature/v4l2-camera-current`
（本分支 `feature/v4l2-camera-zero2w-validation` 基于其创建）的 V4L2 RAW 后端。
补充 [v4l2-auto-exposure.md](v4l2-auto-exposure.md) 的通用设计文档 - 本文档记录
**这一块具体板子**上发现的真实拓扑、与 CM0 验证配置的差异，以及测得的内存对比。/

Board validation log for the V4L2 RAW backend
(`feature/v4l2-camera-current`, on which this branch
`feature/v4l2-camera-zero2w-validation` is based) on a real Zero2W (IP
192.168.0.41). Complements [v4l2-auto-exposure.md](v4l2-auto-exposure.md)'s
general design doc with the actual topology discovered on **this specific
board**, how it differs from the CM0-validated example, and a measured memory
comparison.

**Status: partial validation.** Media pipeline, control readback, and RAW
capture confirmed working with a bright/indoor test scene. Real night-sky
solve accuracy, AE convergence under actual star fields, and long-run
stability are **not yet validated** - see [Still open](#still-open-before-this-becomes-the-default) below. Do not
enable this as the default backend or re-enable motors/alignment against it
until those pass, per the product's own acceptance gate.

## Discovery: this board's real topology differs from the CM0 example

`docs/development/v4l2-auto-exposure.md`'s example config was validated on a
CM0 board and explicitly warns that device nodes, entity names, and formats
are board-discovered, not portable. Confirmed true on this Zero2W:

```
media-ctl -p -d /dev/media0
```

```
- entity 1: unicam                /dev/v4l-subdev0   (sink-only: pad1 -> "unicam-image" is IMMUTABLE)
- entity 5: imx327 10-001a        /dev/v4l-subdev1   (sensor)
- entity 9: unicam-image          /dev/video0         (plain V4L node, no configurable subdev pad)
```

```
v4l2-ctl -d /dev/video0 --list-formats-ext   # RG12 (12-bit Bayer RGRG/GBGB) present, among RG10/RG14/others
v4l2-ctl -d /dev/v4l-subdev1 --list-ctrls    # exposure, analogue_gain, vertical_blanking,
                                              # horizontal_blanking, pixel_rate=148500000 all present
```

Concrete differences from the doc's CM0 config / "typical" example:

| Field | Doc's CM0-validated example | This Zero2W (discovered) |
|---|---|---|
| Sensor bit depth negotiated | 10-bit (`SRGGB10_1X10`/`RG10`) | **12-bit (`SRGGB12_1X12`/`RG12`)** |
| `v4l2_sensor_subdev` | `/dev/v4l-subdev1` (typical) or `/dev/v4l-subdev0` (doc's sink-only example) | `/dev/v4l-subdev1` |
| `v4l2_media_device` | `/dev/media0` (typical) or `/dev/media2` (doc's sink-only example) | `/dev/media0` |
| `v4l2_receiver_entity` | `unicam` (typical) or `unicam-image` (sink-only) | `unicam-image` (this board is sink-only) |
| `v4l2_receiver_sink_pad` / `_source_pad` | `0`/`1` (typical) or `-1`/`-1` (sink-only) | `-1`/`-1` |

The doc's own two example blocks (typical vs. sink-only) bracket this board's
real values, but neither matches exactly - board-specific rediscovery via
`media-ctl -p` was required, exactly as the doc warns. This board's working
config is captured in `scripts/validate_v4l2_zero2w.py`'s `CONFIG` dict.

The `V4L2RawCamera` implementation itself needed **no code changes** - bit
depth, media bus format, pixel format, and receiver pad numbers are all
already `config.get(...)`-driven (`ogscope/platform/hardware/v4l2_camera.py`
`__init__`), and `white_level = (1 << bit_depth) - 1` / `_unpack_raw()`'s
generic 16-bit-container handling are bit-depth-agnostic by construction.

## Validation results

All three ran via `scripts/validate_v4l2_zero2w.py` against `/dev/video0`
after `systemctl stop ogscope.service` (frees the device from picamera2's
exclusive hold), with `ogscope.service` restarted afterward to restore normal
operation.

**`init`** - media pipeline configuration + control discovery:

```
initialize() -> True
media_pipeline: {'enabled': True, 'state': 'configured', 'error': None}
control_readback: {'verified': True, 'error': None}
signal_levels: {'black_level': 0, 'white_level': 4095, 'sources': {'black_level': 'fallback', 'white_level': 'bit_depth'}}
line_duration_us: 22.2222   line_duration_source: sensor_controls
actual_exposure_us: 10000   actual_analogue_gain: 1.0
```

`white_level=4095` confirms the 12-bit path (`2^12-1`) computed correctly.
`line_duration_source: sensor_controls` confirms line duration came from the
real `pixel_rate`/`horizontal_blanking` controls, not the IMX327 fallback
estimate.

**`exposure`** - sweep 1ms/10ms/50ms/200ms, all with verified readback
matching the request exactly (200ms exercises the vertical_blanking
auto-extension path):

```
set_exposure(1000)   -> True  actual_exposure_us=1000    control_readback={'verified': True, 'error': None}
set_exposure(10000)  -> True  actual_exposure_us=10000   control_readback={'verified': True, 'error': None}
set_exposure(50000)  -> True  actual_exposure_us=50000   control_readback={'verified': True, 'error': None}
set_exposure(200000) -> True  actual_exposure_us=200000  control_readback={'verified': True, 'error': None}
```

**`capture`** - real RAW capture through `_unpack_raw` -> `_debayer`, indoor/
bright test scene (not night sky - see [Still open](#still-open-before-this-becomes-the-default)):

```
frame 0: shape=(720, 1280, 3) dtype=uint8 min=33 max=79 mean=50.47
frame 1: shape=(720, 1280, 3) dtype=uint8 min=30 max=66 mean=44.30
frame 2: shape=(720, 1280, 3) dtype=uint8 min=27 max=56 mean=39.41
```

Correct shape/dtype (RGB888, matches `output_pixel_format`), non-degenerate
pixel values (not all-zero, not saturated). A 40-frame run converged to a
stable mean (~51.4) by the last several frames, consistent with the software
AE loop settling.

## Memory comparison (the actual motivation for this branch)

Measured on this exact device, same capture workload, same board:

| | picamera2/libcamera (current default, live measurement) | V4L2RawCamera (this branch, `capture` stage x40 frames) |
|---|---|---|
| Process RSS | **226 MB** (`ogscope.main`, live pid) | **53 MB** |
| CMA consumed | **~146 MB** of the 256MB pool (`CmaFree` dropped to 876kB at OOM time; ~145MB free with the service stopped, ~118MB free right after start) | **~27 MB** (`CmaFree` 145360kB -> 117504kB during capture) |
| dmabuf handles | ~14 `/dmabuf:picamera2-0`/`picamera2-1` fds (dual-stream, multi-buffered) + `/dmabuf:ls_grid` | none visible (no persistent dmabuf fds found in `/proc/<pid>/fd`) |

**~4x lower process RSS, ~5x lower CMA usage**, on the same hardware, same
capture resolution. This is the single largest lever found during the
broader OGScope/ZenitAPA memory investigation this session - see
`docs/zenit-align-mini-overview.md` in the BSP repo for the OOM this
originated from. Measurement methodology: `/proc/<pid>/status` (`VmRSS`),
`/proc/meminfo` (`CmaFree`), and `/proc/<pid>/fd` listing, immediately before
vs. during each backend's active capture, on an otherwise-idle device with
only `zenitapa.service` also running.

## Still open before this becomes the default

Per this board's and the handoff doc's own acceptance gate - **do not** flip
`OGSCOPE_CAMERA_TYPE` to `v4l2` as a product default, and keep alignment/
motors disabled against it, until:

1. Real night-sky solve accuracy validated (this round used an indoor/bright
   scene - `TOO_FEW`-style rejection or correct solves under actual dim star
   fields not yet exercised on this board).
2. Software AE convergence validated under real dark-sky brightness levels,
   not just the exposure-sweep control-plane check done here (that confirms
   the sensor accepts and reports back the requested values - it says
   nothing about whether the AE control loop's decisions are correct absent
   real signal statistics).
3. Long-run stability (repeated start/stop, extended capture sessions) - only
   a short 40-frame run and a few init/exposure calls were exercised here.
4. City-glow, cloud, and moon/light-pollution scenarios per the handoff's own
   listed test matrix.

## Correction to the original handoff document

The handoff (`ogscope-v4l2-camera-handoff-en.md`) references
`docs/ogscope-v4l2-camera.md` for "the complete compatibility analysis" -
that file does not exist in this branch, `feature/v4l2-camera-current`,
`feature/v4l2-camera`, or `feature/v4l2-camera-v2` (checked all four). The
only doc that actually exists is `docs/development/v4l2-auto-exposure.md`,
which this document complements.
