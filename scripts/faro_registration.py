"""
faro_registration.py — hàm thuần (numpy/scipy) cho `faro_align.py`: căn thô có ràng buộc trọng lực (4 bậc tự do),
ICP point-to-plane, thống kê residual. Không có ngưỡng chấp nhận: hàm chỉ trả số liệu.

Quy ước: phép biến đổi `T` là ma trận 4×4 hệ nguồn → hệ đích, p' = R·p + t. Hệ nào cũng Z-up (đã đo: Faro z ≈ 215 m, mesh ARKit cao 2,6 m theo z).
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.ndimage import maximum_filter
from scipy.signal import fftconvolve
from scipy.spatial import cKDTree

# ---------------------------------------------------------------------------
# Tiện ích biến đổi
# ---------------------------------------------------------------------------


def rot_z(theta_rad: float) -> np.ndarray:
    c, s = np.cos(theta_rad), np.sin(theta_rad)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def make_T(r: np.ndarray, t: np.ndarray) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3], m[:3, 3] = r, np.asarray(t).reshape(3)
    return m


def apply_T(T: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return pts @ T[:3, :3].T + T[:3, 3]


def invert_T(T: np.ndarray) -> np.ndarray:
    return make_T(T[:3, :3].T, -T[:3, :3].T @ T[:3, 3])


def rotation_angle_deg(r: np.ndarray) -> float:
    return float(np.degrees(np.arccos(np.clip((np.trace(r) - 1.0) / 2.0, -1.0, 1.0))))


def yaw_deg(r: np.ndarray) -> float:
    return float(np.degrees(np.arctan2(r[1, 0], r[0, 0])))


def tilt_deg(r: np.ndarray) -> float:
    """Góc giữa trục z sau xoay và trục z gốc (độ): 0 nghĩa là phép xoay chỉ quanh trục đứng."""
    return float(np.degrees(np.arccos(np.clip(r[2, 2], -1.0, 1.0))))


def rodrigues_small(omega: np.ndarray) -> np.ndarray:
    th = float(np.linalg.norm(omega))
    if th < 1e-15:
        return np.eye(3)
    k = omega / th
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(th) * kx + (1 - np.cos(th)) * (kx @ kx)


# ---------------------------------------------------------------------------
# Điểm "cấu trúc đứng" và ảnh nhìn từ trên xuống
# ---------------------------------------------------------------------------


def structure_mask(pts: np.ndarray, cell: float = 0.05, min_zrange: float = 1.0) -> np.ndarray:
    """Mặt nạ các điểm nằm trong ô 2D (cạnh `cell`) có độ cao z trải ≥ `min_zrange` (tường, cột, đồ vật cao).
    Sàn/trần phẳng bị loại. `cell` và `min_zrange` là tham số của bước căn thô, không phải ngưỡng chấp nhận."""
    ij = np.floor(pts[:, :2] / cell).astype(np.int64)
    key = (ij[:, 0] + (1 << 30)) * (1 << 31) + (ij[:, 1] + (1 << 30))
    order = np.argsort(key, kind="stable")
    ks = key[order]
    z = pts[order, 2]
    starts = np.r_[0, np.nonzero(np.diff(ks))[0] + 1]
    zmin = np.minimum.reduceat(z, starts)
    zmax = np.maximum.reduceat(z, starts)
    tall = (zmax - zmin) >= min_zrange
    counts = np.diff(np.r_[starts, len(ks)])
    keep_sorted = np.repeat(tall, counts)
    mask = np.zeros(len(pts), dtype=bool)
    mask[order] = keep_sorted
    return mask


def raster(xy: np.ndarray, origin: np.ndarray, shape: Tuple[int, int], cell: float) -> np.ndarray:
    """Ảnh nhị phân (hàng = y, cột = x) của các điểm 2D."""
    ij = np.floor((xy - origin) / cell).astype(np.int64)
    ok = (ij[:, 0] >= 0) & (ij[:, 0] < shape[1]) & (ij[:, 1] >= 0) & (ij[:, 1] < shape[0])
    img = np.zeros(shape, dtype=np.float32)
    img[ij[ok, 1], ij[ok, 0]] = 1.0
    return img


# ---------------------------------------------------------------------------
# Căn thô 4 DoF: yaw quét + tương quan chéo FFT cho (tx, ty); z bằng tương quan histogram độ cao
# ---------------------------------------------------------------------------


def _peaks(score: np.ndarray, min_sep: int, k: int = 2) -> List[Tuple[int, int]]:
    """k đỉnh cao nhất của ảnh score cách nhau ≥ min_sep ô (Chebyshev)."""
    s = score.copy()
    out = []
    for _ in range(k):
        i = int(np.argmax(s))
        iy, ix = np.unravel_index(i, s.shape)
        if not np.isfinite(s[iy, ix]) or s[iy, ix] <= -1:
            break
        out.append((int(iy), int(ix)))
        s[max(0, iy - min_sep):iy + min_sep + 1, max(0, ix - min_sep):ix + min_sep + 1] = -np.inf
    return out


def coarse_yaw_xy(src_struct: np.ndarray, dst_struct: np.ndarray, cell: float = 0.05, yaw_step_deg: float = 0.5,
                  dilate_cells: int = 3) -> Dict:
    """Tìm yaw θ và (tx, ty) sao cho p_dst ≈ Rz(θ)·p_src + t, chỉ dùng điểm cấu trúc đứng của nguồn và đích.

    Điểm số mỗi (θ, tx, ty) = tỉ lệ ô chiếm dụng của ĐÍCH (mẫu, có thể phủ một phần phòng) mà ô nguồn đã xoay (nở ra
    `dilate_cells` ô) cũng chiếm dụng. Trả về dict gồm `T` (4×4, tz = 0), điểm số tốt nhất, đỉnh thứ hai (độ mơ hồ).
    """
    c_src = src_struct[:, :2].mean(axis=0)
    rel = src_struct[:, :2] - c_src
    radius = float(np.hypot(rel[:, 0], rel[:, 1]).max())
    n = int(np.ceil(2 * radius / cell)) + 4
    origin_src = -np.array([radius + 2 * cell, radius + 2 * cell])          # gốc canvas (trong hệ đã xoay quanh c_src)
    dst_min = dst_struct[:, :2].min(axis=0) - 2 * cell
    shape_t = tuple(int(v) for v in np.ceil((dst_struct[:, :2].max(axis=0) - dst_min) / cell).astype(int)[::-1] + 3)
    tmpl = raster(dst_struct[:, :2], dst_min, shape_t, cell)
    n_t = float(tmpl.sum())
    if n_t == 0:
        raise ValueError("đích không có ô cấu trúc")
    if shape_t[0] > n or shape_t[1] > n:
        n = max(n, max(shape_t) + 4)                                          # mẫu lớn hơn canvas: nới canvas
    tflip = tmpl[::-1, ::-1]
    best_per_yaw, results = [], []
    yaws = np.arange(0.0, 360.0, yaw_step_deg)
    for th in yaws:
        r = rot_z(np.radians(th))[:2, :2]
        xy = rel @ r.T
        img = raster(xy, origin_src, (n, n), cell)
        if dilate_cells > 1:
            img = maximum_filter(img, size=dilate_cells)
        corr = fftconvolve(img, tflip, mode="valid") / n_t
        iy, ix = np.unravel_index(int(np.argmax(corr)), corr.shape)
        best_per_yaw.append(float(corr[iy, ix]))
        results.append((th, iy, ix, float(corr[iy, ix])))
    best_per_yaw = np.array(best_per_yaw)
    i_best = int(np.argmax(best_per_yaw))

    def to_T(th, iy, ix):
        # ô (iy, ix) của canvas đã xoay ↔ ô (0, 0) của mẫu:  p_dst = xy_rot + t'  với xy_rot = R(p − c_src) (gốc canvas origin_src)
        tx_img = dst_min[0] - (origin_src[0] + ix * cell)
        ty_img = dst_min[1] - (origin_src[1] + iy * cell)
        r2 = rot_z(np.radians(th))
        t = np.array([tx_img, ty_img, 0.0])
        # p_dst = R(p − c) + t_img  ⇒  t_total = t_img − R c
        c3 = np.array([c_src[0], c_src[1], 0.0])
        return make_T(r2, t - r2 @ c3)

    th, iy, ix, sc = results[i_best]
    # tinh chỉnh yaw ±yaw_step với bước nhỏ
    fine = []
    for th2 in np.arange(th - yaw_step_deg, th + yaw_step_deg + 1e-9, yaw_step_deg / 5):
        r = rot_z(np.radians(th2))[:2, :2]
        img = raster(rel @ r.T, origin_src, (n, n), cell)
        if dilate_cells > 1:
            img = maximum_filter(img, size=dilate_cells)
        corr = fftconvolve(img, tflip, mode="valid") / n_t
        jy, jx = np.unravel_index(int(np.argmax(corr)), corr.shape)
        fine.append((float(th2 % 360.0), int(jy), int(jx), float(corr[jy, jx])))
    th, iy, ix, sc = max(fine, key=lambda a: a[3])
    # đỉnh yaw thứ hai cách ≥ 10°
    sep = int(round(10.0 / yaw_step_deg))
    masked = best_per_yaw.copy()
    for d in range(-sep, sep + 1):
        masked[(i_best + d) % len(masked)] = -1.0
    i2 = int(np.argmax(masked))
    th2n, iy2, ix2, sc2 = results[i2]
    return {"T": to_T(th, iy, ix), "yaw_deg": float(th), "score": float(sc),
            "second_peak": {"yaw_deg": float(th2n), "score": float(sc2), "T": to_T(th2n, iy2, ix2)},
            "n_target_cells": n_t, "cell": cell, "yaw_step_deg": yaw_step_deg,
            "yaw_curve": best_per_yaw}


def coarse_z(src_xyz_in_dst_xy: np.ndarray, dst_xyz: np.ndarray, xy_cell: float = 0.10, bin_z: float = 0.02,
             max_shift: float = 4.0) -> Dict:
    """Dịch tz sao cho histogram độ cao của nguồn (đã khớp xy) trùng với đích, chỉ xét nguồn nằm trên dấu chân xy của đích.
    Trả về {tz, score} (tz gồm cả phần chênh trung vị độ cao) với score = tương quan chuẩn hoá (cosine) của hai histogram."""
    lo = dst_xyz[:, :2].min(axis=0) - xy_cell
    shape = tuple(int(v) for v in np.ceil((dst_xyz[:, :2].max(axis=0) - lo) / xy_cell).astype(int)[::-1] + 3)
    foot = maximum_filter(raster(dst_xyz[:, :2], lo, shape, xy_cell), size=3)
    ij = np.floor((src_xyz_in_dst_xy[:, :2] - lo) / xy_cell).astype(np.int64)
    ok = (ij[:, 0] >= 0) & (ij[:, 0] < shape[1]) & (ij[:, 1] >= 0) & (ij[:, 1] < shape[0])
    sel = np.zeros(len(src_xyz_in_dst_xy), dtype=bool)
    sel[ok] = foot[ij[ok, 1], ij[ok, 0]] > 0
    s = src_xyz_in_dst_xy[sel, 2]
    d = dst_xyz[:, 2]
    if len(s) == 0:
        raise ValueError("không có điểm nguồn nào trên dấu chân xy của đích")
    offset = float(np.median(d) - np.median(s))      # đưa hai độ cao về cùng cỡ (Faro z ≈ 215 m, scene z ≈ 0) trước khi quét ±max_shift
    s = s + offset
    zlo = min(s.min(), d.min()) - max_shift - bin_z
    zhi = max(s.max(), d.max()) + max_shift + bin_z
    edges = np.arange(zlo, zhi + bin_z, bin_z)
    hs, _ = np.histogram(s, edges)
    hd, _ = np.histogram(d, edges)
    hs, hd = hs.astype(np.float64), hd.astype(np.float64)
    corr = fftconvolve(hd, hs[::-1], mode="full")                   # corr[k] ~ Σ hd[i] hs[i - (k - (n-1))]
    n = len(hs)
    shifts = (np.arange(len(corr)) - (n - 1)) * bin_z                # dịch nguồn thêm `shift` để khớp đích
    keep = np.abs(shifts) <= max_shift
    k = int(np.argmax(np.where(keep, corr, -np.inf)))
    score = float(corr[k] / (np.linalg.norm(hs) * np.linalg.norm(hd) + 1e-12))
    return {"tz": offset + float(shifts[k]), "score": score, "n_source_used": int(sel.sum()), "median_offset": offset}


# ---------------------------------------------------------------------------
# ICP point-to-plane (tự cài để biết rõ số vòng lặp và tiêu chí hội tụ)
# ---------------------------------------------------------------------------


def icp_point_to_plane(query: np.ndarray, ref: np.ndarray, ref_normals: np.ndarray, T0: np.ndarray, max_corr: float,
                       max_iter: int = 100, tol_fitness: float = 1e-6, tol_rmse: float = 1e-6, tree: Optional[cKDTree] = None,
                       fix_up: bool = False) -> Dict:
    """Căn `query` (mây điểm di chuyển) vào `ref` (có pháp tuyến) bằng ICP point-to-plane, scale cố định = 1.

    Trả về T (query → ref), `fitness` (tỉ lệ điểm query có tương ứng trong max_corr), `inlier_rmse` (khoảng cách điểm, m),
    `rmse_plane` (căn bậc hai trung bình bình phương khoảng cách tới mặt phẳng), `iterations`, `converged`.
    `converged` = đã dừng vì |Δfitness| < tol_fitness và |Δinlier_rmse| < tol_rmse (mặc định của Open3D) TRƯỚC khi hết `max_iter`.
    `fix_up=True` chỉ cho xoay quanh trục đứng (4 DoF); mặc định 6 DoF."""
    tree = tree or cKDTree(ref)
    T = np.array(T0, dtype=np.float64)
    prev_fit, prev_rmse = None, None
    converged, it = False, 0
    fit = rmse = rmse_plane = float("nan")
    for it in range(1, max_iter + 1):
        p = apply_T(T, query)
        d, idx = tree.query(p, k=1, distance_upper_bound=max_corr)
        ok = np.isfinite(d)
        n_ok = int(ok.sum())
        if n_ok < 6:
            return {"T": T, "fitness": 0.0, "inlier_rmse": float("nan"), "rmse_plane": float("nan"), "iterations": it,
                    "converged": False, "reason": f"chỉ {n_ok} tương ứng trong {max_corr} m"}
        pk, q, nrm = p[ok], ref[idx[ok]], ref_normals[idx[ok]]
        r = ((pk - q) * nrm).sum(axis=1)
        fit = n_ok / len(query)
        rmse = float(np.sqrt(np.mean(d[ok] ** 2)))
        rmse_plane = float(np.sqrt(np.mean(r ** 2)))
        if prev_fit is not None and abs(fit - prev_fit) < tol_fitness and abs(rmse - prev_rmse) < tol_rmse:
            converged = True
            break
        prev_fit, prev_rmse = fit, rmse
        jrot = np.cross(pk, nrm)
        if fix_up:
            jac = np.concatenate([jrot[:, 2:3], nrm], axis=1)               # [ωz, tx, ty, tz]
        else:
            jac = np.concatenate([jrot, nrm], axis=1)                       # [ωx, ωy, ωz, tx, ty, tz]
        a = jac.T @ jac + 1e-9 * np.eye(jac.shape[1])
        x = np.linalg.solve(a, -jac.T @ r)
        if fix_up:
            om, tt = np.array([0.0, 0.0, x[0]]), x[1:4]
        else:
            om, tt = x[:3], x[3:6]
        dT = make_T(rodrigues_small(om), tt)
        T = dT @ T
    return {"T": T, "fitness": float(fit), "inlier_rmse": rmse, "rmse_plane": rmse_plane, "iterations": it,
            "converged": converged, "reason": "dung sai" if converged else f"hết {max_iter} vòng lặp",
            "last_delta_fitness": None if prev_fit is None else float(abs(fit - prev_fit)),
            "last_delta_rmse": None if prev_rmse is None else float(abs(rmse - prev_rmse))}


# ---------------------------------------------------------------------------
# Thống kê residual (không phán xét)
# ---------------------------------------------------------------------------


def distance_stats(d: np.ndarray) -> Dict:
    d = np.asarray(d, dtype=np.float64)
    d = d[np.isfinite(d)]
    if len(d) == 0:
        return {"n": 0}
    q = np.percentile(d, [50, 90, 95, 99])
    return {"n": int(len(d)), "mean": float(d.mean()), "median": float(q[0]), "p90": float(q[1]), "p95": float(q[2]),
            "p99": float(q[3]), "max": float(d.max()), "frac_le_1cm": float((d <= 0.01).mean()),
            "frac_le_2cm": float((d <= 0.02).mean()), "frac_le_5cm": float((d <= 0.05).mean())}


def transform_difference(t_a: np.ndarray, t_b: np.ndarray, pts: Optional[np.ndarray] = None) -> Dict:
    """Chênh lệch giữa hai phép biến đổi: góc xoay (độ) của Rb·Raᵀ và độ dời hai tịnh tiến (m).

    CHÚ Ý: `translation_m` phụ thuộc gốc toạ độ (Faro có z ≈ 215 m nên xoay 0,26° quanh gốc cho ~1 m tịnh tiến) — không dùng để
    đánh giá độ ổn định. Truyền `pts` (điểm nguồn nằm trong phòng) để có `point_rms_m`, `point_p95_m`, `point_max_m`: độ dời
    của chính các điểm đó khi áp hai phép biến đổi."""
    dr = t_b[:3, :3] @ t_a[:3, :3].T
    out = {"rotation_deg": rotation_angle_deg(dr), "translation_m": float(np.linalg.norm(t_b[:3, 3] - t_a[:3, 3]))}
    if pts is not None and len(pts):
        disp = np.linalg.norm(apply_T(t_a, pts) - apply_T(t_b, pts), axis=1)
        out.update(point_rms_m=float(np.sqrt(np.mean(disp ** 2))), point_p95_m=float(np.percentile(disp, 95)),
                   point_max_m=float(disp.max()), n_points=int(len(pts)))
    return out
