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
6. **2026-09-20, applied to rpi-cm0 too**: the deployed
   `OGSCOPE_CAMERA_V4L2_*` config uses this board's exact topology -
   `SRGGB12_1X12`/`RG12`, sink-only Unicam, `/dev/v4l-subdev1` sensor - for
   **both** rpi-zero2w and rpi-cm0, on the basis that both machines use the
   same BCM2710A1 SoC, the same Unicam CSI receiver, and the same IMX327
   sensor, so the same media topology is expected to hold. This has only
   been confirmed by directly running `media-ctl`/`v4l2-ctl` on a physical
   rpi-zero2w (192.168.0.41) - not independently re-run on a physical
   rpi-cm0 board. If a real cm0 unit's discovery ever turns up a difference
   (as this board's own discovery did against the doc's older CM0-validated
   example above), the config needs updating for both machines, not just
   cm0.

## Plate-solve equivalence: picamera2 vs V4L2 (2026-09-20)

Investigated whether centroid extraction (the first stage of plate solving,
`get_centroids_from_image`) behaves equivalently between the two backends,
as a precondition for ever dropping the `python3-picamera2` dependency from
the BSP. Methodology: both backends captured the same physical (indoor,
daytime) scene on this board, using OGScope's actual production config path
(`CameraManager._build_base_config()` in `ogscope/web/camera_shared.py`,
mirrored in a throwaway comparison script) - real `auto_exposure=True` left
to converge, `ae_polar_preset`/`ae_exposure_value`/`ae_aggressive_enabled`,
`noise_reduction_mode="fast"`, `rotation=180`, lores stream, and the real
`solver_centroid_*` extraction params from `config.py`
(`sigma=2.5, bg_sub_mode=local_mean, sigma_mode=global_root_square`) -
confirmed against `/data/ogscope/ogscope.env` on this device, which has zero
camera overrides, so `Settings()` defaults are what's actually running.

**Baseline (before any fix)**: at the same production sigma threshold,
picamera2 detected 6-7 centroids, V4L2 detected 0-2, both under fixed
matched exposure and under each backend's own real auto-exposure. Root
cause, found in code: `_debayer()` did a purely linear black/white-level
stretch with no gamma or tone curve, while picamera2's libcamera ISP applies
a real gamma/tone-mapping pipeline that non-linearly boosts faint highlights
(exactly what point sources are) relative to background.

