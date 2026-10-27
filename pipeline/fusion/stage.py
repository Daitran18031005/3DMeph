"""Stage `fuse` (ĐC §16, kế hoạch §4.5, M1d): ghép dự đoán VGGT theo trọng số sáu tín hiệu cho từng điểm MVS.

Điểm `k` là điểm của `stereo_fusion` (`fused.ply`), `V_k` đọc từ `fused.ply.vis`. Với mỗi view i trong V_k: chiếu `k` vào ảnh bằng camera COLMAP, lấy mẫu song tuyến
bản đồ điểm VGGT tại pixel tương ứng (qua `pad_geometry`), đổi sang mét bằng Sim(3) của chunk và `s_m` (18); lấy sáu tín hiệu tại (i, k) rồi ghép theo (19), (22).
COLMAP chỉ cung cấp điểm, tập view và các tín hiệu; VGGT là "người bỏ phiếu" cho vị trí. Mọi vị trí ra ở MÉT (hệ COLMAP × s_m).
"""

from __future__ import annotations

import struct
import time
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import numpy as np

from ..alignment.stage import load_colmap_cameras
from ..common import config as cfgmod
from ..common.errors import E_MISSING_INPUT, StageError
from ..common.io import SceneLayout, ensure_dir, read_json, write_json
from ..common.ply import write_ply
from ..common.quality import window_gradient_mean
from ..common.schema import read_keyframes_csv
from ..vggt.infer import original_to_vggt, pad_geometry
from .fusion import fuse, gate_weight, weights_from_signals


def read_vis(path) -> Tuple[np.ndarray, np.ndarray]:
    """`fused.ply.vis` của COLMAP: uint64 số điểm, rồi mỗi điểm: uint32 số view m và m × uint32 chỉ số ảnh. Trả về (counts (K,), flat (Σm,))."""
    raw = open(path, "rb").read()
    n = struct.unpack_from("<Q", raw, 0)[0]
    pos, counts, parts = 8, np.empty(n, dtype=np.int64), []
    for k in range(n):
        c = struct.unpack_from("<I", raw, pos)[0]
        pos += 4
        counts[k] = c
        parts.append(np.frombuffer(raw, dtype="<u4", count=c, offset=pos))
        pos += 4 * c
    if pos != len(raw):
        raise ValueError(f"{path}: còn {len(raw) - pos} byte thừa sau {n} điểm")
    return counts, (np.concatenate(parts).astype(np.int64) if parts else np.empty(0, dtype=np.int64))


def read_fusion_image_names(mvs_dir: Path) -> List[str]:
    """Thứ tự ảnh mà `fused.ply.vis` dùng để đánh chỉ số: `stereo/fusion.cfg` (mỗi dòng một tên ảnh)."""
    cfg = Path(mvs_dir) / "stereo" / "fusion.cfg"
    if not cfg.is_file():
        raise StageError(E_MISSING_INPUT, f"thiếu {cfg}: chạy stage mvs trước")
    return [ln.strip() for ln in cfg.read_text(encoding="utf-8").splitlines() if ln.strip()]


