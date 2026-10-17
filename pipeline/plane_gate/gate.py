"""Cổng và bước chiếu của plane-gated refinement. ĐC §17, công thức (23)–(25).

Mặt phẳng π: nᵀx + d = 0 với ‖n‖₂ = 1. Điểm KHÔNG qua cổng được giữ nguyên (không bị xoá): xem
ĐC Hình 20 ("gk = 0 giữ nguyên điểm"); đây là chỗ khác với ghi chú trên sơ đồ dataflow.
"""

from __future__ import annotations

from typing import Iterable, Sequence, Tuple

import numpy as np

STRUCT_CLASSES = ("wall", "floor", "ceiling")  # S_struct = {tường, sàn, trần}


def signed_distance(points: np.ndarray, n: np.ndarray, d: float) -> np.ndarray:
    """nᵀP + d (m, có dấu)."""
    n = np.asarray(n, dtype=np.float64)
    return np.atleast_2d(np.asarray(points, dtype=np.float64)) @ n + d


def residual(points: np.ndarray, n: np.ndarray, d: float) -> np.ndarray:
    """r_k = |nᵀP_k + d|  (23)."""
    return np.abs(signed_distance(points, n, d))


def angle_to_plane_deg(local_normals: np.ndarray, n: np.ndarray) -> np.ndarray:
    """θ_k = góc giữa pháp tuyến cục bộ và n, trong [0°, 90°] (bảng biến §17.1)."""
    ln = np.atleast_2d(np.asarray(local_normals, dtype=np.float64))
    ln = ln / np.linalg.norm(ln, axis=1, keepdims=True)
    nn = np.asarray(n, dtype=np.float64)
    nn = nn / np.linalg.norm(nn)
    cosang = np.clip(np.abs(ln @ nn), 0.0, 1.0)
    return np.degrees(np.arccos(cosang))


def is_structural(labels: Iterable[str]) -> np.ndarray:
    return np.isin(np.asarray(list(labels)), STRUCT_CLASSES)


def gate_mask(r: np.ndarray, theta_deg: np.ndarray, s_is_struct: np.ndarray, w: np.ndarray,
              tau_r: float, tau_n_deg: float, tau_w: float) -> np.ndarray:
    """g_k = 1[ r_k < τ_r ∧ θ_k < τ_n ∧ s_k ∈ S_struct ∧ w_k > τ_w ]  (24). Cả bốn điều kiện phải đúng."""
    r = np.asarray(r)
    return ((r < tau_r) & (np.asarray(theta_deg) < tau_n_deg)
            & np.asarray(s_is_struct, dtype=bool) & (np.asarray(w) > tau_w))


def project_to_plane(points: np.ndarray, n: np.ndarray, d: float, g: np.ndarray, alpha: float) -> np.ndarray:
    """P'_k = P_k − α g_k (nᵀP_k + d) n,  0 < α ≤ 1  (25). Chỉ điểm có g_k = 1 bị dịch."""
    if not (0.0 < alpha <= 1.0):
        raise ValueError("alpha phải thuộc (0, 1]")
    pts = np.atleast_2d(np.asarray(points, dtype=np.float64))
    n = np.asarray(n, dtype=np.float64)
    sd = signed_distance(pts, n, d)
    g = np.asarray(g, dtype=np.float64)
    return pts - alpha * (g * sd)[:, None] * n[None, :]


def force_project(points: np.ndarray, planes: Sequence[Tuple[np.ndarray, float]], alpha: float) -> np.ndarray:
    """Ablation 2 (ĐC §20.1): kéo MỌI điểm về mặt phẳng gần nhất, không cổng."""
    pts = np.atleast_2d(np.asarray(points, dtype=np.float64))
    dists = np.stack([residual(pts, n, d) for n, d in planes], axis=1)  # (K, P)
    nearest = dists.argmin(axis=1)
    out = pts.copy()
    for pi, (n, d) in enumerate(planes):
        sel = nearest == pi
        if sel.any():
            out[sel] = project_to_plane(pts[sel], n, d, np.ones(int(sel.sum())), alpha)
    return out
