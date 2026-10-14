"""统一硬件与软件画面方向 / Shared hardware and software image orientation."""

from __future__ import annotations


def hardware_flips(
    rotation: int, horizontal: bool, vertical: bool
) -> tuple[bool, bool] | None:
    """仅 0/180 度可用传感器翻转 / Only 0/180 degrees can use sensor flips."""
    if rotation not in {0, 180}:
        return None
    half_turn = rotation == 180
    return bool(horizontal) ^ half_turn, bool(vertical) ^ half_turn


def residual_geometry(
    rotation: int, horizontal: bool, vertical: bool, applied: tuple[bool, bool]
) -> tuple[int, bool, bool]:
    """扣除已生效硬件变换，保持原始逆时针语义 / Remove applied hardware flips, preserving counterclockwise rotation."""
    desired = hardware_flips(rotation, horizontal, vertical)
    if desired is not None:
        h, v = desired[0] ^ applied[0], desired[1] ^ applied[1]
        return (180, False, False) if h and v else (0, h, v)
    # 旋转 90/270 度后，横纵镜像轴互换 / Quarter turns swap the horizontal and vertical mirror axes.
    return rotation, bool(horizontal) ^ applied[1], bool(vertical) ^ applied[0]


def apply_geometry(
    image,
    rotation: int,
    horizontal: bool,
    vertical: bool,
    applied: tuple[bool, bool] = (False, False),
):
    """一次旋转或镜像生成连续像素 / Generate contiguous pixels with the necessary residual transforms."""
    import cv2
    import numpy as np

    rotation, horizontal, vertical = residual_geometry(
        rotation, horizontal, vertical, applied
    )
    if rotation:
        image = cv2.rotate(
            image,
            {
                90: cv2.ROTATE_90_COUNTERCLOCKWISE,
                180: cv2.ROTATE_180,
                270: cv2.ROTATE_90_CLOCKWISE,
            }[rotation],
        )
    if horizontal or vertical:
        image = cv2.flip(
            image, -1 if horizontal and vertical else 1 if horizontal else 0
        )
    return np.ascontiguousarray(image)
