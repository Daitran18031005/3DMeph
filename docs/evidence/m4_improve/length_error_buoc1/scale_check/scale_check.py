"""Bước 3 (chỉ đọc): (A) fusion có đổi scale so với B0 không; (B) tự kiểm ICP scale trên B3; (C) từng mặt tường so với Faro."""
import sys, csv, json
from pathlib import Path
REPO = Path(r"D:\Nghien_Cuu\3D_Metric\3DMeph")
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))
import pipeline  # noqa
import numpy as np
import length_error as le, length_error_v2 as v2, sweep_thresholds as st
from pipeline.common import config as cfgmod
from pipeline.eval import geometry as geo
from pipeline.eval.stage import gt_camera_centers

cfg = cfgmod.load_config(REPO / "configs/default.yaml") if hasattr(cfgmod, "load_config") else None
cfg = cfgmod.load_config(REPO / "configs" / "default.yaml")
root = REPO
voxel, md = float(cfgmod.require(cfg, "eval.voxel_m")), float(cfgmod.require(cfg, "eval.icp_max_dist_m"))
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
rowsA = []
for sc in v2.SCENES:
    ctx = st.eval_context(root, cfg, f"arkitscenes/{sc}")
    lay, faro = ctx["base"], ctx["region"].faro
    gt = gt_camera_centers(lay)
    ms = {}
    for v in ["B0", "B3"]:
        _, r, t, cloud = le.variant_rows(lay, cfg, v, [], gt, 0.05, "kabsch", faro)
        ms[v] = (cloud - t) @ r
    k03 = v2.icp_scale(ms["B3"], ms["B0"], voxel, md)["k"]                       # B3 → B0 (cloud-to-cloud)
    k0f = v2.icp_scale(ms["B0"], faro, voxel, md)["k"]
    k3f = v2.icp_scale(ms["B3"], faro, voxel, md)["k"]
    c = ms["B3"].mean(axis=0)
    k3self = v2.icp_scale(c + 1.03 * (ms["B3"] - c), faro, voxel, md)["k"]
    rowsA.append({"scene": sc, "k_B3_to_B0": k03, "k_B0_to_Faro": k0f, "k_B3_to_Faro": k3f, "product_k03_k0f": k03 * k0f,
                  "selftest_B3_k": k3self, "selftest_B3_bias": k3self - 1 / 1.03})
    print(sc, {k: round(v, 4) for k, v in rowsA[-1].items() if k != "scene"}, flush=True)
v2.write_csv(OUT / "fusion_scale_check.csv", rowsA)

# C: từng mặt phẳng (sàn/tường) so với Faro, sau phép căn Kabsch + ICP cứng như bước 3
from scipy.spatial import cKDTree
rowsC = []
tau_r = float(cfgmod.require(cfg, "plane.tau_r"))
from pipeline.common.io import read_json
from pipeline.common.ply import read_ply
from pipeline.eval.variants import base_layout
for sc in v2.SCENES:
    lay = ctx_lay = st.eval_context(root, cfg, f"arkitscenes/{sc}")["base"]
    pl = read_json(lay.plane_refinement / "planes.json")["planes"]
    ref = read_ply(lay.plane_refinement / "refined_points.ply")
    pts = np.stack([ref["x"], ref["y"], ref["z"]], axis=1).astype(np.float64)
    glog = list(csv.DictReader(open(lay.plane_refinement / "gate_log.csv", encoding="utf-8")))
    pid = np.array([int(x["plane_id"]) for x in glog]); rr = np.array([float(x["r_m"]) for x in glog])
    gtc = gt_camera_centers(lay); faro = geo.load_points(lay.faro / "faro_scene_frame.ply")
    _, r, t, _ = le.variant_rows(lay, cfg, "proposed", [], gtc, 0.05, "icp", faro)
    faro_m = faro @ r.T + t; ftree = cKDTree(faro_m)
    for p in pl:
        if p["label"] not in ("floor", "ceiling", "wall"):
            continue
        inl = pts[(pid == p["id"]) & (rr < tau_r)]
        if len(inl) < 100:
            continue
        n = np.array(p["n"])
        cand = ftree.query_ball_point(inl[:: max(1, len(inl) // 3000)], v2.FARO_REGION_M)
        idx = np.unique(np.concatenate([np.array(c_, dtype=int) for c_ in cand if len(c_)])) if any(len(c_) for c_ in cand) else np.array([], int)
        if len(idx) == 0:
            continue
        near = idx[np.abs(faro_m[idx] @ n + p["d"]) <= v2.FARO_BAND_M]
        if len(near) < 200:
            continue
        nf, cf, _ = v2.fit_plane(faro_m[near]); nm, cm, _ = v2.fit_plane(inl)
        nf = nf if nf @ nm > 0 else -nf
        sd = (inl - cf) @ nf                                           # khoảng cách có dấu của inlier mô hình tới mặt Faro (dọc pháp tuyến Faro)
        tilt = float(np.degrees(np.arccos(min(abs(nm @ nf), 1))))
        rowsC.append({"scene": sc, "plane": p["id"], "label": p["label"], "n_inl": len(inl), "tilt_model_vs_faro_deg": tilt,
                      "offset_mean_cm": float(sd.mean() * 100), "offset_std_cm": float(sd.std() * 100),
                      "offset_p5_cm": float(np.percentile(sd, 5) * 100), "offset_p95_cm": float(np.percentile(sd, 95) * 100),
                      "extent_m": float(np.ptp(inl @ (np.cross(nf, [0, 0, 1.0]) / max(np.linalg.norm(np.cross(nf, [0, 0, 1.0])), 1e-9))))})
    print(sc, "mặt phẳng xong", flush=True)
v2.write_csv(OUT / "plane_offsets.csv", rowsC)