def sample_bilinear(arr: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """Lấy mẫu song tuyến mảng (H, W) hoặc (H, W, C) tại toạ độ liên tục uv (n, 2) (tâm pixel ở nửa số nguyên); kẹp vào biên."""
    h, w = arr.shape[:2]
    x = np.clip(uv[:, 0] - 0.5, 0, w - 1)
    y = np.clip(uv[:, 1] - 0.5, 0, h - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
    fx, fy = x - x0, y - y0
    if arr.ndim == 3:
        fx, fy = fx[:, None], fy[:, None]
    return (arr[y0, x0] * (1 - fx) * (1 - fy) + arr[y0, x1] * fx * (1 - fy) + arr[y1, x0] * (1 - fx) * fy + arr[y1, x1] * fx * fy)


def view_to_chunk(chunks: List[Dict]) -> Dict[int, Tuple[int, int]]:
    """view → (chunk, chỉ số trong chunk). View nằm trong hai chunk (ảnh gối) thì chọn chunk mà view ở xa biên hơn [Suy luận, kế hoạch §4.5]."""
    best: Dict[int, Tuple[int, int, int]] = {}
    for c in chunks:
        views = c["views"]
        for j, v in enumerate(views):
            margin = min(j, len(views) - 1 - j)
            if v not in best or margin > best[v][2]:
                best[v] = (c["chunk"], j, margin)
    return {v: (k, j) for v, (k, j, _) in best.items()}


def load_accepted_chunks(layout: SceneLayout) -> List[Dict]:
    """Các chunk được nhận ở stage align: {chunk, views, s, R, t}."""
    out = []
    for p in sorted(layout.alignment.glob("chunk_*_sim3.json")):
        r = read_json(p)
        if r.get("accepted"):
            out.append({"chunk": int(r["chunk"]), "views": [int(v) for v in r["views"]], "s": float(r["s"]), "R": np.array(r["R"]), "t": np.array(r["t"])})
    if not out:
        raise StageError(E_MISSING_INPUT, f"không có chunk_XX_sim3.json nào được nhận trong {layout.alignment}: chạy stage align trước")
    return out


def sample_pairs(layout: SceneLayout, xyz_colmap: np.ndarray, kk: np.ndarray, view: np.ndarray, cams: Dict[int, Dict], chunks: List[Dict],
                 s_m: float, geo: Dict, e_cap: float, g_ref: float, log: Callable[[str], None]) -> Dict[str, np.ndarray]:
    """Lấy tín hiệu cho từng cặp (i, k) (mảng phẳng theo cặp). Cặp không lấy được (view không đăng ký/chunk bị loại/chiếu ngoài ảnh) có `valid = False`."""
    import cv2

    from ..vggt.infer import read_chunk

    n = len(kk)
    out = {"valid": np.zeros(n, bool), "P": np.full((n, 3), np.nan), "c_model": np.full(n, np.nan), "e_reproj": np.full(n, np.nan),
           "sigma_m": np.full(n, np.nan), "q_texture": np.full(n, np.nan), "uv": np.full((n, 2), np.nan)}
    v2c = view_to_chunk(chunks)
    by_chunk = {c["chunk"]: c for c in chunks}
    cache: Dict[int, Tuple[np.ndarray, np.ndarray]] = {}
    e_dir, s_dir = layout.colmap_sfm / "e_reproj_map", layout.colmap_mvs / "sigma_depth"
    stat = {"no_cam": 0, "no_chunk": 0, "outside": 0, "sigma_nan": 0, "e_missing_views": 0}
    for v in sorted(set(view.tolist())):
        sel = np.nonzero(view == v)[0]
        if v not in cams:
            stat["no_cam"] += len(sel)
            continue
        if v not in v2c:
            stat["no_chunk"] += len(sel)
            continue
        c = cams[v]
        xc = xyz_colmap[kk[sel]] @ c["R"].T + c["t"]
        z = xc[:, 2]
        pix = xc @ c["K"].T
        uv = pix[:, :2] / np.where(z > 1e-9, z, 1.0)[:, None]
        h, w = geo["orig_h"], geo["orig_w"]
        ok = (z > 1e-9) & (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
        stat["outside"] += int((~ok).sum())
        sel, uv = sel[ok], uv[ok]
        if len(sel) == 0:
            continue
        k_chunk, j = v2c[v]
        if k_chunk not in cache:
            cache.clear()
            _, vout, _ = read_chunk(layout, k_chunk)
            cache[k_chunk] = (vout["points"], vout["c_model"])
        pts_map, c_map = cache[k_chunk]
        uvv = original_to_vggt(uv, geo)
        ch = by_chunk[k_chunk]
        p_vggt = sample_bilinear(pts_map[j], uvv)
        out["P"][sel] = s_m * (ch["s"] * p_vggt @ ch["R"].T + ch["t"])
        out["c_model"][sel] = np.clip(sample_bilinear(c_map[j], uvv), 0.0, 1.0)
        e_path = e_dir / f"{v:04d}.npy"
        if e_path.is_file():
            e_map = np.load(e_path)
            out["e_reproj"][sel] = e_map[np.clip(uv[:, 1].astype(int), 0, h - 1), np.clip(uv[:, 0].astype(int), 0, w - 1)]
        else:
            stat["e_missing_views"] += 1
            out["e_reproj"][sel] = e_cap
        s_path = s_dir / f"{v:04d}.npy"
        sig = np.load(s_path)[np.clip(uv[:, 1].astype(int), 0, h - 1), np.clip(uv[:, 0].astype(int), 0, w - 1)] if s_path.is_file() else np.full(len(sel), np.nan)
        stat["sigma_nan"] += int(np.isnan(sig).sum())
        out["sigma_m"][sel] = sig * s_m
        gray = cv2.imread(str(layout.keyframes / f"{v:04d}.jpg"), cv2.IMREAD_GRAYSCALE)
        grad = window_gradient_mean(gray, uv)
        out["q_texture"][sel] = np.clip(grad / g_ref, 0.0, 1.0)
        out["uv"][sel] = uv
        out["valid"][sel] = True
    out["_stat"] = stat
    log(f"[fuse] cặp (i, k): {n:,}; lấy được {int(out['valid'].sum()):,}; bỏ: {stat['no_cam']:,} view chưa đăng ký, {stat['no_chunk']:,} view không thuộc chunk nào được nhận, "
        f"{stat['outside']:,} chiếu ngoài ảnh; σ_depth không có (NaN) tại {stat['sigma_nan']:,} cặp")
    return out


def pad_pairs(counts: np.ndarray, values: np.ndarray, fill=0.0) -> np.ndarray:
    """Mảng phẳng theo cặp (Σm, ...) → (K, Vmax, ...) theo từng điểm."""
    vmax = int(counts.max())
    k = len(counts)
    offsets = np.concatenate([[0], np.cumsum(counts)[:-1]])
    pos = np.arange(counts.sum()) - np.repeat(offsets, counts)
    row = np.repeat(np.arange(k), counts)
    out = np.full((k, vmax) + values.shape[1:], fill, dtype=values.dtype)
    out[row, pos] = values
    return out


def run_fuse(layout: SceneLayout, cfg: Dict, log: Callable[[str], None] = print,
             load_cameras: Callable[[SceneLayout], Dict[int, Dict]] = load_colmap_cameras) -> Dict:
    """Stage `fuse`. Vào: `baselines/colmap/{sfm,mvs}`, `baselines/vggt/chunk_XX`, `proposed/alignment/`, `metadata/keyframes.csv`.
    Ra: `proposed/fusion/fused_points.ply` (x, y, z, w_k, n_views; mét) và `fusion_log.npz` (theo cặp (i, k))."""
    t0 = time.time()
    tau_e, tau_s = float(cfgmod.require(cfg, "fusion.tau_e")), float(cfgmod.require(cfg, "fusion.tau_sigma"))
    e_cap, use_q = float(cfgmod.require(cfg, "fusion.e_cap_px")), bool(cfgmod.require(cfg, "fusion.use_quality"))
    g_ref = float(cfgmod.require(cfg, "quality.g_ref.vga"))
    scale_path = layout.alignment / "scale.json"
    mvs = layout.colmap_mvs
    for p in (scale_path, mvs / "fused.ply", mvs / "fused.ply.vis"):
        if not p.is_file():
            raise StageError(E_MISSING_INPUT, f"thiếu {p}: chạy stage trước đó (align, mvs)")
    s_m = float(read_json(scale_path)["s_m"])
    chunks = load_accepted_chunks(layout)
    cams = load_cameras(layout)
    kf = read_keyframes_csv(layout.metadata / "keyframes.csv")
    geo = pad_geometry(int(kf[0]["w"]), int(kf[0]["h"]))
    ply = read_ply_xyz(mvs / "fused.ply")
    counts, flat = read_vis(mvs / "fused.ply.vis")
    if len(counts) != len(ply):
        raise StageError(E_MISSING_INPUT, f"fused.ply có {len(ply)} điểm nhưng fused.ply.vis có {len(counts)}")
    names = read_fusion_image_names(mvs)
    idx_to_view = np.array([int(n.split(".")[0]) for n in names])
    kk = np.repeat(np.arange(len(counts)), counts)
    view = idx_to_view[flat]
    log(f"[fuse] {len(counts):,} điểm MVS, {counts.sum():,} cặp (i, k), {np.median(counts):.0f} view/điểm (trung vị), s_m = {s_m:.4f}, {len(chunks)} chunk được nhận")

    pr = sample_pairs(layout, ply, kk, view, cams, chunks, s_m, geo, e_cap, g_ref, log)
    stat = pr.pop("_stat")
    valid = pr["valid"]
    q_blur_v = {int(r["view_id"]): float(r["q_blur"]) for r in kf}
    q_exp_v = {int(r["view_id"]): float(r["q_exposure"]) for r in kf}
    q_blur = np.array([q_blur_v.get(int(v), np.nan) for v in view])
    q_exp = np.array([q_exp_v.get(int(v), np.nan) for v in view])
    sigma = np.where(np.isnan(pr["sigma_m"]), np.inf, pr["sigma_m"])          # không có σ_depth: coi là rất xấu (f = 0) [Suy luận, xem README]
    ok = valid
    w = np.zeros(len(kk))
    w[ok] = weights_from_signals(pr["c_model"][ok], pr["e_reproj"][ok], sigma[ok], q_blur[ok], pr["q_texture"][ok], q_exp[ok], tau_e, tau_s, use_q)

    n_valid_pt = np.bincount(kk[ok], minlength=len(counts))
    keep = n_valid_pt > 0
    log(f"[fuse] điểm có ít nhất 1 view lấy được: {int(keep.sum()):,}/{len(counts):,} (bỏ {int((~keep).sum()):,})")
    p_pad, w_pad, m_pad = pad_pairs(counts, np.nan_to_num(pr["P"]), 0.0), pad_pairs(counts, w), pad_pairs(counts, ok.astype(bool), False)
    p_hat, w_tilde = fuse(p_pad, w_pad, m_pad)
    w_k = gate_weight(w_pad, w_tilde)
    p_hat, w_k, n_views = p_hat[keep], w_k[keep], n_valid_pt[keep]

    out_dir = ensure_dir(layout.fusion)
    write_ply(out_dir / "fused_points.ply", {"x": p_hat[:, 0].astype(np.float32), "y": p_hat[:, 1].astype(np.float32), "z": p_hat[:, 2].astype(np.float32),
                                              "w_k": w_k.astype(np.float32), "n_views": n_views.astype(np.uint8)})
    wt_flat = w_tilde[pad_pairs(counts, np.ones(len(kk), bool), False)]                           # w̃ theo cặp, cùng thứ tự với kk
    np.savez_compressed(out_dir / "fusion_log.npz", view=view[ok].astype(np.int16), point=kk[ok].astype(np.int32), c_model=pr["c_model"][ok].astype(np.float32),
                        e_reproj=pr["e_reproj"][ok].astype(np.float32), sigma_m=pr["sigma_m"][ok].astype(np.float32), q_blur=q_blur[ok].astype(np.float32),
                        q_texture=pr["q_texture"][ok].astype(np.float32), q_exposure=q_exp[ok].astype(np.float32), w=w[ok].astype(np.float32),
                        w_tilde=wt_flat[ok].astype(np.float32))
    x_m = ply[keep] * s_m
    dev_pair = np.linalg.norm(pr["P"][ok] - (ply[kk[ok]] * s_m), axis=1)
    dev_fused = np.linalg.norm(p_hat - x_m, axis=1)
    pc = lambda a, q: float(np.percentile(a, q))  # noqa: E731
    stats = {"n_points_mvs": int(len(counts)), "n_points_fused": int(keep.sum()), "n_pairs": int(len(kk)), "n_pairs_valid": int(ok.sum()),
             "pairs_dropped": {k: int(v) for k, v in stat.items()}, "s_m": s_m, "use_quality": use_q,
             "w_k_percentiles": {q: round(pc(w_k, q), 4) for q in (5, 25, 50, 75, 95)}, "w_k_mean": float(w_k.mean()),
             "frac_w_k_above_tau_w": float((w_k > float(cfgmod.get(cfg, "plane.tau_w"))).mean()),
             "signal_medians": {k: round(float(np.nanmedian(pr[k][ok])), 4) for k in ("c_model", "e_reproj", "sigma_m", "q_texture")},
             "sigma_nan_fraction": float(np.isnan(pr["sigma_m"][ok]).mean()),
             "vggt_vs_colmap_pair_cm": {"median": round(pc(dev_pair, 50) * 100, 2), "p90": round(pc(dev_pair, 90) * 100, 2)},
             "fused_vs_colmap_cm": {"median": round(pc(dev_fused, 50) * 100, 2), "p90": round(pc(dev_fused, 90) * 100, 2)},
             "seconds": round(time.time() - t0, 1)}
    write_json(out_dir / "fusion_result.json", stats)
    log(f"[fuse] xong {stats['n_points_fused']:,} điểm trong {stats['seconds']} s; w_k trung vị {stats['w_k_percentiles'][50]}, {stats['frac_w_k_above_tau_w'] * 100:.1f}% điểm có w_k > τ_w; "
        f"lệch VGGT so với COLMAP theo cặp: trung vị {stats['vggt_vs_colmap_pair_cm']['median']} cm, p90 {stats['vggt_vs_colmap_pair_cm']['p90']} cm")
    return stats


def read_ply_xyz(path) -> np.ndarray:
    """xyz (K, 3) float64 của `fused.ply` (PLY của COLMAP, nhị phân: dùng Open3D cho ổn định)."""
    import open3d as o3d
    return np.asarray(o3d.io.read_point_cloud(str(path)).points, dtype=np.float64)


__all__ = ["read_vis", "read_fusion_image_names", "sample_bilinear", "view_to_chunk", "load_accepted_chunks", "sample_pairs", "pad_pairs", "run_fuse"]
