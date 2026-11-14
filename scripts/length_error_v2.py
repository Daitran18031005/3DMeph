#!/usr/bin/env python3
"""
length_error_v2.py — đo lại sai số chiều dài với ĐỦ MẪU SỐ (không lạc quan do chọn lọc). Quy tắc đặt trước: `docs/evidence/m4_improve/length_error/PLAN_v2.md`.

  Bước 1: bảng mẫu số từ `kabsch/per_segment.csv` và `icp/per_segment.csv` (bán kính snap 2, 3, 5 cm; đoạn không hợp lệ = chưa đạt; theo độ dài Faro; theo scene; tập chung B0/B3/proposed).
  Bước 2: ICP CÓ scale (chỉ để KIỂM scale, không dùng suy scale) của từng biến thể vào Faro + tự kiểm bằng đám điểm B0 nhân 1,03; so với s_m/s theo quỹ đạo.
  Bước 3: kích thước phòng bằng khoảng cách giữa mặt phẳng song song (sàn–trần, tường–tường) của `proposed/plane_refinement/planes.json` so với mặt phẳng khớp trên Faro cùng vùng.

    python scripts/length_error_v2.py --out docs/evidence/m4_improve/length_error/v2
Chỉ đọc; không đổi pipeline, không đổi kết quả cũ, không đụng held-out.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import pipeline  # noqa: E402,F401  (import torch trước cv2/open3d/pycolmap)

# isort: split
import length_error as le  # noqa: E402
import numpy as np  # noqa: E402
import sweep_thresholds as st  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402
from pipeline.common.io import read_json, scene_layout  # noqa: E402
from pipeline.common.ply import read_ply  # noqa: E402
from pipeline.eval import geometry as geo  # noqa: E402
from pipeline.eval.stage import gt_camera_centers  # noqa: E402
from pipeline.eval.variants import base_layout  # noqa: E402

SCENES = ["42897599", "42898849", "42897566", "45662981", "42445022", "42444738"]
VARIANTS = ["B0", "B1", "B3", "proposed"]
RADII = [2.0, 3.0, 5.0]
BINS = [("< 1 m", lambda g: g < 1.0), ("1–2 m", lambda g: 1.0 <= g <= 2.0), ("> 2 m", lambda g: g > 2.0)]
SELF_TEST_SCALE = 1.03
K_TOL_SELF, K_TOL_TRAJ, K_TOL_SIGN = 0.01, 0.02, 0.01                      # ngưỡng đặt trước (PLAN_v2.md bước 2)
PARALLEL_COS, MIN_WALL_GAP_M, FARO_BAND_M, FARO_REGION_M = 0.985, 1.0, 0.08, 0.5


# ---------------------------------------------------------------- Bước 1
def read_seg(path: Path) -> List[Dict]:
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        if r["anchor"] == "True":
            continue
        out.append({"scene": r["scene"], "variant": r["variant"], "id": r["segment"], "gt": float(r["gt_m"]), "nn": max(float(r["nn_a_cm"]), float(r["nn_b_cm"])),
                    "err": None if r["err_cm"] == "" else float(r["err_cm"])})
    return out


def summarize(rows: List[Dict], r_cm: float) -> Dict:
    """rows: các đoạn của MỘT biến thể (cùng tập mẫu số). Hợp lệ(r) = nn ≤ r; sai số đã có sẵn (điểm snap là điểm gần nhất)."""
    n = len(rows)
    va = [x for x in rows if x["nn"] <= r_cm and x["err"] is not None]
    e = np.array([x["err"] for x in va])
    g = np.array([x["gt"] for x in va]) * 100
    ok = int((e < 5).sum()) if len(e) else 0
    full = np.concatenate([e, np.full(n - len(e), np.inf)]) if n else np.array([])
    med_all = float(np.median(full)) if n and len(e) * 2 > n else None             # >= 50% hợp lệ mới xác định được
    return {"N": n, "valid": len(va), "pass": ok, "frac_valid": len(va) / n if n else None, "frac_pass_all": ok / n if n else None, "median_valid": float(np.median(e)) if len(e) else None,
            "mae_valid": float(e.mean()) if len(e) else None, "mape_valid": float((e / g * 100).mean()) if len(e) else None, "pct_lt5_valid": float((e < 5).mean() * 100) if len(e) else None,
            "median_all_invalid_inf": med_all}


def step1(out: Path) -> List[Dict]:
    rows_out: List[Dict] = []
    common_out: List[Dict] = []
    for al in ("kabsch", "icp"):
        seg = read_seg(out.parent / al / "per_segment.csv")
        for r in RADII:
            for v in VARIANTS:
                vs = [x for x in seg if x["variant"] == v]
                if not vs:
                    continue
                scopes = [("tất cả", vs)] + [(f"độ dài {nm}", [x for x in vs if f(x["gt"])]) for nm, f in BINS] + [(f"scene {s}", [x for x in vs if x["scene"] == s]) for s in SCENES]
                for s in SCENES:
                    for nm, fn in BINS:
                        scopes.append((f"scene {s} · {nm}", [x for x in vs if x["scene"] == s and fn(x["gt"])]))
                for sc, rr in scopes:
                    if rr:
                        rows_out.append({"align": al, "variant": v, "radius_cm": r, "scope": sc, **summarize(rr, r)})
            # tập chung B0, B3, proposed
            key = lambda x: (x["scene"], x["id"])                                                       # noqa: E731
            by = {v: {key(x): x for x in seg if x["variant"] == v} for v in ("B0", "B3", "proposed")}
            common = [k for k in by["B0"] if all(k in by[v] and by[v][k]["nn"] <= r and by[v][k]["err"] is not None for v in by)]
            row = {"align": al, "radius_cm": r, "n_common": len(common), "n_total": len(by["B0"])}
            for v in by:
                e = np.array([by[v][k]["err"] for k in common])
                row.update({f"median_{v}": float(np.median(e)) if len(e) else None, f"mae_{v}": float(e.mean()) if len(e) else None})
            for a_, b_ in (("proposed", "B0"), ("proposed", "B3")):
                d = np.array([by[a_][k]["err"] - by[b_][k]["err"] for k in common])
                row[f"paired_median_{a_}_minus_{b_}"] = float(np.median(d)) if len(d) else None
                row[f"paired_max_abs_{a_}_minus_{b_}"] = float(np.abs(d).max()) if len(d) else None
            for nm, fn in BINS:
                row[f"n_common_{nm}"] = sum(1 for k in common if fn(by["B0"][k]["gt"]))
            common_out.append(row)
    write_csv(out / "coverage.csv", rows_out)
    write_csv(out / "common_set.csv", common_out)
    return rows_out


# ---------------------------------------------------------------- Bước 2
def icp_scale(model_scene: np.ndarray, faro: np.ndarray, voxel: float, max_dist: float) -> Dict:
    """ICP rigid rồi ICP có scale; trả về hệ số k (nhân mô hình với k để khớp Faro; k > 1: mô hình nhỏ hơn Faro)."""
    import open3d as o3d
    m, g = geo.voxel_downsample(model_scene, voxel), geo.voxel_downsample(faro, voxel)
    t0, _ = geo.icp_rigid(m, g, max_dist)
    p, q = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(m)), o3d.geometry.PointCloud(o3d.utility.Vector3dVector(g))
    res = o3d.pipelines.registration.registration_icp(p, q, max_dist, t0, o3d.pipelines.registration.TransformationEstimationPointToPoint(with_scaling=True),
                                                       o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=50))
    k = float(np.cbrt(np.linalg.det(np.asarray(res.transformation)[:3, :3])))
    return {"k": k, "fitness": float(res.fitness), "rmse_cm": float(res.inlier_rmse * 100)}


def step2(root: Path, cfg: Dict, out: Path) -> List[Dict]:
    rows: List[Dict] = []
    voxel, md = float(cfgmod.require(cfg, "eval.voxel_m")), float(cfgmod.require(cfg, "eval.icp_max_dist_m"))
    for sc in SCENES:
        ctx = st.eval_context(root, cfg, f"arkitscenes/{sc}")
        lay, faro = ctx["base"], ctx["region"].faro
        gt = gt_camera_centers(lay)
        ratio = next(float(r["s_m_over_s"]) for r in csv.DictReader(open(out.parent / "kabsch" / "per_scene.csv", encoding="utf-8")) if r["scene"] == sc and r["s_m_over_s"])
        k_traj = 1.0 / ratio
        res0 = None
        for v in VARIANTS:
            rr = le.variant_rows(lay, cfg, v, [], gt, 0.05, "kabsch", faro)
            if rr is None:
                continue
            _, r, t, cloud = rr
            ms = (cloud - t) @ r
            a = icp_scale(ms, faro, voxel, md)
            row = {"scene": sc, "variant": v, "k_icp": a["k"], "fitness": a["fitness"], "rmse_cm": a["rmse_cm"], "s_m_over_s": ratio, "k_trajectory": k_traj, "diff_vs_traj": a["k"] - k_traj}
            if v == "B0":
                c = ms.mean(axis=0)
                self_ = icp_scale(c + SELF_TEST_SCALE * (ms - c), faro, voxel, md)
                row.update(k_selftest=self_["k"], selftest_bias=self_["k"] - 1.0 / SELF_TEST_SCALE)
                res0 = row
            rows.append(row)
        for row in rows:
            if row["scene"] == sc:
                bias = res0["selftest_bias"] if res0 else None
                row["reliable"] = bias is not None and abs(bias) <= K_TOL_SELF
                dk = row["k_icp"] - row["k_trajectory"]
                opposite = (row["k_icp"] - 1) * (row["k_trajectory"] - 1) < 0 and abs(row["k_icp"] - 1) > K_TOL_SIGN and abs(row["k_trajectory"] - 1) > K_TOL_SIGN
                row["contradiction"] = bool(abs(dk) > K_TOL_TRAJ or opposite)
        print(f"[bước 2] {sc} xong")
    write_csv(out / "scale_icp.csv", rows)
    return rows


# ---------------------------------------------------------------- Bước 3
def fit_plane(pts: np.ndarray, iters: int = 4):
    """Mặt phẳng bình phương tối thiểu có bỏ dần ngoại lai (residual > 2 × trung vị). Trả về (n, c)."""
    keep = np.ones(len(pts), bool)
    for _ in range(iters):
        c = pts[keep].mean(axis=0)
        n = np.linalg.svd(pts[keep] - c, full_matrices=False)[2][-1]
        res = np.abs((pts - c) @ n)
        keep = res <= max(2 * np.median(res[keep]), 1e-3)
    c = pts[keep].mean(axis=0)
    return np.linalg.svd(pts[keep] - c, full_matrices=False)[2][-1], c, int(keep.sum())


def plane_dist(na, ca, nb, cb) -> float:
    n = na if na @ nb >= 0 else -na
    nbar = n + nb
    nbar /= np.linalg.norm(nbar)
    return float(abs(nbar @ (cb - ca)))


def step3(root: Path, cfg: Dict, out: Path) -> List[Dict]:
    rows: List[Dict] = []
    tau_r = float(cfgmod.require(cfg, "plane.tau_r"))
    for sc in SCENES:
        lay = base_layout(scene_layout(root / cfgmod.require(cfg, "paths.data_root"), "arkitscenes", sc))
        pl = read_json(lay.plane_refinement / "planes.json")["planes"]
        ref = read_ply(lay.plane_refinement / "refined_points.ply")
        pts = np.stack([ref["x"], ref["y"], ref["z"]], axis=1).astype(np.float64)
        glog = list(csv.DictReader(open(lay.plane_refinement / "gate_log.csv", encoding="utf-8")))
        pid = np.array([int(x["plane_id"]) for x in glog])
        rr = np.array([float(x["r_m"]) for x in glog])
        gt = gt_camera_centers(lay)
        faro = geo.load_points(lay.faro / "faro_scene_frame.ply")
        _, r, t, _ = le.variant_rows(lay, cfg, "proposed", [], gt, 0.05, "icp", faro)
        faro_m = faro @ r.T + t                                                            # Faro → hệ mô hình (COLMAP × s_m)
        ftree = cKDTree(faro_m)
        planes = {}
        for p in pl:
            if p["label"] not in ("floor", "ceiling", "wall"):
                continue
            inl = pts[(pid == p["id"]) & (rr < tau_r)]
            if len(inl) < 100:
                continue
            n = np.array(p["n"])
            cand = ftree.query_ball_point(inl[:: max(1, len(inl) // 3000)], FARO_REGION_M)            # điểm Faro gần inlier (cùng vùng)
            idx = np.unique(np.concatenate([np.array(c, dtype=int) for c in cand if len(c)])) if any(len(c) for c in cand) else np.array([], int)
            if len(idx) == 0:
                continue
            near = idx[np.abs(faro_m[idx] @ n + p["d"]) <= FARO_BAND_M]
            if len(near) < 200:
                continue
            nf, cf, nkeep = fit_plane(faro_m[near])
            nm, cm_, _ = fit_plane(inl)
            planes[p["id"]] = {"label": p["label"], "n_model": nm if nm @ n > 0 else -nm, "c_model": cm_, "n_faro": nf, "c_faro": cf, "n_inl": len(inl), "n_faro_pts": nkeep}
        labels = {k: v["label"] for k, v in planes.items()}
        pairs = []
        fl = [k for k, v in labels.items() if v == "floor"]
        ce = [k for k, v in labels.items() if v == "ceiling"]
        pairs += [("sàn–trần", a, b) for a in fl for b in ce]
        wl = [k for k, v in labels.items() if v == "wall"]
        for i, a in enumerate(wl):
            for b in wl[i + 1:]:
                if abs(planes[a]["n_model"] @ planes[b]["n_model"]) >= PARALLEL_COS and plane_dist(planes[a]["n_model"], planes[a]["c_model"], planes[b]["n_model"], planes[b]["c_model"]) >= MIN_WALL_GAP_M:
                    pairs.append(("tường–tường", a, b))
        if not pairs:
            rows.append({"scene": sc, "pair": "không có cặp", "n_floor": len(fl), "n_ceiling": len(ce), "n_wall": len(wl)})
        for typ, a, b in pairs:
            A, B = planes[a], planes[b]
            dm = plane_dist(A["n_model"], A["c_model"], B["n_model"], B["c_model"])
            df = plane_dist(A["n_faro"], A["c_faro"], B["n_faro"], B["c_faro"])
            rows.append({"scene": sc, "pair": typ, "plane_a": a, "plane_b": b, "model_dist_m": dm, "faro_dist_m": df, "err_cm": (dm - df) * 100, "rel_err_pct": (dm - df) / df * 100,
                         "angle_model_deg": float(np.degrees(np.arccos(min(abs(A["n_model"] @ B["n_model"]), 1)))), "angle_faro_deg": float(np.degrees(np.arccos(min(abs(A["n_faro"] @ B["n_faro"]), 1)))),
                         "n_inl_a": A["n_inl"], "n_inl_b": B["n_inl"], "n_faro_a": A["n_faro_pts"], "n_faro_b": B["n_faro_pts"], "n_floor": len(fl), "n_ceiling": len(ce), "n_wall": len(wl)})
        print(f"[bước 3] {sc}: sàn {len(fl)}, trần {len(ce)}, tường {len(wl)}, cặp {len(pairs)}")
    write_csv(out / "plane_pairs.csv", rows)
    return rows


def write_csv(path: Path, rows: List[Dict]) -> None:
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows([{k: ("" if r.get(k) is None else r.get(k)) for k in keys} for r in rows])


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--out", default="docs/evidence/m4_improve/length_error/v2")
    ap.add_argument("--steps", nargs="+", type=int, default=[1, 2, 3])
    a = ap.parse_args(argv)
    root = Path(a.root)
    cfg = cfgmod.load_config(root / "configs" / "default.yaml")
    splits = sp.load_splits(root / "data" / "splits.csv")
    if any(splits.get(v) not in (sp.SPLIT_TRAIN, sp.SPLIT_VAL) for v in SCENES):
        print("[LỖI] có scene không phải train/Validation")
        return 1
    out = (Path(a.out) if Path(a.out).is_absolute() else root / a.out)
    out.mkdir(parents=True, exist_ok=True)
    if 1 in a.steps:
        step1(out)
    if 2 in a.steps:
        step2(root, cfg, out)
    if 3 in a.steps:
        step3(root, cfg, out)
    print(json.dumps({"ok": True, "out": str(out)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
