"""Tầm nhìn của camera lên một đám điểm (z-buffer có tính che khuất): dùng chung cho `scripts/annotate_segments.py` (chọn đầu mút) và `pipeline/eval` (vùng đánh giá).

Chuyển nguyên hành vi từ `annotate_segments.py` (09/11); chỉ thêm `with_spread`. Chẩn đoán/đánh giá, không đổi kết quả pipeline."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np


def project_upright(d: np.ndarray, k: Tuple[float, float, float, float], rot: str) -> Tuple[np.ndarray, np.ndarray]:
    """Điểm trong toạ độ camera OpenCV (x phải, y xuống, z trước) → pixel (u, v) của ảnh ĐÃ XOAY ĐỨNG theo `rot` (none | cw90 | ccw90 | rot180);
    k = (fx, fy, cx, cy) của ảnh đã xoay (như `keyframes.csv`). Điểm có z ≤ 0 trả về giá trị vô nghĩa, người gọi tự lọc."""
    fx, fy, cx, cy = k
    zs = np.where(d[:, 2] > 1e-9, d[:, 2], 1.0)
    x, y = d[:, 0] / zs, d[:, 1] / zs
    if rot == "none":
        return fx * x + cx, fy * y + cy
    if rot == "cw90":
        return cx - fx * y, fy * x + cy
    if rot == "ccw90":
        return fx * y + cx, cy - fy * x
    if rot == "rot180":
        return cx - fx * x, cy - fy * y
    raise ValueError(f"rot_applied không hợp lệ: {rot!r}")


def point_visibility(points: np.ndarray, cams: List[Dict], size: Tuple[int, int], margin: int = 20, z_range: Tuple[float, float] = (0.5, 4.5),
                     cell: int = 8, occl: float = 0.12, voxel: float = 0.02, with_spread: bool = True) -> Tuple[np.ndarray, np.ndarray]:
    """Mỗi điểm: (số keyframe nhìn thấy, góc tia ước lượng °). Nhìn thấy = trong ảnh (cách mép ≥ margin px), độ sâu trong z_range, không bị
    che (z-buffer ô `cell` px, dung sai `occl` m). Góc tia = 2 × góc lớn nhất giữa hướng tới camera và hướng trung bình (ước lượng thô).
    Tính trên điểm voxel hoá `voxel` rồi gán cho điểm gần nhất (điểm hiển thị có thể tới hàng triệu).
    `cams`: {R (camera → thế giới), c (tâm), k = (fx, fy, cx, cy), rot}. `with_spread=False` bỏ phần góc tia (trả về mảng 0), đỡ tốn bộ nhớ khi chỉ cần số view."""
    from scipy.spatial import cKDTree

    _, keep = np.unique(np.floor(points / voxel).astype(np.int64), axis=0, return_index=True)
    sub = points[keep]
    w, h = size
    nvis = np.zeros(len(sub), dtype=int)
    sum_dir = np.zeros((len(sub), 3))
    per_cam = []
    for cam in cams:
        d = (sub - cam["c"]) @ cam["R"]                                     # = Rᵀ (p − c), toạ độ camera OpenCV
        z = d[:, 2]
        ok = z > z_range[0]
        u, v = project_upright(d, cam["k"], cam.get("rot", "none"))
        inside = ok & (u >= margin) & (u < w - margin) & (v >= margin) & (v < h - margin) & (z < z_range[1])
        key = (np.clip(v, 0, h - 1) // cell).astype(int) * (w // cell + 1) + (np.clip(u, 0, w - 1) // cell).astype(int)
        zbuf = np.full((h // cell + 1) * (w // cell + 1), np.inf)
        np.minimum.at(zbuf, key[ok], z[ok])
        vis = inside & (z <= zbuf[key] + occl)
        nvis += vis
        if not with_spread:
            continue
        dv = cam["c"] - sub
        dv /= np.maximum(np.linalg.norm(dv, axis=1, keepdims=True), 1e-9)
        sum_dir[vis] += dv[vis]
        per_cam.append((vis, dv))
    mean = sum_dir / np.maximum(np.linalg.norm(sum_dir, axis=1, keepdims=True), 1e-9)
    spread = np.zeros(len(sub))
    for vis, dv in per_cam:
        ang = np.degrees(np.arccos(np.clip((dv * mean).sum(axis=1), -1.0, 1.0)))
        spread = np.where(vis, np.maximum(spread, ang), spread)
    _, nn = cKDTree(sub).query(points)
    return nvis[nn], 2.0 * spread[nn]
