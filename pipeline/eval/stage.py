"""Stage `eval` (ĐC §20, kế hoạch §4.8, M3): chấm các biến thể B0, B1, B3, proposed, abl_quality trên một scene, ghi `evaluation/metrics.csv`.

Vào: `ground_truth/measurements.csv` (+ `faro/faro_scene_frame.ply`), `raw/source.json` (→ `lowres_wide.traj`), `metadata/keyframes.csv`, đầu ra các biến thể
(`variants.cloud_path`), tuỳ chọn `evaluation/logs/endpoints_<variant>.json` (chế độ manual; thiếu thì truyền từ `endpoints_proposed.json`).
Ra: `evaluation/metrics.csv` (một dòng mỗi biến thể), `evaluation/logs/{lengths_<v>_<mode>.csv, align_<v>.json}`, `baselines/vggt/metric/` (B1).

Pose GT (`.traj`) chỉ dùng ở đây để ĐỊNH VỊ (phép cứng scale = 1); không đi vào bất kỳ stage dựng mô hình nào (ĐC §8.1).
Chỉ số hình học (Chamfer/F) báo cả sau Kabsch và sau ICP cứng scale = 1. Plane metrics và Ablation 2 chuyển sang Replica (M5), không ở đây.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import numpy as np

from ..alignment.stage import load_colmap_cameras
from ..common import config as cfgmod
from ..common.adapters import Trajectory
from ..common.errors import E_MISSING_INPUT, StageError
from ..common.io import SceneLayout, ensure_dir, read_json, write_json
from ..common.schema import read_keyframes_csv
from . import geometry as geo
from . import lengths as ln
from .b1 import build_b1
from .metrics import ate_after_sim3, delta_percent
from .variants import VARIANTS, base_layout, camera_centers, cloud_path

MAX_POSE_GAP_S = 0.5     # không nội suy pose GT qua khoảng trống pose lớn hơn thế [Suy luận]

COLUMNS = ["variant", "length_mode", "n_segments", "n_valid", "mae_cm", "median_cm", "mape_pct", "pct_lt5cm",
           "n_common", "mae_cm_common", "median_cm_common", "mape_pct_common", "pct_lt5cm_common", "delta_pct_mae_vs_B0", "delta_pct_median_vs_B0",
           "ate_rigid_cm", "ate_rigid_all_cm", "ate_sim3_cm", "n_cameras", "n_cameras_dropped", "n_unsnapped_endpoints", "snap_mean_cm", "nn_median_cm",
           "acc_cm", "comp_cm", "chamfer_cm", "precision", "recall", "f_score", "acc_cm_kabsch", "comp_cm_kabsch", "chamfer_cm_kabsch", "f_score_kabsch"]


def gt_camera_centers(layout: SceneLayout) -> Dict[int, np.ndarray]:
    """view_id → tâm camera GT (hệ scene, mét) tại `frame_ts` của keyframe, từ `lowres_wide.traj` (nội suy). View ngoài quỹ đạo hoặc nằm trong khoảng trống pose bị bỏ."""
    src = layout.raw / "source.json"
    if not src.is_file():
        raise StageError(E_MISSING_INPUT, f"thiếu {src}: chạy stage keyframe trước")
    traj_path = Path(read_json(src)["raw_dir"]) / "lowres_wide.traj"
    if not traj_path.is_file():
        raise StageError(E_MISSING_INPUT, f"thiếu {traj_path}")
    traj = Trajectory.from_file(traj_path)
    out: Dict[int, np.ndarray] = {}
    for r in read_keyframes_csv(layout.metadata / "keyframes.csv"):
        try:
            out[int(r["view_id"])] = traj.pose_wc(float(r["frame_ts"]), True, MAX_POSE_GAP_S)[:3, 3]
        except ValueError:
            continue
    return out


def _fmt(v):
    return "" if v is None else (f"{v:.6g}" if isinstance(v, float) else v)


def _eval_variant(name: str, layout: SceneLayout, cfg: Dict, segs: List[Dict], gt_cams: Dict[int, np.ndarray], faro: Optional[np.ndarray],
                  load_cameras: Callable, log: Callable[[str], None]) -> Dict:
    snap, mode = float(cfgmod.require(cfg, "eval.snap_radius_m")), str(cfgmod.require(cfg, "eval.mode"))
    cloud = geo.load_points(cloud_path(layout, name))
    cams = camera_centers(layout, name, load_cameras)
    views = sorted(set(cams) & set(gt_cams))
    if len(views) < 3:
        raise StageError(E_MISSING_INPUT, f"{name}: chỉ {len(views)} view có cả tâm camera mô hình và GT (cần ≥ 3)")
    c_mod, c_gt = np.array([cams[v] for v in views]), np.array([gt_cams[v] for v in views])
    trim_k, trim_iters = float(cfgmod.require(cfg, "eval.align.trim_k")), int(cfgmod.require(cfg, "eval.align.trim_max_iters"))
    r, t, rms, keep = ln.kabsch_rigid_trimmed(c_gt, c_mod, trim_k, trim_iters)   # mô hình = R·GT + t, scale cố định 1; lặp bỏ camera residual > trim_k × trung vị
    err_all = np.linalg.norm(c_gt @ r.T + t - c_mod, axis=1)         # residual của MỌI camera dưới phép căn bền (camera bị loại vẫn được báo)
    n_drop = int((~keep).sum())
    auto = ln.measure_auto(segs, r, t, cloud, snap)
    ep_path, src_path = layout.logs / f"endpoints_{name}.json", layout.logs / "endpoints_proposed.json"
    export_json = layout.export / "measurements.json"
    model_frame = read_json(export_json).get("frame") if export_json.is_file() else None
    rows, label = auto, "auto"
    if mode == "manual" and ep_path.is_file():              # chấm trực tiếp trên point cloud của biến thể này
        rows, label = ln.measure_manual(segs, ln.read_endpoints_json(ep_path, None, None if name == "B1" else model_frame)), "manual"
    elif mode == "manual" and name != "proposed" and src_path.is_file():   # truyền cặp điểm chấm trên proposed (PLAN §4.8 mục 3)
        eps = ln.read_endpoints_json(src_path, None, model_frame)          # hệ COLMAP × s_m
        r_t, t_t = np.eye(3), np.zeros(3)
        if name == "B1":                                                   # B1 ở hệ chuỗi VGGT: phép cứng scale = 1 theo tâm camera chung
            c_cm = camera_centers(layout, "proposed", load_cameras)
            common = sorted(set(c_cm) & set(cams))
            if len(common) < 3:
                raise StageError(E_MISSING_INPUT, f"B1: chỉ {len(common)} view chung với COLMAP để truyền đầu mút (cần ≥ 3)")
            r_t, t_t, _, _ = ln.kabsch_rigid_trimmed(np.array([c_cm[v] for v in common]), np.array([cams[v] for v in common]), trim_k, trim_iters)
        rows, label = ln.measure_transfer(segs, eps, r_t, t_t, cloud, snap), "manual_transfer"
    ln.write_lengths_csv(layout.logs / f"lengths_{name}_auto.csv", auto)
    if label != "auto":
        ln.write_lengths_csv(layout.logs / f"lengths_{name}_{label}.csv", rows)
    ate_sim3 = ate_after_sim3(c_mod[keep], c_gt[keep])
    res = {"variant": name, "length_mode": label, "rows": rows, "n_segments": len(segs), "ate_rigid_cm": rms * 100.0, "ate_rigid_all_cm": float(np.sqrt(np.mean(err_all ** 2))) * 100.0, "ate_sim3_cm": ate_sim3 * 100.0,
           "n_cameras": len(views), "n_cameras_dropped": n_drop}
    snap_info = ln.snap_summary(auto)
    res.update(n_unsnapped_endpoints=snap_info["n_unsnapped"], snap_mean_cm=snap_info["snap_mean_cm"], nn_median_cm=snap_info["nn_median_cm"])
    info = {"variant": name, "length_mode": label, "cloud": str(cloud_path(layout, name)), "n_points": int(len(cloud)), "n_cameras": len(views),
            "kabsch_rms_cm": rms * 100.0, "kabsch_max_cm": float(err_all.max() * 100.0), "ate_sim3_cm": ate_sim3 * 100.0,
            "trim_k": trim_k, "n_cameras_dropped": n_drop, "dropped_views": [int(views[i]) for i in np.nonzero(~keep)[0]], "ate_rigid_all_cm": res["ate_rigid_all_cm"],
            "R_gt_to_model": r.tolist(), "t_gt_to_model": t.tolist(), "snap_radius_m": snap, "snap_auto": snap_info}
    if faro is not None:
        model_scene = (cloud - t) @ r                   # Rᵀ(p − t): mô hình → hệ scene
        pad = float(cfgmod.require(cfg, "eval.crop_margin_m"))
        allc = np.array(list(gt_cams.values()))
        g = geo.evaluate_geometry(model_scene, faro, (allc.min(axis=0) - pad, allc.max(axis=0) + pad), float(cfgmod.require(cfg, "eval.voxel_m")),
                                  float(cfgmod.require(cfg, "eval.delta_m")), float(cfgmod.require(cfg, "eval.icp_max_dist_m")))
        res.update(**{k: g["icp"][k] for k in ("acc_cm", "comp_cm", "chamfer_cm", "precision", "recall", "f_score")},
                   **{f"{k}_kabsch": g["kabsch"][k] for k in ("acc_cm", "comp_cm", "chamfer_cm", "f_score")})
        info["geometry"] = {"kabsch": g["kabsch"], "icp": g["icp"], "icp_info": g["icp_info"], "n_model_voxels": g["n_model"], "n_faro_voxels": g["n_faro"]}
    write_json(layout.logs / f"align_{name}.json", info)
    m = ln.length_metrics(rows)
    log(f"[eval] {name} ({label}): ATE cứng {rms * 100:.1f} cm trên {len(views) - n_drop}/{len(views)} camera (loại {n_drop}; mọi camera {res['ate_rigid_all_cm']:.1f} cm); hợp lệ {m['n_valid']}/{len(segs)} đoạn"
        + (f", MAE {m['mae_cm']:.1f} cm, median {m['median_cm']:.1f} cm" if m["n_valid"] else "")
        + f"; đầu mút không snap {snap_info['n_unsnapped']}/{snap_info['n_endpoints']} (điểm gần nhất trung vị {snap_info['nn_median_cm']:.1f} cm)"
        + (f"; Chamfer {res['chamfer_cm']:.1f} cm (sau Kabsch {res['chamfer_cm_kabsch']:.1f}), F {res['f_score']:.3f}" if faro is not None else ""))
    return res


def run_eval(layout: SceneLayout, cfg: Dict, log: Callable[[str], None] = print, variants: Optional[List[str]] = None,
             load_cameras: Callable[[SceneLayout], Dict[int, Dict]] = load_colmap_cameras) -> Dict:
    """Stage `eval`. `variants=None` chấm mọi biến thể có đầu ra; danh sách tường minh thì thiếu đầu ra là lỗi."""
    t0 = time.time()
    base = base_layout(layout)
    explicit = variants is not None
    names = list(variants) if explicit else list(VARIANTS)
    bad = [v for v in names if v not in VARIANTS]
    if bad:
        raise ValueError(f"biến thể không có: {bad} (có: {VARIANTS}); Ablation 2 thuộc M5")
    meas_path = base.ground_truth / "measurements.csv"
    if not meas_path.is_file():
        raise StageError(E_MISSING_INPUT, f"thiếu {meas_path}: chạy scripts/annotate_segments.py --finalize")
    segs = ln.test_segments(ln.read_measurements(meas_path))
    gt_cams = gt_camera_centers(base)
    faro_path = base.faro / "faro_scene_frame.ply"
    faro = geo.load_points(faro_path) if faro_path.is_file() else None
    if faro is None:
        log(f"[eval] CẢNH BÁO: thiếu {faro_path}: bỏ qua Chamfer/F-score")
    ensure_dir(base.logs)
    results, skipped = [], {}
    for name in names:
        try:
            if name == "B1" and any(base.vggt.glob("chunk_*/vggt_out.npz")):
                build_b1(base, cfg, log)
            if not cloud_path(base, name).is_file():
                raise StageError(E_MISSING_INPUT, f"thiếu {cloud_path(base, name)}")
            results.append(_eval_variant(name, base, cfg, segs, gt_cams, faro, load_cameras, log))
        except StageError as e:
            if explicit:
                raise
            skipped[name] = str(e)
            log(f"[eval] bỏ qua {name}: {e}")
    if not results:
        raise StageError(E_MISSING_INPUT, f"không biến thể nào có đầu ra để chấm: {skipped}")
    common = set.intersection(*[{r["id"] for r in x["rows"] if r["valid"]} for x in results])
    ref = next((x for x in results if x["variant"] == "B0"), None)
    ref_c = ln.length_metrics(ref["rows"], common) if ref and common else None
    table = []
    for x in results:
        row = {k: x.get(k) for k in COLUMNS}
        row.update(ln.length_metrics(x["rows"]))
        c = ln.length_metrics(x["rows"], common) if common else {"n_valid": 0, "mae_cm": None, "median_cm": None, "mape_pct": None, "pct_lt5cm": None}
        row.update(n_common=len(common), mae_cm_common=c["mae_cm"], median_cm_common=c["median_cm"], mape_pct_common=c["mape_pct"], pct_lt5cm_common=c["pct_lt5cm"])
        if ref_c and c["mae_cm"] is not None and ref_c["mae_cm"]:
            row["delta_pct_mae_vs_B0"] = delta_percent(ref_c["mae_cm"], c["mae_cm"])
            row["delta_pct_median_vs_B0"] = delta_percent(ref_c["median_cm"], c["median_cm"]) if ref_c["median_cm"] else None
        table.append(row)
    out = base.evaluation / "metrics.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for row in table:
            w.writerow({k: _fmt(row.get(k)) for k in COLUMNS})
    stats = {"variants": [x["variant"] for x in results], "skipped": skipped, "n_segments": len(segs), "n_common": len(common), "common_ids": sorted(common),
             "snap_radius_m": float(cfgmod.require(cfg, "eval.snap_radius_m")), "metrics_csv": str(out), "seconds": round(time.time() - t0, 1)}
    write_json(base.logs / "eval_result.json", stats)
    log(f"[eval] xong {len(results)} biến thể, {len(common)}/{len(segs)} đoạn hợp lệ ở mọi biến thể → {out}")
    return stats
