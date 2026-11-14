#!/usr/bin/env python3
"""
diagnose_gate.py — chẩn đoán cổng plane gate (M4 đợt 3c): CHỈ ĐỌC kết quả đã có (`proposed/fusion`, `proposed/plane_refinement`), không đổi pipeline, không đổi ngưỡng.

Dùng Faro làm đáp án (đúng hệ và vùng chấm của `eval`: Kabsch cắt tỉa, vùng `eval.region.mode`) để trả lời:
  A. Thang `w_k`: phân bố và hệ số nào trong 6 hệ số kéo `w` xuống.
  B. `w_k` có báo trước độ chính xác không (tỉ lệ điểm cách Faro ≤ 5 cm theo thập phân vị `w_k`, Spearman)?
  C. Từng điều kiện của cổng (r, θ, w, nhãn cấu trúc): điểm qua có chính xác hơn điểm trượt không?
  D. Góc θ của điểm đã sát mặt phẳng (r < τ_r): phân bố, và tính lại với k khác (nhiễu pháp tuyến?).
  E. Mặt phẳng: nhãn, độ cao, hướng "lên" ước lượng so với trọng lực thật (trục z của hệ scene ARKit).
  F. Cổng có kéo điểm về phía Faro không (sai số trước/sau với điểm g = 1)?
  G. Nếu đổi ngưỡng (chỉ để xem, KHÔNG áp dụng): tỉ lệ qua cổng và độ chính xác của điểm qua.

    python scripts/diagnose_gate.py --scenes 42897599 42898849 --out docs/evidence/m4_improve/gate_diagnosis
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
import numpy as np  # noqa: E402
import sweep_thresholds as st  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402
from pipeline.common.ply import read_ply  # noqa: E402
from pipeline.eval.geometry import icp_rigid, voxel_downsample  # noqa: E402

SCENES = ["42897599", "42898849", "42897566", "45662981", "42445022", "42444738"]
FACTORS = ["c_model", "f_e", "f_sigma", "q_blur", "q_texture", "q_exposure"]


def pct(a, qs=(5, 25, 50, 75, 95)) -> Dict[str, float]:
    a = np.asarray(a, dtype=np.float64)
    return {str(q): round(float(np.percentile(a, q)), 4) for q in qs} if len(a) else {}


def frac_le(d, cm=5.0) -> float:
    d = np.asarray(d)
    return round(float((d <= cm / 100.0).mean()), 4) if len(d) else float("nan")


def local_normals(tree: cKDTree, pts: np.ndarray, xyz: np.ndarray, k: int) -> np.ndarray:
    """Pháp tuyến PCA (k láng giềng trong toàn cloud) tại `pts`."""
    _, idx = tree.query(pts, k=k, workers=-1)
    nb = xyz[idx] - xyz[idx].mean(axis=1, keepdims=True)
    cov = np.einsum("nki,nkj->nij", nb, nb) / k
    w, v = np.linalg.eigh(cov)
    return v[:, :, 0]                                              # vector riêng của trị riêng nhỏ nhất


def diagnose(root: Path, cfg: Dict, scene: str) -> Dict:
    ctx = st.eval_context(root, cfg, f"arkitscenes/{scene}")
    base = ctx["base"]
    r_mat, t_vec = ctx["r"], ctx["t"]
    tau = {k: float(cfgmod.require(cfg, f"plane.{k}")) for k in ("tau_r", "tau_n_deg", "tau_w", "alpha")}
    fz = read_ply(base.fusion / "fused_points.ply")
    rf = read_ply(base.plane_refinement / "refined_points.ply")
    xyz = np.stack([fz["x"], fz["y"], fz["z"]], axis=1).astype(np.float64)
    xyz2 = np.stack([rf["x"], rf["y"], rf["z"]], axis=1).astype(np.float64)
    log = list(csv.DictReader(open(base.plane_refinement / "gate_log.csv", encoding="utf-8")))
    r_m = np.array([float(x["r_m"]) for x in log])
    theta = np.array([float(x["theta_deg"]) for x in log])
    label = np.array([x["label"] for x in log])
    g = np.array([int(x["g"]) for x in log])
    w_k = np.array([float(x["w_k"]) for x in log])
    pid = np.array([int(x["plane_id"]) for x in log])
    planes = json.loads((base.plane_refinement / "planes.json").read_text(encoding="utf-8"))
    tree_f = cKDTree(ctx["region"].faro)
    # căn y như `eval`: Kabsch cắt tỉa theo camera rồi ICP cứng (scale = 1) trên cloud CHƯA qua cổng; cùng một phép căn cho trước và sau để cô lập tác động của cổng
    pg = (xyz - t_vec) @ r_mat
    icp_t, _ = icp_rigid(voxel_downsample(pg, ctx["voxel"]), voxel_downsample(ctx["region"].faro, ctx["voxel"]), ctx["icp"])
    to_faro = lambda p_: ((p_ - t_vec) @ r_mat) @ icp_t[:3, :3].T + icp_t[:3, 3]            # noqa: E731
    d_before = tree_f.query(to_faro(xyz))[0]                        # khoảng cách tới Faro (m)
    d_after = tree_f.query(to_faro(xyz2))[0]
    out: Dict = {"scene": scene, "n_points": int(len(xyz)), "tau": tau, "frac_within_5cm_all": frac_le(d_before)}
    struct = np.isin(label, ["wall", "floor", "ceiling"])
    cond = {"r": r_m < tau["tau_r"], "theta": theta < tau["tau_n_deg"], "w": w_k > tau["tau_w"], "struct": struct}
    out["gate_pass_fraction"] = round(float(g.mean()), 5)
    out["cond_pass_fraction"] = {k: round(float(v.mean()), 4) for k, v in cond.items()}
    # A. thang w_k và 6 hệ số (theo cặp (điểm, view) trong fusion_log)
    fl = np.load(base.fusion / "fusion_log.npz")
    tau_e, tau_s = float(cfgmod.require(cfg, "fusion.tau_e")), float(cfgmod.require(cfg, "fusion.tau_sigma"))
    fac = {"c_model": fl["c_model"], "f_e": np.exp(-fl["e_reproj"] / tau_e), "f_sigma": np.exp(-np.nan_to_num(fl["sigma_m"], nan=1e9) / tau_s),
           "q_blur": fl["q_blur"], "q_texture": fl["q_texture"], "q_exposure": fl["q_exposure"]}
    out["w_k_percentiles"] = pct(w_k)
    out["w_pair_percentiles"] = pct(fl["w"])
    out["factor_median"] = {k: round(float(np.nanmedian(v)), 3) for k, v in fac.items()}
    out["factor_frac_below_0.5"] = {k: round(float(np.nanmean(v < 0.5)), 3) for k, v in fac.items()}
    out["sigma_nan_fraction"] = round(float(np.isnan(fl["sigma_m"]).mean()), 3)
    # B. w_k báo trước độ chính xác?
    sel = np.isfinite(d_before)
    rho = spearmanr(w_k[sel], d_before[sel])
    qs = np.quantile(w_k, np.linspace(0, 1, 11))
    dec = []
    for i in range(10):
        m = (w_k >= qs[i]) & ((w_k <= qs[i + 1]) if i == 9 else (w_k < qs[i + 1]))
        dec.append({"w_lo": round(float(qs[i]), 3), "w_hi": round(float(qs[i + 1]), 3), "frac_within_5cm": frac_le(d_before[m]), "median_err_cm": round(float(np.median(d_before[m])) * 100, 2)})
    out["spearman_w_vs_error"] = round(float(rho.statistic), 3)
    out["error_by_w_decile"] = dec
    # C. từng điều kiện: điểm qua so với điểm trượt
    out["by_condition"] = {k: {"pass_frac_within_5cm": frac_le(d_before[v]), "fail_frac_within_5cm": frac_le(d_before[~v]),
                               "pass_median_cm": round(float(np.median(d_before[v])) * 100, 2) if v.any() else None,
                               "fail_median_cm": round(float(np.median(d_before[~v])) * 100, 2) if (~v).any() else None} for k, v in cond.items()}
    # D. θ của điểm sát mặt phẳng, tính lại với k khác
    near = np.nonzero(struct & cond["r"])[0]
    out["n_near_plane"] = int(len(near))
    out["theta_near_plane_percentiles"] = pct(theta[near], (10, 25, 50, 75, 90))
    out["theta_near_plane_frac_lt_15"] = round(float((theta[near] < 15).mean()), 3)
    rng = np.random.default_rng(0)
    samp = rng.choice(near, size=min(15000, len(near)), replace=False) if len(near) else near
    tree_m = cKDTree(xyz)
    pl_n = {p["id"]: np.array(p["n"]) for p in planes["planes"]}
    nn = np.array([pl_n[int(i)] for i in pid[samp]]) if len(samp) else np.zeros((0, 3))
    th_k = {}
    for k in (30, 100, 300):
        nv = local_normals(tree_m, xyz[samp], xyz, k)
        th_k[str(k)] = round(float(np.median(np.degrees(np.arccos(np.clip(np.abs((nv * nn).sum(1)), 0, 1))))), 2)
    out["theta_median_deg_by_knn"] = th_k
    # E. mặt phẳng và hướng lên so với trọng lực thật
    up = np.array(planes["up"])
    up = up / np.linalg.norm(up)
    gravity = r_mat @ np.array([0.0, 0.0, 1.0])                      # trục z (lên) của hệ scene ARKit trong hệ mô hình (khoảng z của phòng ≈ 2,8 m)
    out["up_error_vs_true_gravity_deg"] = round(float(np.degrees(np.arccos(np.clip(abs(float(up @ gravity)), 0, 1)))), 2)
    out["up_refine_deviation_deg"] = planes["up_info"].get("deviation_deg")
    out["planes"] = [{"id": p["id"], "label": p["label"], "height_m": None if p["height_m"] is None else round(p["height_m"], 3), "angle_to_up_deg": round(p["angle_to_up_deg"], 1), "n_inliers": p["n_inliers"]} for p in planes["planes"]]
    # F. cổng có kéo điểm về phía Faro?
    gi = g == 1
    out["gate_moves"] = {"n": int(gi.sum()), "median_err_before_cm": round(float(np.median(d_before[gi])) * 100, 2) if gi.any() else None,
                         "median_err_after_cm": round(float(np.median(d_after[gi])) * 100, 2) if gi.any() else None,
                         "frac_improved": round(float((d_after[gi] < d_before[gi] - 1e-6).mean()), 3) if gi.any() else None,
                         "frac_worse": round(float((d_after[gi] > d_before[gi] + 1e-6).mean()), 3) if gi.any() else None}
    # G. what-if (chỉ xem)
    wi = []
    for tw in (0.1, 0.2, 0.3, 0.4, 0.5):
        for tn in (15, 25, 35):
            m = cond["r"] & struct & (w_k > tw) & (theta < tn)
            wi.append({"tau_w": tw, "tau_n": tn, "pass_frac": round(float(m.mean()), 4), "frac_within_5cm": frac_le(d_before[m])})
    out["what_if"] = wi
    return out


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--scenes", nargs="+", default=SCENES)
    ap.add_argument("--out", default="docs/evidence/m4_improve/gate_diagnosis")
    a = ap.parse_args(argv)
    root = Path(a.root)
    cfg = cfgmod.load_config(root / "configs" / "default.yaml")
    splits = sp.load_splits(root / "data" / "splits.csv")
    bad = [v for v in a.scenes if splits.get(v) not in (sp.SPLIT_TRAIN, sp.SPLIT_VAL)]
    if bad:
        print(f"[LỖI] scene không phải train/Validation (held-out bị chặn): {bad}")
        return 1
    out = Path(a.out) if Path(a.out).is_absolute() else root / a.out
    out.mkdir(parents=True, exist_ok=True)
    res: List[Dict] = []
    for v in a.scenes:
        r = diagnose(root, cfg, v)
        (out / f"{v}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[ok] {v}: qua cổng {r['gate_pass_fraction']:.4f}, Spearman(w_k, sai số) {r['spearman_w_vs_error']}, hướng lên lệch trọng lực {r['up_error_vs_true_gravity_deg']}°")
        res.append(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