**Fix attempt 1 - gamma correction** (kept, `camera_v4l2_gamma` in
`config.py`, default 2.2): applied to the RAW code values in float32 before
quantizing to 8-bit (a first implementation applied it after the linear
8-bit stretch instead, which was a real bug - by then the dim/star-level
raw precision had already been crushed into a handful of 8-bit codes and
gamma could no longer recover it). This closed most of the *brightness*
gap (mean 35 -> 129, vs. picamera2's 165) but barely moved *contrast*: std
1.31 -> 1.36 (picamera2: 5.5+). Tested gamma=4.0 (aggressive) to check
whether the gap was just a mistuned value: brightness overshot picamera2
(175 vs 165) while std_global got *worse* (0.91) - proof the bottleneck is
local contrast, not brightness, and no monotonic global curve can fix it.

**Fix attempt 2 - CLAHE (reverted)**: added a local-contrast (adaptive
histogram equalization, LAB L-channel) stage after gamma. Contrast
statistics moved further (std 1.36 -> 3.07 at the default clip_limit=3.0)
but for the wrong reason: `patch_noise_std` jumped 0.58 -> 2.65 and
Laplacian variance to 71 (picamera2: ~2.3) - CLAHE was amplifying sensor
noise in the dark/flat background, not real star signal. Centroid count
stayed at 0 regardless. Tried clip_limit down to 1.0 (conservative):
noise still sat at 1.2-1.4 (well above picamera2's 0.68) and centroid
counts stayed at 0-1. Reverted entirely - no clip_limit tested produced a
real improvement, only worse SNR and extra per-frame CPU cost.

**Current status**: gamma correction alone is kept (`v4l2_camera.py`'s
`_debayer()` + `_build_gamma_lut()`, wired through
`camera_shared.py`/`config_catalog.py`) since it's a genuine, measured
improvement in brightness matching - but it does **not** achieve centroid-
count parity with picamera2 on this indoor test scene. `python3-picamera2`
must **not** be removed from the BSP on the basis of this investigation.

**Update, same day - V4L2-specific `solver_centroid_sigma_v4l2` implemented**:
swept `bg_sub_mode`/`sigma_mode`/`sigma` on both backends' real captures and
found that a *lower V4L2-specific sigma*, keeping the same `bg_sub_mode`/
`sigma_mode` as production (`local_mean`/`global_root_square`), reaches
picamera2-comparable detection counts without any image reshaping. Added
`Settings.solver_centroid_sigma_v4l2` and wired it into
`CentroidExtractionParams.from_settings()` (`ogscope/algorithms/plate_solve/
solver.py`) via a `camera_type == "v4l2"` check.

Important finding while tuning the default: **the matching sigma is not a
precise constant**. Across four independent captures on this same indoor
daylight scene:

| round | picamera2 count (sigma=2.5) | V4L2 sigma tested | V4L2 count |
|---|---|---|---|
| 1 | 8 | 1.9 | 8 (match) |
| 2 | 8 | 1.9 | 8 (match, repeat) |
| 3 | 11 | 1.9 | 38 (badly overshot; 2.2 would have matched exactly) |
| 4 | 12 | 2.1 (re-centered default) | 10 (close) |

Round 3 showed the initially-chosen default (1.9) can overshoot by 3-4x
under slightly different exposure/noise realizations - the real matching
value ranged ~1.9-2.2 run to run. Re-centered the default to **2.1** (the
midpoint, chosen conservatively since over-detection is the worse failure
mode for a solver - more candidate centroids means more compute and more
chances for a spurious match, vs. under-detection which just needs more
signal). This is not a precisely calibrated value; see the field's own
docstring in `config.py` for the same caveat.

**Update, same day - repeatability test reveals the count-matching approach
itself was flawed**: since the camera is physically static and looking at
the same scene, a *real* feature should produce a centroid at a
near-identical pixel position across consecutive frames, while sensor-
noise-driven spurious detections should not. Captured 10 consecutive frames
per backend (after AE convergence) and clustered detections across frames by
proximity (<=3px) to separate position-stable ("plausibly real") detections
from one-off transient ("plausibly noise") ones, using each backend's real
production sigma via `CentroidExtractionParams.from_settings()`.

**Result: zero stable detections for either backend.** Not one centroid, in
either picamera2 or V4L2, appeared in more than 1 of the 10 frames - the
single best (most frequently recurring) candidate for each backend still
only showed up once. This holds even after excluding a border margin (see
next paragraph). This means every "centroid" counted throughout this whole
investigation, for both backends, was very likely sensor/scene noise, not a
real repeatable feature - the count-matching methodology used above (tuning
V4L2's sigma to match picamera2's *count*) was comparing noise-floor
statistics between backends, not real point-source detection sensitivity.
It's still a legitimate, useful property (a backend whose noise floor
produces far more spurious candidates than the other would burden the
solver with more false candidates even under real starlight), but it does
**not** establish that V4L2 detects real faint stars as well as picamera2 -
that remains genuinely untested.

**Separate bug found along the way, independent of V4L2/picamera2**:
inspecting raw per-frame centroid positions showed ~28% of picamera2's
detections landed within 10px of the image's right edge (<1% of the image's
width). `solver.py`'s real production pipeline passes no `crop` to
`get_centroids_from_image`, so `bg_sub_mode='local_mean'`
(`scipy.ndimage.uniform_filter`) has no border exclusion and produces
spurious edge-concentrated detections. This is a real accuracy issue
affecting both backends' actual production solving (wastes solver budget on
edge artifacts, could reduce match confidence) - **not fixed here** (this
investigation only excluded a border crop in its own analysis script to get
a clean signal), but worth a separate fix (pass a centered `crop` in
`solver.py`, or otherwise exclude a border margin) independent of this
V4L2 work.

