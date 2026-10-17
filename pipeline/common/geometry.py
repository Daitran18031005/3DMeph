"""Hình học dùng chung. Số công thức "(n)" và mục "ĐC §x" theo đề cương
Docs/TaiTao3D_Metric_3DMeph.pdf (bản Revised 10/2026).

Quy ước: điểm là mảng (n, d), mỗi hàng một điểm; ma trận xoay R ∈ SO(d); đơn vị theo ngữ cảnh
(đv mô hình hoặc mét), hàm không tự đổi đơn vị.
"""

from __future__ import annotations

import math
from typing import Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Umeyama Sim(3)  —  ĐC §15.1, công thức (13)–(17)
# ---------------------------------------------------------------------------


def umeyama_sim3(x: np.ndarray, y: np.ndarray) -> Tuple[float, np.ndarray, np.ndarray]:
    """Nghiệm đóng bình phương tối thiểu của y ≈ s·R·x + t giữa hai tập điểm tương ứng.

    x, y: (n, d), d = 2 (minh họa) hoặc 3. Trả về (s, R, t) theo (14)–(17):
        Σxy = (1/n) Σ (y_i − μy)(x_i − μx)ᵀ = U D Vᵀ
        R = U S Vᵀ,  s = tr(D S) / σx²,  t = μy − s R μx
        S = I nếu det(U) det(V) ≥ 0, ngược lại diag(1, …, 1, −1)
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if x.shape != y.shape or x.ndim != 2:
        raise ValueError(f"x và y phải cùng shape (n, d); nhận {x.shape} và {y.shape}")
    n, d = x.shape
    if n < 2:
        raise ValueError("cần ít nhất 2 cặp điểm (đề cương yêu cầu n ≥ 3 để ổn định)")

    mu_x = x.mean(axis=0)
    mu_y = y.mean(axis=0)
    xc = x - mu_x
    yc = y - mu_y
    sigma2 = float((xc ** 2).sum() / n)  # σx² = (1/n) Σ ‖x_i − μx‖²   (14)
    if sigma2 <= 0.0:
        raise ValueError("các điểm x trùng nhau (σx² = 0), không xác định được scale")

    sigma_xy = yc.T @ xc / n  # (15)
    u, dvals, vt = np.linalg.svd(sigma_xy)
    s_diag = np.ones(d)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:  # (17)
        s_diag[-1] = -1.0
    s_mat = np.diag(s_diag)
    r = u @ s_mat @ vt  # (16)
    scale = float(np.trace(np.diag(dvals) @ s_mat) / sigma2)
    t = mu_y - scale * r @ mu_x
    return scale, r, t


def apply_sim3(s: float, r: np.ndarray, t: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """y = s·R·x + t cho mọi hàng của pts."""
    pts = np.asarray(pts, dtype=np.float64)
    return s * (pts @ np.asarray(r).T) + np.asarray(t)


# ---------------------------------------------------------------------------
# Camera, pose
# ---------------------------------------------------------------------------


def rodrigues(angle_axis: np.ndarray) -> np.ndarray:
    """Vector angle-axis (rad) → ma trận xoay 3×3 (công thức Rodrigues, ĐC §10.2)."""
    v = np.asarray(angle_axis, dtype=np.float64).reshape(3)
    theta = float(np.linalg.norm(v))
    if theta < 1e-12:
        return np.eye(3)
    k = v / theta
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(theta) * kx + (1.0 - math.cos(theta)) * (kx @ kx)


def camera_center(r_cw: np.ndarray, t_cw: np.ndarray) -> np.ndarray:
    """Tâm camera trong hệ world = −Rᵀt, với (R, t) là world→camera  (ĐC §10.2, công thức (5))."""
    return -np.asarray(r_cw).T @ np.asarray(t_cw).reshape(3)


def invert_pose(r_cw: np.ndarray, t_cw: np.ndarray) -> np.ndarray:
    """T_wc = T_cw⁻¹ = [[Rᵀ, −Rᵀt], [0, 1]]  (5). Trả về ma trận 4×4 camera→world."""
    r = np.asarray(r_cw, dtype=np.float64)
    t = np.asarray(t_cw, dtype=np.float64).reshape(3)
    twc = np.eye(4)
    twc[:3, :3] = r.T
    twc[:3, 3] = -r.T @ t
    return twc


def project(k: np.ndarray, r: np.ndarray, t: np.ndarray, xyz: np.ndarray) -> np.ndarray:
    """Phép chiếu phối cảnh λx = K[R|t]X  (10). xyz: (n, 3) → pixel (n, 2)."""
    xyz = np.atleast_2d(np.asarray(xyz, dtype=np.float64))
    cam = xyz @ np.asarray(r).T + np.asarray(t).reshape(3)
    pix = cam @ np.asarray(k).T
    return pix[:, :2] / pix[:, 2:3]


def reproj_error(k, r, t, xyz, observed_xy) -> np.ndarray:
    """e_reproj theo từng quan sát = ‖π(R X + t) − x‖ (px)  (ĐC §14.3)."""
    pred = project(k, r, t, xyz)
    return np.linalg.norm(pred - np.atleast_2d(np.asarray(observed_xy, dtype=np.float64)), axis=1)


# ---------------------------------------------------------------------------
# Xoay ảnh theo sky_direction và cập nhật intrinsics (quyết định của nhóm, xem keyframe/README)
# ---------------------------------------------------------------------------

SKY_TO_ROT = {"Up": "none", "Left": "cw90", "Down": "rot180", "Right": "ccw90"}


def rotation_for_sky(sky_direction: str) -> str:
    """Up→0°, Left→90° CW, Down→180°, Right→90° CCW. Giá trị khác (ví dụ NA) → ValueError."""
    try:
        return SKY_TO_ROT[sky_direction]
    except KeyError:
        raise ValueError(f"sky_direction không hợp lệ: {sky_direction!r} (cần Up/Left/Down/Right; NA phải xem tay)")


def rotate_intrinsics(w: int, h: int, fx: float, fy: float, cx: float, cy: float, rot: str):
    """Intrinsics sau khi xoay ảnh upright. Toạ độ pixel liên tục như COLMAP (tâm pixel ở nửa số nguyên).

    rot: none | cw90 | ccw90 | rot180. Trả về (w', h', fx', fy', cx', cy').
      cw90 : w'=h, h'=w, fx'=fy, fy'=fx, cx'=h−cy, cy'=cx
      ccw90: w'=h, h'=w, fx'=fy, fy'=fx, cx'=cy,   cy'=w−cx
      rot180: w'=w, h'=h, fx'=fx, fy'=fy, cx'=w−cx, cy'=h−cy
    """
    if rot == "none":
        return w, h, fx, fy, cx, cy
    if rot == "cw90":
        return h, w, fy, fx, h - cy, cx
    if rot == "ccw90":
        return h, w, fy, fx, cy, w - cx
    if rot == "rot180":
        return w, h, fx, fy, w - cx, h - cy
    raise ValueError(f"rot không hợp lệ: {rot!r}")


def rotate_pixels(uv: np.ndarray, w: int, h: int, rot: str) -> np.ndarray:
    """Ánh xạ toạ độ pixel liên tục (u, v) của ảnh gốc w×h sang ảnh đã xoay."""
    uv = np.atleast_2d(np.asarray(uv, dtype=np.float64))
    u, v = uv[:, 0], uv[:, 1]
    if rot == "none":
        return uv.copy()
    if rot == "cw90":
        return np.stack([h - v, u], axis=1)
    if rot == "ccw90":
        return np.stack([v, w - u], axis=1)
    if rot == "rot180":
        return np.stack([w - u, h - v], axis=1)
    raise ValueError(f"rot không hợp lệ: {rot!r}")


def rotate_camera_axes(rot: str) -> np.ndarray:
    """Ma trận 3×3 đổi toạ độ điểm từ camera gốc sang camera của ảnh đã xoay (X', Y', Z')."""
    if rot == "none":
        return np.eye(3)
    if rot == "cw90":
        return np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    if rot == "ccw90":
        return np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    if rot == "rot180":
        return np.array([[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]])
    raise ValueError(f"rot không hợp lệ: {rot!r}")


# ---------------------------------------------------------------------------
# Các công thức nhỏ khác
# ---------------------------------------------------------------------------


def overlap_percent(w_scene: float, delta: float) -> float:
    """Overlap = (W − Δ)/W × 100%  (1), ĐC §6.1."""
    if w_scene <= 0 or not (0 <= delta <= w_scene):
        raise ValueError("cần W > 0 và 0 ≤ Δ ≤ W")
    return (w_scene - delta) / w_scene * 100.0


def valid_depth(d: np.ndarray, lo: float = 0.05, hi: float = 10.0) -> np.ndarray:
    """valid(u,v) = 1[0,05 ≤ D ≤ 10] (m)  (6), ĐC §10.3. Không nội suy phần không hợp lệ."""
    d = np.asarray(d)
    return (d >= lo) & (d <= hi)


def euclid(a, b) -> float:
    """‖B − A‖₂ (30), ĐC §19.1."""
    return float(np.linalg.norm(np.asarray(b, dtype=np.float64) - np.asarray(a, dtype=np.float64)))
