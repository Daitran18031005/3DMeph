"""Chỉ số đánh giá. ĐC §20.1–§20.2 và §11.1, công thức (7), (31)–(37).

Đơn vị: mét ở đầu vào; hàm trả về mét trừ khi tên hàm nói khác (…_cm, …_percent).
"""

from __future__ import annotations

from typing import Dict, Mapping, Sequence

import numpy as np
from scipy.spatial import cKDTree

from ..common.geometry import apply_sim3, umeyama_sim3

# ---------------------------------------------------------------------------
# Chiều dài  (32)(33)
# ---------------------------------------------------------------------------


def length_errors(pred_m: Sequence[float], true_m: Sequence[float]) -> np.ndarray:
    """|ℓ̂_m − ℓ_m| (m). Mốc scale (used_as_anchor) KHÔNG được đưa vào đây."""
    return np.abs(np.asarray(pred_m, dtype=np.float64) - np.asarray(true_m, dtype=np.float64))


def mae_cm(pred_m, true_m) -> float:
    return float(length_errors(pred_m, true_m).mean() * 100.0)


def median_cm(pred_m, true_m) -> float:
    return float(np.median(length_errors(pred_m, true_m)) * 100.0)


def mape_percent(pred_m, true_m) -> float:
    t = np.asarray(true_m, dtype=np.float64)
    return float((length_errors(pred_m, t) / t).mean() * 100.0)


def percent_under_cm(pred_m, true_m, threshold_cm: float = 5.0) -> float:
    return float((length_errors(pred_m, true_m) * 100.0 < threshold_cm).mean() * 100.0)


# ---------------------------------------------------------------------------
# Hình học  (34)(35)
# ---------------------------------------------------------------------------


def accuracy_completeness(model_pts: np.ndarray, gt_pts: np.ndarray):
    """Acc = mean_p min_q ‖p−q‖ (mô hình → chuẩn); Comp = mean_q min_p ‖q−p‖ (chuẩn → mô hình)."""
    p = np.asarray(model_pts, dtype=np.float64)
    g = np.asarray(gt_pts, dtype=np.float64)
    d_pg, _ = cKDTree(g).query(p)
    d_gp, _ = cKDTree(p).query(g)
    return float(d_pg.mean()), float(d_gp.mean()), d_pg, d_gp


def chamfer(acc: float, comp: float) -> float:
    """Chamfer = (Acc + Comp) / 2  (34)."""
    return (acc + comp) / 2.0


def precision_recall(d_pg: np.ndarray, d_gp: np.ndarray, delta: float = 0.05):
    """Prec_δ, Rec_δ (35) với δ = 5 cm."""
    return float((d_pg < delta).mean()), float((d_gp < delta).mean())


def f_score(prec: float, rec: float) -> float:
    """F_δ = 2·Prec·Rec / (Prec + Rec)  (35)."""
    return 0.0 if prec + rec == 0 else 2.0 * prec * rec / (prec + rec)


# ---------------------------------------------------------------------------
# Mặt phẳng và camera  (36)(37)
# ---------------------------------------------------------------------------


def p2plane(points: np.ndarray, n: np.ndarray, d: float) -> float:
    """P2Plane = (1/|P_π|) Σ |nᵀp + d|  (36), mét."""
    n = np.asarray(n, dtype=np.float64)
    return float(np.abs(np.atleast_2d(points) @ n + d).mean())


def plane_recall(n_found: int, n_gt: int) -> float:
    """PlaneRecall = #{plane chuẩn được tìm thấy} / #{plane chuẩn}  (36)."""
    if n_gt <= 0:
        raise ValueError("n_gt phải > 0")
    return n_found / n_gt


def ate_rmse(est: np.ndarray, gt: np.ndarray) -> float:
    """ATE = sqrt( (1/N) Σ ‖c_est − c_gt‖² )  (37). Quỹ đạo phải đã căn."""
    e = np.asarray(est, dtype=np.float64)
    g = np.asarray(gt, dtype=np.float64)
    return float(np.sqrt(np.mean(np.sum((e - g) ** 2, axis=1))))


def ate_after_sim3(est: np.ndarray, gt: np.ndarray) -> float:
    """ATE sau khi căn quỹ đạo bằng Sim(3) (Umeyama)  (37)."""
    s, r, t = umeyama_sim3(est, gt)
    return ate_rmse(apply_sim3(s, r, t, est), gt)


# ---------------------------------------------------------------------------
# Tổng hợp
# ---------------------------------------------------------------------------


def delta_percent(m_before: float, m_after: float) -> float:
    """Δ% = (m_trước − m_sau) / m_trước × 100  (31); dương = tốt hơn."""
    return (m_before - m_after) / m_before * 100.0


def space_average(values_by_scene: Mapping[str, float], space_of_scene: Mapping[str, str]) -> float:
    """m̄ = (1/|G|) Σ_g (1/|g|) Σ_{s∈g} m_s  (7): trung bình theo không gian độc lập (Replica: 18 scene → 13 không gian)."""
    groups: Dict[str, list] = {}
    for scene, v in values_by_scene.items():
        groups.setdefault(space_of_scene[scene], []).append(v)
    return float(np.mean([np.mean(v) for v in groups.values()]))


def replica_space_of(scene_id: str) -> str:
    """Quy tắc ĐC §11: frl_apartment_0..5 là cùng một không gian; mọi scene khác là một không gian riêng."""
    return "frl_apartment" if scene_id.startswith("frl_apartment_") else scene_id