**What's actually needed to resolve backend equivalence**: a scene with a
genuine, verifiable point source above the noise floor - a small bright
LED/pinhole at distance in an otherwise dark room (simulating a star), or
real night sky. Further sigma-tuning against this indoor daylight scene
would only continue to fit noise-floor statistics, not real detection
performance, no matter how it's refined.

**Update, same day - image-quality (not solving) comparison, per explicit
request to compare "image by image" since there's no sky to solve against
right now**: switched methodology entirely away from centroid counting.
Since the camera is physically static on the same scene, captured 10
consecutive frames per backend and used the **temporal** mean/std across
frames (not a single-frame spatial patch) - the scene can't have changed, so
any per-pixel variation *across* frames is pure noise, and the per-pixel
temporal mean is the true denoised signal. This is a rigorous, correct
separation of signal from noise that a single-frame spatial-patch estimate
cannot provide.

First measurement (V4L2, gamma-only, no denoising): **picamera2 noise=0.55,
SNR=302; V4L2 noise=3.55, SNR=35 - a 6.5x noise gap.** Root cause: V4L2's
raw path applies literally zero noise reduction, while picamera2's ISP
applies real denoising by default. This explains a large part of the
contrast/detection shortfall found earlier - gamma and CLAHE were both
redistributing brightness on an already-noisy signal, never actually
removing noise.

**Fix implemented**: a temporal exponential-moving-average (EMA) noise-
reduction stage (`Settings.camera_v4l2_temporal_nr_alpha`, default 0.2;
`V4L2RawCamera._apply_temporal_nr()`). Chose temporal over spatial
denoising because the product's real use case is static/tracked
astrophotography - temporal accumulation reduces random noise without
sacrificing spatial resolution, unlike spatial filters (Gaussian/bilateral)
which always trade away real detail. The accumulator resets on any
exposure/gain change (hooked into `_apply_exposure_gain`) so frames of
different brightness are never blended together, and on `start_capture()`
so a stale accumulator from a previous run can't leak into a new session.

**A real methodological bug surfaced while validating this**: the first
retest showed only a modest improvement (noise 3.55 -> 2.43, not the ~3x
expected from alpha=0.2). Instrumentation revealed why - the AE settle-
detection used to decide "start the measurement now" declared convergence
on a single "converged" reading, but the AE kept drifting afterward
(exposure moved 61111 -> 55733 -> 51267us *during* what was supposed to be
the stable measurement window), repeatedly resetting the NR accumulator
mid-measurement. Fixed by requiring exposure to be unchanged for 8
consecutive reads before starting the measurement - confirmed 0 accumulator
resets during capture in all subsequent rounds.

**Final result, reproduced across two independent capture rounds**:

| round | picamera2 noise / SNR | V4L2 (NR alpha=0.2) noise / SNR |
|---|---|---|
| 1 | 0.820 / 200.1 | 0.288 / 423.3 |
| 2 | 0.607 / 273.3 | 0.270 / 453.7 |

**V4L2 now has consistently lower noise (2.2-2.8x) and higher SNR (1.7-2.3x)
than picamera2 on this static scene**, once measured correctly. Visually,
the fixed-pattern/lens-shading mottling noted in the pre-NR denoised image
is much less visible after the longer, properly-accumulated NR window - most
of what looked like a fixed spatial pattern apparently had enough
frame-to-frame randomness to be reduced by sufficient temporal averaging,
rather than being purely deterministic PRNU.

**Scope note**: this is a pure image-quality (noise/SNR) comparison, not a
solving or star-detection comparison - the earlier centroid-based work
(sigma tuning, the zero-stable-detections finding) remains separately
unresolved and is a different question from "is the image clear."

**Update, same day - full exposure-range sweep (10ms-3s), per concern that
the NR fix might not hold across the whole exposure range**: manual, fixed
exposure (gain=1.0 pinned, no AE) on both backends at 10ms/50ms/200ms/
500ms/1s/2s/3s on the same bright indoor scene, measuring luminance and
temporal (multi-frame) noise at each level.

