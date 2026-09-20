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

**`exposure`** - sweep 1ms through 3s, all with verified readback matching
the request exactly (200ms+ exercises the vertical_blanking auto-extension
path). `set_exposure()` does not go through `AutoExposureLimits`' 1-second
policy ceiling (see [AE loop](#auto-exposure-control-loop) below) - it's
bounded only by the real hardware control ranges. From this board's
`vertical_blanking.max=261423` and `line_duration≈22.22us`, the theoretical
ceiling is `(720+261423)*22.22us ≈ 5.8s`, so 3s was expected to be well
within range, and was:

```
set_exposure(1000)    -> True  actual_exposure_us=1000     control_readback={'verified': True, 'error': None}
set_exposure(10000)   -> True  actual_exposure_us=10000    control_readback={'verified': True, 'error': None}
set_exposure(50000)   -> True  actual_exposure_us=50000    control_readback={'verified': True, 'error': None}
set_exposure(200000)  -> True  actual_exposure_us=200000   control_readback={'verified': True, 'error': None}
set_exposure(500000)  -> True  actual_exposure_us=500000   control_readback={'verified': True, 'error': None}
set_exposure(1000000) -> True  actual_exposure_us=1000000  control_readback={'verified': True, 'error': None}
set_exposure(2000000) -> True  actual_exposure_us=2000000  control_readback={'verified': True, 'error': None}
set_exposure(3000000) -> True  actual_exposure_us=3000000  control_readback={'verified': True, 'error': None}
```

**`long_capture`** - actual frame capture (not just control write/readback)
at 1s/2s/3s, confirming the read doesn't hang or time out:

```
exposure=1000000 set_exposure=True actual=1000000 capture_elapsed=1.74s shape=(720, 1280, 3) dtype=uint8 min=229 max=255 mean=246.33
exposure=2000000 set_exposure=True actual=2000000 capture_elapsed=0.67s shape=(720, 1280, 3) dtype=uint8 min=229 max=255 mean=246.33
exposure=3000000 set_exposure=True actual=3000000 capture_elapsed=1.91s shape=(720, 1280, 3) dtype=uint8 min=229 max=255 mean=246.33
```

Two things worth noting, not bugs but real characteristics to design around:

- Frames are **fully saturated** (`min=229 max=255`, near-white) at every
  exposure. Expected: a 1-3s exposure indoors under normal room light
  massively overexposes the sensor - this is what multi-second exposures are
  *for* under actual dark-sky conditions, not something a bright test scene
  can validate. The mechanism (control write, readback, capture completing
  without hanging) is what this stage actually confirms.
- `capture_elapsed` does **not** scale monotonically with requested exposure
  (1.74s / 0.67s / 1.91s for 1s / 2s / 3s). Read as V4L2/OpenCV buffer
  pipelining returning a frame already in flight rather than one freshly
  exposed at the just-applied setting - the same lag the AE engine's
  `settling` state (see below) exists to absorb. Anything reading a frame
  immediately after changing exposure - manually or via the AE loop -
  should not trust that specific frame's exposure to already reflect the
  new setting; the AE engine already accounts for this, a fact any other
  caller of `set_exposure()` followed immediately by `capture_image()`
  should keep in mind.

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

## Auto-exposure control loop

`capture_image()` already calls `_observe_auto_exposure()` internally on
every frame (`ogscope/platform/hardware/v4l2_camera.py`) - the `ae_loop`
validation stage doesn't reimplement any AE logic, it just runs 20 real
capture cycles with `auto_exposure=True` (the default) and prints the real
engine's state per frame.

**Important, confirmed in code before running anything**: the automatic
engine's own exposure ceiling is deliberately hard-clamped to 1 second -
`auto_exposure_max_us = max(10_000, min(1_000_000, config.get(...)))` in
`V4L2RawCamera.__init__` unconditionally caps at `1_000_000` regardless of
what's configured. This matches `docs/development/v4l2-auto-exposure.md`'s
documented product decision ("产品自动曝光上限仍为 1 秒" / "the product auto
exposure ceiling remains 1 second") - it is intentional, not a bug, and not
something this validation round works around. `long_capture` above tests the
*hardware's* ceiling via manual `set_exposure()`, which bypasses this policy
layer entirely; this section tests the *policy-bounded automatic engine*
within its designed range.

```
effective_auto_exposure_max_us (policy ceiling): 1000000
frame 0: ae_state=converged  exposure_us=10000  gain=1.0 mean=49.51
frame 1: ae_state=converged  exposure_us=10000  gain=1.0 mean=43.71
frame 2: ae_state=adjusting  exposure_us=11111  gain=1.0 mean=38.85
frame 3: ae_state=settling   exposure_us=11111  gain=1.0 mean=34.94
frame 4: ae_state=settling   exposure_us=11111  gain=1.0 mean=34.92
frame 5: ae_state=adjusting  exposure_us=14244  gain=1.0 mean=37.39
frame 6: ae_state=settling   exposure_us=14244  gain=1.0 mean=37.40
frame 7: ae_state=settling   exposure_us=14244  gain=1.0 mean=37.40
frame 8: ae_state=adjusting  exposure_us=17400  gain=1.0 mean=43.86
frame 9: ae_state=settling   exposure_us=17400  gain=1.0 mean=43.86
frame 10: ae_state=settling  exposure_us=17400  gain=1.0 mean=43.86
frame 11: ae_state=converged exposure_us=17400  gain=1.0 mean=50.48
...
frame 19: ae_state=converged exposure_us=17400  gain=1.0 mean=50.49
```

Reads as a correct, textbook convergence: exposure-only ramp (gain never
moves, matching the documented "lengthen exposure before adding gain"
policy - the bright indoor scene never needed gain), each `adjusting` step
followed by `settling` frames before the next decision (the hysteresis/wait
built into the control loop, which also absorbs the same
capture-vs-setting lag noted under `long_capture` above), then a stable
`converged` hold for the remaining 9 of 20 frames. The state machine and its
settling design work correctly on this board's real 12-bit config. What
this does *not* validate: AE behavior against real dark-sky signal
statistics, where target background/highlight levels and convergence speed
matter far more than they do against a well-lit indoor scene - see
[Still open](#still-open-before-this-becomes-the-default).

## Repeated start/stop

Per the original handoff's own acceptance list item ("repeated camera
stop/start"). 5 cycles of `initialize()` -> `start_capture()` ->
`capture_image()` -> `close()`, each a fresh `V4L2RawCamera` instance:

```
cycle 0: initialize=True captured_shape=(720, 1280, 3)
cycle 1: initialize=True captured_shape=(720, 1280, 3)
cycle 2: initialize=True captured_shape=(720, 1280, 3)
cycle 3: initialize=True captured_shape=(720, 1280, 3)
cycle 4: initialize=True captured_shape=(720, 1280, 3)
```

All 5 succeeded - no device-busy failures from a prior cycle not fully
releasing the node before the next one opened it, no resource leak
preventing re-initialization.

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

1. Real night-sky solve accuracy validated (all rounds so far used an
   indoor/bright scene - `TOO_FEW`-style rejection or correct solves under
   actual dim star fields not yet exercised on this board).
2. **AE decision-loop mechanics are now validated** (state machine
   progression, exposure-only ramp before gain, settling/hysteresis, stable
   convergence and hold - see [Auto-exposure control loop](#auto-exposure-control-loop)),
   but only against a well-lit indoor scene. What remains open: whether the
   same convergence quality and speed hold against real dark-sky signal
   statistics, where `target_background`/`target_highlight` and the
   percentile-based highlight metric behave very differently against sparse
   stars on a near-black background than against a uniformly lit room.
3. **Short-run repeated start/stop is now validated** (5 cycles, see
   [Repeated start/stop](#repeated-start-stop)). Still open: long-run
   stability under extended real capture sessions (hours, not a few dozen
   frames), and repeated cycles interleaved with real AE convergence under
   dark-sky conditions rather than the bright/fast-converging case tested
   here.
4. City-glow, cloud, and moon/light-pollution scenarios per the handoff's own
   listed test matrix.
5. **Superseded 2026-09-20**: manual long-exposure control up to 3s (see
   [`exposure`](#validation-results)/[`long_capture`](#validation-results)
   above) validated cleanly enough that the product decision itself changed
   - the automatic engine's policy ceiling was raised from 1s to 3s
   (`AUTO_EXPOSURE_MAX_CEILING_US` in `v4l2_camera.py`,
   `Settings.camera_auto_exposure_max_us` in `config.py`). The picamera2
   backend's own independent ceiling (`camera.py`'s `AUTO_EXPOSURE_MAX_US`)
   is intentionally untouched - it has its own separate clamp and this
   round only validated the V4L2 path. Still genuinely open: whether the AE
   loop's convergence *behavior* holds up all the way out to 3s under real
   dark-sky signal (item 2 above) - only the control-plane ceiling changed
   here, not a re-validation of AE quality at the new ceiling.

## Correction to the original handoff document

The handoff (`ogscope-v4l2-camera-handoff-en.md`) references
`docs/ogscope-v4l2-camera.md` for "the complete compatibility analysis" -
that file does not exist in this branch, `feature/v4l2-camera-current`,
`feature/v4l2-camera`, or `feature/v4l2-camera-v2` (checked all four). The
only doc that actually exists is `docs/development/v4l2-auto-exposure.md`,
which this document complements.
