"""Confidence fusion. ĐC §16, công thức (19)–(22).

Chỉ số: i = view, k = điểm/correspondence (§16, §23). Mảng có trục cuối là view i; trục đầu (nếu có) là
điểm k. `mask` đánh dấu view nhìn thấy điểm k (tập V_k); view không thấy không tham gia.
Ký hiệu theo PDF: w = trọng số THÔ (19); w̃ = trọng số ĐÃ CHUẨN HÓA (22).
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

from ..common.quality import f_err


def raw_weight(c_model, f_e, f_sigma, q_blur, q_texture, q_exposure) -> np.ndarray:
    """w_{i,k} = c_model · f(e_reproj) · f(σ_depth) · q_blur · q_texture · q_exposure  (19).

    Cả sáu thừa số nằm trong [0, 1]. Phép nhân: chỉ cần một tín hiệu rất thấp là cả view bị hạ mạnh.
    """
    factors = [np.asarray(v, dtype=np.float64) for v in (c_model, f_e, f_sigma, q_blur, q_texture, q_exposure)]
    out = factors[0]
    for f in factors[1:]:
        out = out * f
    return out


def weights_from_signals(c_model, e_reproj, sigma_depth, q_blur, q_texture, q_exposure,
                         tau_e: float, tau_sigma: float, use_quality: bool = True) -> np.ndarray:
    """Đổi sai số thành điểm bằng f(x) = e^{−x/τ} (21) rồi nhân theo (19).

    e_reproj: px; sigma_depth: MÉT (nhân s_m trước khi gọi, vì τ_σ = 0,20 m); tau_e: px; tau_sigma: m.
    use_quality=False là Ablation 1: bỏ q_blur, q_texture, q_exposure (coi bằng 1).
    """
    f_e = f_err(e_reproj, tau_e)
    f_s = f_err(sigma_depth, tau_sigma)
    if not use_quality:
        q_blur = q_texture = q_exposure = 1.0
    return raw_weight(c_model, f_e, f_s, q_blur, q_texture, q_exposure)


def normalize_weights(w: np.ndarray, mask: Optional[np.ndarray] = None) -> np.ndarray:
    """w̃_{i,k} = w_{i,k} / Σ_{j∈V_k} w_{j,k}  (22), chuẩn hóa theo trục cuối.

    Điểm có tổng w bằng 0 (mọi view đều ≈ 0): đề cương không nêu; ta chia đều cho các view nhìn thấy
    điểm để không sinh NaN [Suy luận], người gọi nên ghi log những điểm này.
    """
    w = np.asarray(w, dtype=np.float64)
    m = np.ones_like(w, dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    wm = np.where(m, w, 0.0)
    total = wm.sum(axis=-1, keepdims=True)
    count = m.sum(axis=-1, keepdims=True)
    safe_total = np.where(total > 0, total, 1.0)
    uniform = np.where(m, 1.0 / np.maximum(count, 1), 0.0)
    return np.where(total > 0, wm / safe_total, uniform)


def fuse(points: np.ndarray, w: np.ndarray, mask: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
    """P̂_k = Σ_i w̃_{i,k} P_{i,k}  (22). Trả về (P̂, w̃).

    points: (..., V) cho độ sâu hoặc (..., V, 3) cho toạ độ 3D; w: (..., V).
    """
    w_tilde = normalize_weights(w, mask)
    points = np.asarray(points, dtype=np.float64)
    if points.ndim == w_tilde.ndim:
        p_hat = (w_tilde * points).sum(axis=-1)
    elif points.ndim == w_tilde.ndim + 1:
        p_hat = (w_tilde[..., None] * points).sum(axis=-2)
    else:
        raise ValueError(f"shape không khớp: points {points.shape}, w {w_tilde.shape}")
    return p_hat, w_tilde


def gate_weight(w: np.ndarray, w_tilde: np.ndarray) -> np.ndarray:
    """w_k = Σ_i w̃_{i,k}·w_{i,k}: trọng số tin cậy của điểm đã ghép, đưa sang cổng (24).

    Quyết định của nhóm (đề cương chỉ nói 'trọng số tin cậy từ fusion'). Với một view duy nhất, w_k = w.
    """
    return (np.asarray(w_tilde, dtype=np.float64) * np.asarray(w, dtype=np.float64)).sum(axis=-1)