Two test-methodology bugs surfaced and were fixed before the numbers were
trustworthy:
1. picamera2's manual `ExposureTime` control takes ~5 frames to actually
   propagate through the ISP pipeline (confirmed via per-frame metadata:
   `actual_exposure_us` metadata stayed at the OLD value for frames 0-4
   after a `set_exposure()` call). Measuring too soon after a change
   captured a step-function luminance jump as fake "noise" - a spurious 
   39.6/47.1 spike at 50ms/200ms that had nothing to do with real sensor
   behavior. Fixed by polling `actual_exposure_us` until it matches the
   requested value before measuring.
2. For V4L2, `set_exposure()` resets the temporal-NR accumulator (by
   design - see the NR update above), but the exposure-control readback
   settles in a single frame, well before the NR accumulator (which needs
   ~8-10 frames at alpha=0.2) reaches steady state. Measuring right after
   exposure-settle caught the accumulator mid-warmup, inflating V4L2's
   noise readings (10.88 at 200ms, later corrected to 1.76). Fixed by
   adding dedicated NR-warmup frames after exposure settles, before
   measuring.

**Final, correctly-measured result**:

| exposure_us | picam luminance | picam noise | picam clip% | v4l2 luminance | v4l2 noise | v4l2 clip% |
|---|---|---|---|---|---|---|
| 10,000 | 29.2 | 1.12 | 0% | 78.2 | 0.19 | 0% |
| 50,000 | 104.3 | 0.45 | 0% | 98.7 | 0.75 | 0% |
| 200,000 | 217.8 | 0.23 | 0% | 151.6 | 1.76 | 0% |
| 500,000 | 255.0 | 0.00 | **100%** | 216.8 | 2.09 | 0% |
| 1,000,000 | 255.0 | 0.00 | 100% | 243.7 | 0.66 | 0% |
| 2,000,000 | 255.0 | 0.00 | 100% | 246.3 | 0.00 | 0% |
| 3,000,000 | 255.0 | 0.00 | 100% | 246.3 | 0.00 | 0% |

Two honest, not-fully-one-sided findings:
- **picamera2 hard-clips at 500ms+ on this bright scene (100% of pixels at
  255); V4L2 never fully saturates**, asymptotically approaching ~246
  instead. Plausibly the gamma curve's natural highlight compression
  (`x^(1/gamma)` softly rolls off near the top rather than clipping
  abruptly) - but **not fully verified whether the underlying raw sensor
  is itself also saturating at long exposures** with the gamma LUT merely
  not mapping the top raw code to a literal 255. Don't treat "V4L2 doesn't
  clip" as a proven real-dynamic-range advantage without checking that.
- **Noise is not uniformly better for V4L2 across the whole range.** At
  10ms V4L2 is clearly better (0.19 vs 1.12, consistent with the earlier
  AE-converged-point result). But at 50-500ms, *before* picamera2
  saturates, picamera2 actually measures lower noise than V4L2 (0.45 vs
  0.75 at 50ms; 0.23 vs 1.76 at 200ms) - picamera2's noise readings at
  500ms+ are not meaningful for comparison since full saturation trivially
  produces zero measured variance, not genuine cleanliness. So the earlier
  "V4L2 has lower noise" conclusion holds at short/AE-natural exposures but
  does **not** generalize as a blanket claim across the whole 10ms-3s range
  on this scene.

As with everything else in this document, this is still a bright indoor
proxy scene, not real night sky - the exposure range that matters most for
the product (long, dim, no saturation) is exactly the range where picamera2
is already fully clipped here and uninformative to compare against.

**Update, same day - two countermeasures implemented from a true dark-frame
calibration**: with the lens physically covered (zero incident light),
captured RAW sensor frames at 10ms-3s to separate real black-level/dark-
current behavior from scene-driven signal (the earlier lit-scene test
couldn't distinguish the two - this bright indoor scene keeps accumulating
real photons even in its "shadow" region at long exposure, up to full
saturation by 1s).

