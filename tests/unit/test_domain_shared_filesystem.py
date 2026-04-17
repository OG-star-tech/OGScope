from __future__ import annotations

import pytest

from ogscope.domain.shared.filesystem import ensure_safe_basename


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

