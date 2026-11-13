"""Lọc nhiễu điểm sau fuse (M4 đợt 3). Không thuộc đề cương [Suy luận]; mặc định TẮT (`fusion.filter_*` = null).

f1 — số view: bỏ điểm có ít hơn `min_views` view lấy được (`n_views` của `fused_points.ply`).
f2 — ngoại lai thống kê theo lân cận (giống `remove_statistical_outlier` của Open3D): với mỗi điểm lấy khoảng cách trung bình tới `k` láng giềng gần nhất;
     bỏ điểm có khoảng cách trung bình > trung bình toàn cloud + `std_ratio` × độ lệch chuẩn.
"""

from __future__ import annotations

from typing import Optional

import numpy as np


def min_views_mask(n_views: np.ndarray, min_views: int) -> np.ndarray:
    """True = giữ. `min_views` ≥ 1."""
    if min_views < 1:
        raise ValueError(f"min_views phải ≥ 1, nhận {min_views}")
    return np.asarray(n_views) >= min_views


def statistical_outlier_mask(xyz: np.ndarray, k: int, std_ratio: float) -> np.ndarray:
    """True = giữ. Cloud có ≤ k điểm thì giữ hết (không đủ láng giềng)."""
    from scipy.spatial import cKDTree

    if k < 1 or std_ratio < 0:
        raise ValueError(f"cần k ≥ 1 và std_ratio ≥ 0, nhận k={k}, std_ratio={std_ratio}")
    xyz = np.asarray(xyz, dtype=np.float64)
    if len(xyz) <= k:
        return np.ones(len(xyz), bool)
    d, _ = cKDTree(xyz).query(xyz, k=k + 1, workers=-1)             # cột 0 là chính điểm
    md = d[:, 1:].mean(axis=1)
    return md <= md.mean() + std_ratio * md.std()


def noise_keep_mask(xyz: np.ndarray, n_views: np.ndarray, min_views: Optional[int] = None, sor_std_ratio: Optional[float] = None,
                    sor_k: int = 20) -> np.ndarray:
    """Hợp hai bộ lọc (bộ nào `None` thì tắt). Lọc theo số view trước, rồi ngoại lai thống kê trên phần còn lại."""
    keep = np.ones(len(xyz), bool)
    if min_views is not None:
        keep &= min_views_mask(n_views, int(min_views))
    if sor_std_ratio is not None and keep.any():
        idx = np.nonzero(keep)[0]
        keep[idx[~statistical_outlier_mask(np.asarray(xyz)[idx], int(sor_k), float(sor_std_ratio))]] = False
    return keep