**Finding 1 - black_level was hard-broken at 0.** `v4l2-ctl --list-ctrls`
confirms this sensor/driver exposes no black-level control at all, so
`_resolve_signal_levels()`'s auto-detect always failed and fell back to 0 -
meaning zero black-level correction was ever applied; the gamma curve
amplified the raw signal from code 0 instead of the sensor's real dark
floor. True dark frame (lens covered): mean raw value held steady at
240.5-244.1 (of 4095, 12-bit) across the whole 10ms-3s range, with a
negligible ~1.2 counts/sec dark-current rate - no exposure-dependent
scaling needed, a static value is enough. Fixed:
`FALLBACK_BLACK_LEVEL_FRACTION_OF_FULL_RANGE` (`v4l2_camera.py`) replaces
the old 0 fallback with this measured value, scaled proportionally by bit
depth. Verified on hardware post-fix: `black_level=240` (was 0).

**Finding 2 - a real, growing hot-pixel population, separate from the bulk
black-level bug (implemented, then reverted).** While the *mean* dark level
barely moved, the *max* raw value climbed steeply with exposure: 252 (10ms)
-> 475 (200ms) -> 1380 (1s) -> 3414 of 4095 at 3s (83% of full range, from
pure dark current, zero real light). `hot_pixel_frac` grew from 0% to
0.066% over the same range. These are classic hot pixels (individual
sensor defects with elevated dark-current leakage), worse at exactly the
long exposures the product needs for faint real targets, and
indistinguishable from real stars to any brightness-threshold detector.

Built and verified a fixed hot-pixel coordinate-map correction (lens
covered, 20 frames averaged at 3s/gain=1.0, per-same-color-Bayer-plane
outliers beyond 8 robust-sigma via MAD - 708 pixels found, 0.077% of the
sensor; correction replaced only those specific coordinates with the
median of same-color Bayer neighbors, verified pulling known hot pixels
from their raw 247-253+ values down to true background 240-242). **Reverted
per product decision**: hot pixels are individual sensor defects, not a
general IMX327 characteristic - the calibration is only valid for the one
physical board it was measured on (192.168.0.41), and a per-unit
calibration requirement (covering the lens, capturing a dark reference) is
not something the product can rely on for every unit that ships. Removed
`_load_hot_pixel_map()`/`_correct_hot_pixels()`, the
`camera_v4l2_hot_pixel_correction_enabled`/`camera_v4l2_hot_pixel_map_file`
settings, and the bundled calibration file/directory.

The black-level fix (Finding 1, static and sensor-model-general rather than
per-unit) was kept.

**Update, same day - V4L2 pipeline optimization (three iterations)**, to
close the long-exposure noise gap while keeping the memory advantage.

**Iteration 1 - temporal NR moved into the linear RAW domain.** It was
running last, on the 8-bit gamma-encoded RGB output. Moved before
gamma/debayer, because (a) averaging is only unbiased in linear space,
(b) the gamma curve is steepest near black, so denoising first kills noise
before the curve amplifies it, and (c) the accumulator shrinks from
H*W*3 float32 (~11MB) to H*W float32 (~3.7MB). Added a 16x-oversampled
gamma LUT (`GAMMA_LUT_OVERSAMPLE`) so the averaging's sub-integer precision
survives the lookup - measured output noise at 10ms is ~0.17 RAW codes,
which rounding to integers would quantize away. Result: 25-34% lower noise
across the range, and 500ms flipped from a loss to a win.

**Iteration 2 - frame-duration-aware EMA time constant**
(`_effective_temporal_nr_alpha`, `camera_v4l2_temporal_nr_seconds`,
`camera_v4l2_temporal_nr_max_frames`). Frames averaged =
temporal_nr_seconds / frame duration, clamped to [1/alpha, max_frames].
Short exposures deliver many frames per second, so averaging up to 50 of
them costs negligible wall-clock time; long exposures cost seconds per
frame, so they clamp back to the alpha bound. Result at 10ms: noise 0.05
vs picamera2's 0.16.

