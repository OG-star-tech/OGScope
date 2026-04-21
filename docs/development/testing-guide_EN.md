# OGScope testing guide (small team)

English | [中文](testing-guide.md)

This document targets 1–2 person teams. The goal is not maximum coverage but **minimum cost** regression protection against frequent changes.

## 1) Testing goals

- Protect critical paths: service starts, core APIs work, debug console essentials work.
- Reduce triage time: quickly tell **logic bugs** from **hardware environment** issues.
- Keep tests maintainable: add only **1–2** most relevant tests per change.

## 2) Test layers (recommended)

### 2.1 Unit (default)

- Runs: local machine or board.
- Traits: no real hardware, fast.
- Approach: `FakeCamera`, `monkeypatch`, temp-dir fixtures.

### 2.2 Integration (optional)

- Runs: local first, board if needed.
- Traits: module collaboration (route + service + files).

### 2.3 Hardware (board only)

- Runs: Raspberry Pi board.
- Traits: real camera and system deps only; not exhaustive branch coverage.

## 3) Current minimal test set

Included tests:

- `tests/unit/test_api.py` — root, health, API root, camera status shape.
- `tests/unit/test_debug_presets_api.py` — empty list, save, overwrite, delete.
- `tests/unit/test_debug_files_api.py` — file list, info, delete also removes `.txt` sidecar.
- `tests/unit/test_debug_camera_api.py` — debug camera status, start/stop, rotation, FPS, sampling, quality, settings update.
- `tests/conftest.py` — `temp_debug_dir` fixture to avoid polluting user dirs.

## 4) Day-to-day commands

### 4.1 After local edits (every time)

```bash
poetry run pytest -q
```

### 4.2 Before commit (recommended)

```bash
poetry run pytest -q
poetry run ruff check tests ogscope
```

### 4.3 Board validation (when hardware-related)

```bash
sudo systemctl restart ogscope
sudo systemctl status ogscope
sudo journalctl -u ogscope -f
```

## 5) Rules for new tests (low pressure)

- Each feature change: at least **one happy-path** test.
- Each bugfix: at least **one regression** test.
- Prefer APIs that **break easily** or have **high impact**.
- Do not aim for full coverage in one shot—expand iteratively.

## 6) Suggested next increments

1. Smoke for `/api/camera/*` simulation branch.
2. Exception paths in `DebugPresetService.apply_preset`.
3. Failure branches in `DebugCameraService.set_size` / `set_fps`.
4. 3–5 hardware smoke tests on board (start, capture, health after restart).

## 7) FAQ

### 7.1 Why not lots of hardware tests?

Hardware tests are slow and environment-heavy—poor fit for small-team high-frequency commits. Keep hardware smoke narrow; use unit tests for branches.

### 7.2 Is ~30% coverage acceptable?

Yes at this stage. What matters is **stable regression protection on critical APIs** and fast verification per change.
