"""Test xoay ảnh theo sky_direction và cập nhật intrinsics (quyết định của nhóm; ảnh scene 42444738, sky=Left)."""

import numpy as np
import pytest

from pipeline.common.geometry import (
    SKY_TO_ROT, project, rotate_camera_axes, rotate_intrinsics, rotate_pixels, rotation_for_sky,
)
from pipeline.keyframe.orientation import rotate_image, upright

# Intrinsics thật của scene 42444738 (lowres_wide_intrinsics)
W, H, FX, FY, CX, CY = 256, 192, 213.293, 213.293, 128.371, 95.7593


def test_rotation_for_sky():
    assert rotation_for_sky("Up") == "none"
    assert rotation_for_sky("Left") == "cw90"
    assert rotation_for_sky("Down") == "rot180"
    assert rotation_for_sky("Right") == "ccw90"
    assert set(SKY_TO_ROT) == {"Up", "Left", "Down", "Right"}
    for bad in ("NA", "", "left"):
        with pytest.raises(ValueError):
            rotation_for_sky(bad)  # NA phải xem tay, không đoán


def test_rotate_intrinsics_real_sample_left():
    w2, h2, fx2, fy2, cx2, cy2 = rotate_intrinsics(W, H, FX, FY, CX, CY, "cw90")
    assert (w2, h2) == (192, 256)
    assert fx2 == pytest.approx(213.293) and fy2 == pytest.approx(213.293)
    assert cx2 == pytest.approx(96.2407, abs=1e-3)   # h − cy
    assert cy2 == pytest.approx(128.371, abs=1e-3)   # cx


def test_rotate_intrinsics_other_directions():
    assert rotate_intrinsics(W, H, FX, FY, CX, CY, "none") == (W, H, FX, FY, CX, CY)
    w2, h2, _fx, _fy, cx2, cy2 = rotate_intrinsics(W, H, FX, FY, CX, CY, "ccw90")
    assert (w2, h2) == (192, 256) and cx2 == pytest.approx(CY) and cy2 == pytest.approx(W - CX)
    w3, h3, _a, _b, cx3, cy3 = rotate_intrinsics(W, H, FX, FY, CX, CY, "rot180")
    assert (w3, h3) == (W, H) and cx3 == pytest.approx(W - CX) and cy3 == pytest.approx(H - CY)
    with pytest.raises(ValueError):
        rotate_intrinsics(W, H, FX, FY, CX, CY, "bad")


@pytest.mark.parametrize("rot", ["none", "cw90", "ccw90", "rot180"])
def test_intrinsics_rotation_is_consistent_with_projection(rot):
    # Chiếu điểm 3D bằng camera gốc rồi xoay pixel == chiếu điểm đã đổi trục bằng camera đã xoay
    rng = np.random.default_rng(5)
    pts = np.column_stack([rng.uniform(-1, 1, 40), rng.uniform(-0.7, 0.7, 40), rng.uniform(1.0, 4.0, 40)])
    k = np.array([[FX, 0, CX], [0, FY, CY], [0, 0, 1.0]])
    uv = project(k, np.eye(3), np.zeros(3), pts)
    uv_rot = rotate_pixels(uv, W, H, rot)

    w2, h2, fx2, fy2, cx2, cy2 = rotate_intrinsics(W, H, FX, FY, CX, CY, rot)
    k2 = np.array([[fx2, 0, cx2], [0, fy2, cy2], [0, 0, 1.0]])
    pts2 = pts @ rotate_camera_axes(rot).T
    assert np.allclose(project(k2, np.eye(3), np.zeros(3), pts2), uv_rot, atol=1e-9)


@pytest.mark.parametrize("rot", ["cw90", "ccw90", "rot180"])
def test_image_rotation_matches_pixel_mapping(rot):
    img = np.zeros((H, W), dtype=np.uint8)
    row, col = 30, 200
    img[row, col] = 255
    out = rotate_image(img, rot)
    u, v = rotate_pixels(np.array([[col + 0.5, row + 0.5]]), W, H, rot)[0]  # tâm pixel ở nửa số nguyên
    r2, c2 = np.argwhere(out == 255)[0]
    assert (c2, r2) == (int(np.floor(u)), int(np.floor(v)))
    assert out.shape == ((W, H) if rot != "rot180" else (H, W))


def test_upright_wrapper_left():
    img = np.zeros((H, W, 3), dtype=np.uint8)
    out, (fx, fy, cx, cy), rot = upright(img, (FX, FY, CX, CY), "Left")
    assert rot == "cw90" and out.shape == (W, H, 3)
    assert (cx, cy) == (pytest.approx(H - CY), pytest.approx(CX))