**Iteration 3 - found and fixed a measurement bias that had been
penalizing V4L2 at long exposures.** A fixed 8-frame NR warmup is 83% EMA
convergence at alpha=0.2 but only 57% at alpha=0.1, so the still-chasing
accumulator's transient was being measured AS noise - it made alpha=0.1
look *worse* than alpha=0.2, which is impossible. picamera2 has no
accumulator and pays no such penalty, so every prior long-exposure number
was biased against V4L2. This is the third bug of the same family in this
document (premature AE settle -> NR mid-warmup -> alpha-dependent warmup):
**whenever a stage has its own convergence, the measurement must wait for
it, and the wait must scale with that stage's time constant.**

**Final result, measured fairly (warmup scaled to alpha), same run:**

| exposure | picamera2 noise | V4L2 noise | V4L2 advantage |
|---|---|---|---|
| 10ms | 0.16 | 0.05 | 3.2x |
| 50ms | 0.47 | 0.23 | 2.0x |
| 200ms | 0.84 | 0.55 | 1.5x |
| 500ms | 0.80 | 0.48 | 1.7x |
| 1s | 0.505 | 0.138 | 3.7x |
| 2s | 0.425 | 0.138 | 3.1x |
| 3s | 0.364 | 0.134 | 2.7x |

V4L2 is now quieter than picamera2 across the whole range. A consistency
check that the measurement is finally sound: V4L2's long-exposure noise is
essentially flat (0.138/0.138/0.134), which is what theory predicts for
shot noise through a gamma-2.2 curve (output noise proportional to
x^-0.045). Note this advantage comes from temporal accumulation, which
suits static/tracked scenes but responds more slowly to real change - the
tradeoff is `camera_v4l2_temporal_nr_alpha` (its 1/alpha frame floor sets
long-exposure convergence: 5 frames = 15s at 3s exposure).

**Memory**: measured with each backend imported in isolation (going through
`create_camera()` pulls picamera2 in even for the V4L2 path, which inflates
the V4L2 number with the very dependency it exists to avoid). Peak RSS
V4L2 171.0MB vs picamera2 142.2MB; with V4L2's NR disabled 164.9MB, so the
new NR buffers cost ~6MB - less than the ~11MB accumulator the old
RGB-domain NR used, i.e. these optimizations are a net memory improvement.
**Open item**: the V4L2-vs-picamera2 RSS gap is pre-existing and not from
this work - it is `_apply_postprocessing()` converting the full H*W*3 frame
to float32 for the WB/contrast/saturation maths, several 11MB temporaries
per frame. That is the obvious next memory target. These harness figures
also do not reproduce the historical ~53MB/~226MB service-level numbers
(this harness imports the whole analysis stack), and the CmaFree-delta
readings drifted too much between runs to be trustworthy, so the
service-level RAM claim should be re-verified against the real service
rather than inferred from here.

Two considerations for whoever picks this up next:
- This indoor daylight scene may itself be a poor proxy: V4L2's software AE
  (`NightSkyAutoExposure`) always targets a dark ~3.5% background
  (`camera_v4l2_ae_target_background`) regardless of ambient light, which is
  correct for real night sky but starves contrast under bright indoor
  lighting in a way picamera2's scene-adaptive AE does not reproduce (it
  correctly stayed in normal/daylight mode rather than applying its own
  starfield preset). A real dark-scene/point-source test (or real night sky)
  is needed before drawing a final conclusion either way.
- **Done**: a V4L2-specific `solver_centroid_sigma_v4l2` (lower than
  picamera2's, see the update above) rather than trying to cosmetically
  reshape the V4L2 image to imitate picamera2's ISP output - both gamma and
  CLAHE attempts here were "make the picture look the same" approaches, and
  neither achieved real detection parity, while a lower threshold gets into
  the right order of magnitude directly.

## Correction to the original handoff document

The handoff (`ogscope-v4l2-camera-handoff-en.md`) references
`docs/ogscope-v4l2-camera.md` for "the complete compatibility analysis" -
that file does not exist in this branch, `feature/v4l2-camera-current`,
`feature/v4l2-camera`, or `feature/v4l2-camera-v2` (checked all four). The
only doc that actually exists is `docs/development/v4l2-auto-exposure.md`,
which this document complements.
