"""Tín hiệu hình học từ COLMAP cho fusion (ĐC §14, kế hoạch §4.2): `e_reproj` theo từng quan sát và bản đồ nội suy, `σ_depth`.

- `e_reproj = ‖π(R X + t) − x‖` (px) tính theo TỪNG quan sát (i, điểm 3D); COLMAP không xuất sẵn (ĐC §14.4).
- `e_reproj_map`: nội suy thưa → dày bằng IDW trong bán kính cắt; ngoài bán kính gán `e_cap` (suy luận của nhóm, ĐC chỉ nói "tự cài đặt").
- `σ_depth = |d_photometric − d_geometric|`, đơn vị COLMAP; nhân `s_m` thành mét trước khi vào (19).
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
from scipy.spatial import cKDTree

from ..common.geometry import reproj_error

E_REPROJ_RADIUS_PX = 32.0     # bán kính cắt IDW (px) [Suy luận, chưa có căn cứ trong ĐC]
E_REPROJ_K = 8                # số quan sát gần nhất dùng cho IDW


def observations_from_model(rec) -> Dict[str, np.ndarray]:
    """Mọi quan sát (ảnh, điểm 3D) của một `pycolmap.Reconstruction`: image_id, point3d_id, xy (px), e_reproj (px)."""
    img_ids, pt_ids, xys, errs = [], [], [], []
    for pid, p in rec.points3D.items():
        for el in p.track.elements:
            img = rec.images[el.image_id]
            cam = rec.cameras[img.camera_id]
            cfw = img.cam_from_world
            xy = np.asarray(img.points2D[el.point2D_idx].xy, dtype=np.float64)
            e = reproj_error(cam.calibration_matrix(), cfw.rotation.matrix(), cfw.translation, p.xyz[None, :], xy[None, :])[0]
            img_ids.append(el.image_id)
            pt_ids.append(pid)
            xys.append(xy)
            errs.append(e)
    return {"image_id": np.asarray(img_ids, dtype=np.int64), "point3d_id": np.asarray(pt_ids, dtype=np.int64),
            "xy": np.asarray(xys, dtype=np.float64).reshape(-1, 2), "e_reproj": np.asarray(errs, dtype=np.float64)}


def interpolate_e_reproj(xy: np.ndarray, e: np.ndarray, shape, e_cap: float, radius: float = E_REPROJ_RADIUS_PX,
                         k: int = E_REPROJ_K) -> np.ndarray:
    """IDW (trọng số 1/d²) của `e` tại mọi pixel của ảnh (H, W) từ các quan sát thưa `xy` (cột, hàng). Ngoài `radius` px gán `e_cap`."""
    h, w = shape
    out = np.full((h, w), e_cap, dtype=np.float32)
    xy = np.asarray(xy, dtype=np.float64).reshape(-1, 2)
    e = np.asarray(e, dtype=np.float64)
    if len(xy) == 0:
        return out
    tree = cKDTree(xy)
    cols, rows = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)       # tâm pixel (toạ độ liên tục như COLMAP)
    q = np.stack([cols.ravel(), rows.ravel()], axis=1)
    kk = min(k, len(xy))
    d, idx = tree.query(q, k=kk, distance_upper_bound=radius)
    if kk == 1:
        d, idx = d[:, None], idx[:, None]
    valid = np.isfinite(d)
    ev = np.where(valid, e[np.minimum(idx, len(e) - 1)], 0.0)
    wgt = np.where(valid, 1.0 / np.maximum(d, 1e-3) ** 2, 0.0)
    wsum = wgt.sum(axis=1)
    val = np.where(wsum > 0, (wgt * ev).sum(axis=1) / np.where(wsum > 0, wsum, 1.0), e_cap)
    out[:] = val.reshape(h, w).astype(np.float32)
    return out


def sigma_depth_map(d_photo: np.ndarray, d_geom: np.ndarray) -> np.ndarray:
    """`|d_photo − d_geom|` (đv COLMAP); NaN ở pixel thiếu depth ở một trong hai bản đồ (≤ 0)."""
    a = np.asarray(d_photo, dtype=np.float32)
    b = np.asarray(d_geom, dtype=np.float32)
    if a.shape != b.shape:
        raise ValueError(f"depth photometric {a.shape} và geometric {b.shape} khác kích thước")
    out = np.abs(a - b)
    out[(a <= 0) | (b <= 0)] = np.nan
    return out.astype(np.float32)


def summary(values: np.ndarray, name: str, unit: str, valid: Optional[np.ndarray] = None) -> str:
    v = np.asarray(values)
    v = v[np.isfinite(v)] if valid is None else v[valid]
    if v.size == 0:
        return f"{name}: không có giá trị"
    q = np.percentile(v, [50, 90, 99])
    return f"{name}: n={v.size:,}; trung vị {q[0]:.4g}, p90 {q[1]:.4g}, p99 {q[2]:.4g} {unit}"
