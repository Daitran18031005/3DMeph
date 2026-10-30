"""Xoay ảnh về dạng đứng theo `sky_direction` của ARKitScenes (metadata.csv) và cập nhật intrinsics.

Quy tắc (quyết định của nhóm, đã kiểm trên ảnh scene 42444738 với sky=Left):
    Up → 0°, Left → 90° CW, Down → 180°, Right → 90° CCW.
Sau xoay, hướng "lên" trong camera (quy ước OpenCV, y hướng xuống) là (0, −1, 0).
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

from ..common.geometry import rotate_intrinsics, rotation_for_sky


def rotate_image(img: np.ndarray, rot: str) -> np.ndarray:
    """Xoay ma trận ảnh (H, W[, C]) theo rot ∈ {none, cw90, ccw90, rot180}."""
    if rot == "none":
        return img
    if rot == "cw90":
        return np.rot90(img, k=-1)
    if rot == "ccw90":
        return np.rot90(img, k=1)
    if rot == "rot180":
        return np.rot90(img, k=2)
    raise ValueError(f"rot không hợp lệ: {rot!r}")


def rotation_for_video(deg: int) -> str:
    """Tag rotation của video (góc xoay THEO CHIỀU KIM ĐỒNG HỒ để ảnh đứng) → rot: 0→none, 90→cw90, 180→rot180, 270→ccw90."""
    try:
        return {0: "none", 90: "cw90", 180: "rot180", 270: "ccw90"}[int(deg) % 360]
    except KeyError:
        raise ValueError(f"rotation video không phải bội của 90°: {deg!r}")


def upright(img: np.ndarray, intrinsics: Tuple[float, float, float, float], sky_direction: str):
    """Trả về (ảnh đã xoay, (fx', fy', cx', cy'), rot_applied) theo `sky_direction` của ARKitScenes.

    intrinsics = (fx, fy, cx, cy) của ảnh gốc; kích thước lấy từ img.shape.
    """
    return upright_rot(img, intrinsics, rotation_for_sky(sky_direction))


def upright_rot(img: np.ndarray, intrinsics: Tuple[float, float, float, float], rot: str):
    """Như `upright` nhưng nhận thẳng rot ∈ {none, cw90, ccw90, rot180} (video: `rotation_for_video`)."""
    h, w = img.shape[:2]
    fx, fy, cx, cy = intrinsics
    _w2, _h2, fx2, fy2, cx2, cy2 = rotate_intrinsics(w, h, fx, fy, cx, cy, rot)
    return rotate_image(img, rot), (fx2, fy2, cx2, cy2), rot
