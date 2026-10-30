"""Baseline B1: VGGT thuần, ra mét (kế hoạch §4.4 "B1", Q13; ĐC §20 Hình 26). Không dùng COLMAP.

1. Nối chunk: chunk k+1 → chunk k bằng Sim(3) (Umeyama (13)–(17), cắt tỉa lặp) trên điểm 3D của cùng pixel ở các ảnh gối (`vggt.overlap`),
   rồi nhân dồn về hệ chunk 0. ĐC không nêu cách nối chunk cho B1 [Suy luận].
2. Scale mét: đầu mút mốc (`observations_2d` trong `scale_anchor.json`, click 2D) được tam giác hoá (DLT) bằng camera VGGT đã nối chunk;
   `s = L_real / L_vggt` (4). Mốc không đổi, chỉ đổi hệ đo (không dùng s_m của COLMAP) [Suy luận, người dùng duyệt].
Ra: `baselines/vggt/metric/{points_metric.ply, cameras_metric.json, b1_result.json}`.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Tuple

import numpy as np

from ..alignment.anchor import normalize_obs, triangulate_dlt
from ..common import config as cfgmod
from ..common.errors import E_MISSING_INPUT, StageError
from ..common.geometry import apply_sim3, camera_center, umeyama_sim3
from ..common.io import SceneLayout, ensure_dir, read_json, write_json
from ..common.ply import write_ply
from ..common.schema import read_keyframes_csv
from ..vggt.infer import original_to_vggt, pad_geometry, read_chunk


def fit_sim3_trimmed(src: np.ndarray, dst: np.ndarray, iters: int = 3, k: float = 3.0) -> Tuple[float, np.ndarray, np.ndarray, Dict]:
    """Umeyama (13)–(17) rồi lặp: bỏ điểm có sai số > k·median, căn lại. Trả về (s, R, t, {n_used, rmse, median})."""
    keep = np.ones(len(src), dtype=bool)
    for _ in range(iters + 1):
        s, r, t = umeyama_sim3(src[keep], dst[keep])
        res = np.linalg.norm(apply_sim3(s, r, t, src) - dst, axis=1)
        new = res <= k * max(float(np.median(res[keep])), 1e-12)
        if new.sum() < 10 or np.array_equal(new, keep):
            break
        keep = new
    return s, r, t, {"n_used": int(keep.sum()), "rmse": float(np.sqrt(np.mean(res[keep] ** 2))), "median": float(np.median(res[keep]))}


def compose(a: Tuple[float, np.ndarray, np.ndarray], b: Tuple[float, np.ndarray, np.ndarray]) -> Tuple[float, np.ndarray, np.ndarray]:
    """a ∘ b: x → a(b(x)) với a, b = (s, R, t)."""
    return a[0] * b[0], a[1] @ b[1], a[0] * a[1] @ b[2] + a[2]


def _grid(geo: Dict, stride: int) -> Tuple[np.ndarray, np.ndarray]:
    """Chỉ số hàng, cột của lưới lấy mẫu trong vùng ảnh thật (bỏ phần pad) của ảnh VGGT."""
    return (np.arange(geo["pad_top"], geo["pad_top"] + geo["new_h"], stride), np.arange(geo["pad_left"], geo["pad_left"] + geo["new_w"], stride))


def _home_chunk(views_by_chunk: List[List[int]]) -> Dict[int, int]:
    """view → chunk mà view nằm xa biên hơn (cùng quy tắc như fusion) [Suy luận]; hoà thì chunk nhỏ."""
    best: Dict[int, Tuple[int, int]] = {}
    for k, views in enumerate(views_by_chunk):
        for i, v in enumerate(views):
            score = min(i, len(views) - 1 - i)
            if v not in best or score > best[v][0]:
                best[v] = (score, k)
    return {v: k for v, (_, k) in best.items()}


def build_b1(layout: SceneLayout, cfg: Dict, log: Callable[[str], None] = print) -> Dict:
    """Dựng B1. Cần `baselines/vggt/chunk_XX/{vggt_raw,vggt_out}.npz`, `metadata/keyframes.csv`, `ground_truth/scale_anchor.json` (có `observations_2d`)."""
    t0 = time.time()
    stride, c_min = int(cfgmod.require(cfg, "eval.b1.stride")), float(cfgmod.require(cfg, "eval.b1.c_min"))
    cks = sorted(p for p in layout.vggt.glob("chunk_*") if (p / "vggt_raw.npz").is_file() and (p / "vggt_out.npz").is_file())
    anchor_path = layout.root / str(cfgmod.require(cfg, "align.anchor_file"))
    for p in ([layout.metadata / "keyframes.csv", anchor_path] if cks else [layout.vggt / "chunk_XX"]):
        if not p.exists():
            raise StageError(E_MISSING_INPUT, f"B1 thiếu {p}: chạy stage vggt/keyframe trước")
    anchor = read_json(anchor_path)
    if "observations_2d" not in anchor:
        raise StageError(E_MISSING_INPUT, f"{anchor_path} không có observations_2d (click 2D của mốc): B1 cần để đo mốc trong hệ VGGT")
    kf = read_keyframes_csv(layout.metadata / "keyframes.csv")
    geo = pad_geometry(int(kf[0]["w"]), int(kf[0]["h"]))
    rows, cols = _grid(geo, stride)
    metas = [read_json(p / "chunk_meta.json") for p in cks]
    views_by_chunk = [[int(v) for v in m["views"]] for m in metas]
    home = _home_chunk(views_by_chunk)

    tf: List[Tuple[float, np.ndarray, np.ndarray]] = []     # chunk k → hệ chunk 0
    cam: Dict[int, Dict] = {}                               # view → K, R, t (cục bộ), chunk
    links, pts_out = [], []
    prev = None                                             # (views, points, conf) của chunk trước, đã lấy mẫu
    for k in range(len(cks)):
        raw, out, _ = read_chunk(layout, k)
        pts = out["points"][:, rows][:, :, cols]
        cf = out["c_model"][:, rows][:, :, cols]
        views = views_by_chunk[k]
        if k == 0:
            tf.append((1.0, np.eye(3), np.zeros(3)))
        else:
            shared = [v for v in views if v in prev[0]]
            if not shared:
                raise StageError(E_MISSING_INPUT, f"chunk {k - 1} và {k} không có ảnh gối")
            src, dst = [], []
            for v in shared:
                a, b = pts[views.index(v)], prev[1][prev[0].index(v)]
                ok = (cf[views.index(v)] >= c_min) & (prev[2][prev[0].index(v)] >= c_min) & np.isfinite(a).all(-1) & np.isfinite(b).all(-1)
                src.append(a[ok])
                dst.append(b[ok])
            src, dst = np.concatenate(src), np.concatenate(dst)
            if len(src) < 100:
                raise StageError(E_MISSING_INPUT, f"chunk {k - 1}→{k}: chỉ {len(src)} cặp điểm ở ảnh gối (c_model ≥ {c_min}); không nối được")
            s, r, t, info = fit_sim3_trimmed(src, dst)
            tf.append(compose(tf[k - 1], (s, r, t)))
            links.append({"from_chunk": k, "to_chunk": k - 1, "shared_views": shared, "n_pairs": int(len(src)), "s": s, **info})
            log(f"[b1] nối chunk {k}→{k - 1}: {len(src):,} cặp, {info['n_used']:,} dùng, s {s:.4f}, rmse {info['rmse']:.4f} đv VGGT")
        for i, v in enumerate(views):
            if home[v] != k:
                continue
            cam[v] = {"K": raw["intrinsic"][i].astype(np.float64), "R": raw["extrinsic"][i][:, :3].astype(np.float64),
                      "t": raw["extrinsic"][i][:, 3].astype(np.float64), "chunk": k}
            sel = (cf[i] >= c_min) & np.isfinite(pts[i]).all(-1)
            pts_out.append(apply_sim3(*tf[k], pts[i][sel]))
        prev = (views, pts, cf)

    # Scale mét từ mốc: tam giác hoá từng đầu mút bằng camera VGGT trong hệ chunk 0
    def proj(v: int) -> np.ndarray:
        c = cam[v]
        s, rg, tg = tf[c["chunk"]]
        a = c["R"] @ rg.T / s
        return c["K"] @ np.hstack([a, (c["t"] - a @ tg).reshape(3, 1)])

    obs = normalize_obs(anchor["observations_2d"])
    ends, reproj = {}, {}
    for key in ("a", "b"):
        o = [x for x in obs if x["endpoint"] == key and x["view"] in cam]
        if len(o) < 2:
            raise StageError(E_MISSING_INPUT, f"đầu mút {key} của mốc chỉ có {len(o)} quan sát trên view có camera VGGT (cần ≥ 2)")
        ps = [proj(x["view"]) for x in o]
        uv = [original_to_vggt(x["uv"], geo)[0] for x in o]
        ends[key] = triangulate_dlt(ps, uv)
        x_h = np.append(ends[key], 1.0)
        reproj[key] = [float(np.linalg.norm((p @ x_h)[:2] / (p @ x_h)[2] - u)) for p, u in zip(ps, uv)]
    l_vggt = float(np.linalg.norm(ends["b"] - ends["a"]))
    s_b1 = float(anchor["L_real"]) / l_vggt

    pts_all = np.concatenate(pts_out) * s_b1
    centers = {str(v): (s_b1 * apply_sim3(*tf[c["chunk"]], camera_center(c["R"], c["t"])[None])[0]).tolist() for v, c in sorted(cam.items())}
    out_dir = ensure_dir(layout.vggt_metric)
    write_ply(out_dir / "points_metric.ply", {"x": pts_all[:, 0].astype(np.float32), "y": pts_all[:, 1].astype(np.float32), "z": pts_all[:, 2].astype(np.float32)})
    stats = {"n_chunks": len(cks), "n_points": int(len(pts_all)), "stride": stride, "c_min": c_min, "L_real": float(anchor["L_real"]), "L_vggt": l_vggt,
             "s_b1_m_per_vggt_unit": s_b1, "anchor_id": anchor.get("id"), "anchor_reproj_px": reproj, "links": links, "seconds": round(time.time() - t0, 1)}
    write_json(out_dir / "cameras_metric.json", {"unit": "m", "frame": "chunk 0 × s_b1", "centers": centers})
    write_json(out_dir / "b1_result.json", stats)
    log(f"[b1] {len(pts_all):,} điểm; mốc {stats['anchor_id']}: L_real {stats['L_real']} m, L_vggt {l_vggt:.4f} đv → s = {s_b1:.4f} m/đv; "
        f"sai số chiếu lại mốc lớn nhất {max(max(v) for v in reproj.values()):.2f} px; {stats['seconds']} s")
    return stats
