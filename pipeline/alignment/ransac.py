"""RANSAC + Umeyama trên tâm camera, và đổi sang mét. ĐC §15.1–§15.2, công thức (4), (13)–(18).

Mỗi chunk VGGT có hệ toạ độ riêng (camera đầu chunk là gốc), nên căn từng chunk một lần:
x_i = tâm camera VGGT, y_i = tâm camera COLMAP của cùng view.
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Dict, Optional

import numpy as np

from ..common.geometry import apply_sim3, umeyama_sim3


def sim3_residuals(s: float, r: np.ndarray, t: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.linalg.norm(apply_sim3(s, r, t, x) - y, axis=1)


def reference_distance(y: np.ndarray) -> float:
    """Khoảng cách trung vị giữa hai camera liên tiếp (đv COLMAP); dùng để đặt ngưỡng inlier tương đối."""
    y = np.asarray(y, dtype=np.float64)
    if len(y) < 2:
        raise ValueError("cần ít nhất 2 camera")
    return float(np.median(np.linalg.norm(np.diff(y, axis=0), axis=1)))


def threshold_from_ratio(y: np.ndarray, max_error_ratio: float) -> float:
    """Ngưỡng inlier = max_error_ratio × khoảng cách camera trung vị (align.ransac.max_error_ratio)."""
    if max_error_ratio is None:
        raise ValueError("align.ransac.max_error_ratio chưa có giá trị; chưa có căn cứ trong đề cương")
    return float(max_error_ratio) * reference_distance(y)


def ransac_sim3(x: np.ndarray, y: np.ndarray, thresh: float, min_pairs: int = 3,
                max_iters: int = 2000, seed: int = 0) -> Dict:
    """Chọn nghiệm Sim(3) có nhiều inlier nhất rồi giải lại Umeyama trên các inlier (§15.1).

    thresh: ngưỡng sai số (cùng đơn vị với y). Nếu số tổ hợp C(n, min_pairs) ≤ max_iters thì duyệt hết
    (xác định), ngược lại lấy mẫu ngẫu nhiên với `seed`.
    Trả về dict: s, R, t, inliers (mask bool), n_pairs, n_inliers, rmse (trên inlier).
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = len(x)
    if n < min_pairs:
        raise ValueError(f"cần ít nhất {min_pairs} cặp, nhận {n}")

    if math.comb(n, min_pairs) <= max_iters:
        subsets = list(combinations(range(n), min_pairs))
    else:
        rng = np.random.default_rng(seed)
        subsets = [tuple(rng.choice(n, size=min_pairs, replace=False)) for _ in range(max_iters)]

    best = None  # (n_inliers, -rmse, s, R, t, mask)
    for idx in subsets:
        idx = list(idx)
        try:
            s, r, t = umeyama_sim3(x[idx], y[idx])
        except ValueError:
            continue
        if not np.isfinite(s) or s <= 0:
            continue
        res = sim3_residuals(s, r, t, x, y)
        mask = res < thresh
        cnt = int(mask.sum())
        if cnt < min_pairs:
            continue
        rmse = float(np.sqrt(np.mean(res[mask] ** 2)))
        key = (cnt, -rmse)
        if best is None or key > (best[0], best[1]):
            best = (cnt, -rmse, s, r, t, mask)

    if best is None:
        raise ValueError("RANSAC không tìm được nghiệm với ngưỡng này (không đủ inlier)")

    _, _, s, r, t, mask = best
    for _ in range(5):  # giải lại trên inlier cho tới khi tập inlier ổn định
        if mask.sum() < min_pairs:
            break
        s, r, t = umeyama_sim3(x[mask], y[mask])
        new_mask = sim3_residuals(s, r, t, x, y) < thresh
        if np.array_equal(new_mask, mask):
            break
        mask = new_mask
    res = sim3_residuals(s, r, t, x, y)
    return {
        "s": float(s), "R": r, "t": t, "inliers": mask,
        "n_pairs": int(n), "n_inliers": int(mask.sum()),
        "rmse": float(np.sqrt(np.mean(res[mask] ** 2))),
    }


def metric_scale(l_real: float, l_model: float) -> float:
    """s_m = L_real / L_model  (4). L_real: m (mốc 1–2 m đo bằng laser/Faro); L_model: đv COLMAP."""
    if l_real <= 0 or l_model <= 0:
        raise ValueError("L_real và L_model phải > 0")
    return float(l_real / l_model)


def to_metric(points_vggt: np.ndarray, s: float, r: np.ndarray, t: np.ndarray, s_m: float) -> np.ndarray:
    """X_mét = s_m (s R X_VGGT + t)  (18)."""
    return s_m * apply_sim3(s, r, t, points_vggt)


def total_scale(s: float, s_m: Optional[float]) -> float:
    """s_tổng = s · s_m  (18): mét trên mỗi đv VGGT."""
    return float(s * s_m)
