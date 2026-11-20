"""oracle_gate.py — thí nghiệm A1 + A2 cho plane gate trên Replica dev (lệch #53, WORKING_LOG).

A1 (phân rã): điểm B3 (fusion) được gán mặt phẳng GT (preseg, ≤ eval.plane.assign_m) chia 3 nhóm theo quyết định của cổng
   proposed: qua cổng; bị chặn dù gần mặt RANSAC (r < τ_r, trượt θ hoặc w); bị chặn vì xa mọi mặt RANSAC (r ≥ τ_r).
   Báo tỉ lệ điểm, |khoảng cách tới mặt GT| trung bình và phần đóng góp vào tổng sai số.
A2 (oracle): thay mặt RANSAC bằng mặt GT rồi kéo điểm B3 theo (24)(25):
   O1 cùng cổng gốc (τ_r, τ_n, τ_w, alpha); O2 nới hết (τ_w 0, alpha 1); O3 trần: kéo hết điểm cách mặt GT < τ_r về đúng mặt.
   O3 là giới hạn trên của mọi cổng có độ dày τ_r. Chấm bằng `plane_metrics` (36), cùng hàm của eval.
A3 (lệch của từng mặt RANSAC): đưa (n, d) của mỗi mặt trong `planes.json` sang hệ GT; inlier = điểm B3 cách mặt < τ_r;
   mặt GT tương ứng = nhãn GT chiếm đa số trong inlier. Báo góc lệch pháp tuyến (°), lệch vị trí tại tâm inlier (cm),
   độ thuần (tỉ lệ inlier thuộc mặt GT đó) và số mặt GT bị gộp (mỗi mặt chiếm ≥ 5% inlier).

Dùng: python scripts/oracle_gate.py --scenes hotel_0 frl_apartment_0 --out outputs/eval_results/replica_gate_oracle_dev.csv
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pipeline  # noqa: E402,F401  (import torch trước pycolmap/open3d)
from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common.io import SceneLayout, ensure_dir  # noqa: E402
from pipeline.common.ply import read_ply  # noqa: E402
from pipeline.eval.plane_gt import load_plane_gt, plane_metrics  # noqa: E402
from pipeline.plane_gate.stage import estimate_normals  # noqa: E402

DEV = {"hotel_0", "frl_apartment_0"}


def to_gt(path: Path, align: dict):
    """Đọc PLY (hệ mô hình, mét) → (điểm hệ GT, các trường). Phép căn của eval: mô hình = R·GT + t ⇒ GT = Rᵀ(p − t)."""
    f = read_ply(path)
    p = np.stack([f["x"], f["y"], f["z"]], axis=1).astype(np.float64)
    r, t = np.array(align["R_gt_to_model"]), np.array(align["t_gt_to_model"])
    return (p - t) @ r, f


def gt_assign(pts, gt, assign_m):
    """Chỉ số mặt GT của từng điểm (−1 nếu không gán), khoảng cách có dấu tới mặt đó."""
    from scipy.spatial import cKDTree
    dist, j = cKDTree(gt["points"]).query(pts, distance_upper_bound=assign_m)
    lab = np.full(len(pts), -1)
    ok = np.isfinite(dist)
    lab[ok] = gt["label"][j[ok]]
    n = np.array([p["n"] for p in gt["planes"]])
    d = np.array([p["d"] for p in gt["planes"]])
    res = np.zeros(len(pts))
    m = lab >= 0
    res[m] = np.einsum("ij,ij->i", pts[m], n[lab[m]]) + d[lab[m]]
    return lab, res, n


def project_gt(pts, lab, res, n, mask, alpha):
    """(25) với mặt GT: p ← p − alpha·(nᵀp + d)·n cho các điểm `mask`."""
    out = pts.copy()
    out[mask] -= alpha * res[mask, None] * n[lab[mask]]
    return out


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenes", nargs="+", required=True)
    ap.add_argument("--config", default=str(REPO / "configs" / "default.yaml"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--a3-only", action="store_true", help="chỉ chạy A3 (nhanh, không ước lượng pháp tuyến)")
    ap.add_argument("--variant", default=None, help="A3 đọc planes.json của proposed/variants/<variant>/plane_refinement thay cho proposed")
    a = ap.parse_args(argv)
    if set(a.scenes) - DEV:
        print(f"[LỖI] chỉ chạy trên tập dev {sorted(DEV)}")
        return 1
    cfg = cfgmod.load_config(a.config)
    pc = cfgmod.require(cfg, "eval.plane")
    tau_r, tau_n, tau_w, alpha = (float(cfgmod.require(cfg, f"plane.{k}")) for k in ("tau_r", "tau_n_deg", "tau_w", "alpha"))
    knn = int(cfgmod.get(cfg, "plane.gate_normal_knn") or cfgmod.require(cfg, "plane.normal_knn"))
    rows = []
    for s in a.scenes:
        base = SceneLayout(REPO / "data" / "scenes" / "replica" / s)
        align = json.loads((base.logs / "align_proposed.json").read_text(encoding="utf-8"))
        gt = load_plane_gt(REPO / "data" / "raw" / "replica" / s, pc)
        b3, fb = to_gt(base.fusion / "fused_points.ply", align)
        prop, fp = to_gt(base.plane_refinement / "refined_points.ply", align)
        assert len(b3) == len(prop), "refined_points phải cùng thứ tự với fused_points"
        g = fp["g"].astype(bool)
        r_ransac = np.loadtxt(base.plane_refinement / "gate_log.csv", delimiter=",", skiprows=1, usecols=3)
        lab, res, n = gt_assign(b3, gt, float(pc["assign_m"]))
        on = lab >= 0
        # A3: lệch của từng mặt RANSAC so với mặt GT tương ứng
        pdir = base.proposed / "variants" / a.variant / "plane_refinement" if a.variant else base.plane_refinement
        pj = json.loads((pdir / "planes.json").read_text(encoding="utf-8"))
        members = np.load(pdir / "plane_members.npy") if (pdir / "plane_members.npy").is_file() else None
        rm, tm = np.array(align["R_gt_to_model"]), np.array(align["t_gt_to_model"])
        dgt = np.array([q["d"] for q in gt["planes"]])
        print(f"  A3 {len(pj['planes'])} mặt RANSAC (cấu trúc: {pj['structural_plane_ids']})")
        for q in pj["planes"]:
            nm, dm = np.array(q["n"]), float(q["d"])
            ng, dg = rm.T @ nm, float(nm @ tm + dm)                     # nᵀ(R·p + t) + d = (Rᵀn)ᵀp + (nᵀt + d)
            inl = (members == q["id"]) if members is not None else np.abs(b3 @ ng + dg) < tau_r   # bộ dò refined: inlier là mảng của mặt
            labs = lab[inl & on]
            row = {"scene": s, "exp": "A3", "name": f"plane{q['id']}_{q['label']}", "n_inliers": int(inl.sum()),
                   "structural": q["id"] in pj["structural_plane_ids"]}
            if len(labs):
                cnt = np.bincount(labs, minlength=len(gt["planes"]))
                k = int(cnt.argmax())
                c = b3[inl].mean(axis=0)
                c -= (c @ ng + dg) * ng                                    # tâm inlier chiếu lên mặt RANSAC
                row.update(gt_plane=gt["planes"][k]["segment"], purity=cnt[k] / len(labs), n_gt_merged=int((cnt >= 0.05 * len(labs)).sum()),
                           frac_inliers_on_gt=len(labs) / inl.sum(),
                           angle_deg=float(np.degrees(np.arccos(min(1.0, abs(ng @ n[k]))))), offset_cm=float(abs(c @ n[k] + dgt[k]) * 100))
                print(f"    {row['name']}: {inl.sum():,} inlier, khớp mặt GT {row['gt_plane']} (thuần {row['purity'] * 100:.0f}%, gộp {row['n_gt_merged']} mặt GT), "
                      f"lệch {row['angle_deg']:.2f}°, {row['offset_cm']:.2f} cm")
            rows.append(row)
        if a.a3_only:
            continue
        # A1: phân rã sai số của B3 trên các điểm thuộc mặt GT
        groups = {"qua_cong": on & g, "chan_gan_mat": on & ~g & (r_ransac < tau_r), "chan_xa_mat": on & ~g & (r_ransac >= tau_r)}
        tot = np.abs(res[on]).sum()
        print(f"== {s}: {on.sum():,}/{len(b3):,} điểm B3 thuộc {len(gt['planes'])} mặt GT; |sai số| TB {np.abs(res[on]).mean() * 100:.2f} cm")
        for k, m in groups.items():
            rows.append({"scene": s, "exp": "A1", "name": k, "frac_points": m.sum() / on.sum(), "mean_abs_cm": np.abs(res[m]).mean() * 100,
                         "share_of_error": np.abs(res[m]).sum() / tot})
            print(f"  A1 {k}: {m.sum() / on.sum() * 100:.1f}% điểm, |sai số| TB {np.abs(res[m]).mean() * 100:.2f} cm, "
                  f"chiếm {np.abs(res[m]).sum() / tot * 100:.1f}% tổng sai số")
        # A2: oracle mặt GT
        theta = np.full(len(b3), 90.0)
        nrm = estimate_normals(b3, knn)
        theta[on] = np.degrees(np.arccos(np.clip(np.abs(np.einsum("ij,ij->i", nrm[on], n[lab[on]])), 0, 1)))
        near = on & (np.abs(res) < tau_r)
        w = fb["w_k"].astype(np.float64)
        variants = {"B3": b3, "proposed": prop,
                    "O1_gt_cong_goc": project_gt(b3, lab, res, n, near & (theta < tau_n) & (w > tau_w), alpha),
                    "O2_gt_noi_het": project_gt(b3, lab, res, n, near & (theta < tau_n), 1.0),
                    "O3_tran_tau_r": project_gt(b3, lab, res, n, near, 1.0)}
        ref = None
        for k, p in variants.items():
            m = plane_metrics(p, gt, pc)
            ref = ref or m["p2plane_cm"]
            rows.append({"scene": s, "exp": "A2", "name": k, "p2plane_cm": m["p2plane_cm"], "plane_recall": m["plane_recall"],
                         "delta_pct_vs_B3": 100 * (m["p2plane_cm"] - ref) / ref})
            print(f"  A2 {k}: P2Plane {m['p2plane_cm']:.3f} cm ({100 * (m['p2plane_cm'] - ref) / ref:+.1f}% so với B3), recall {m['plane_recall']:.3f}")
    out = Path(a.out)
    ensure_dir(out.parent)
    cols = ["scene", "exp", "name", "frac_points", "mean_abs_cm", "share_of_error", "p2plane_cm", "plane_recall", "delta_pct_vs_B3",
            "n_inliers", "structural", "gt_plane", "purity", "n_gt_merged", "frac_inliers_on_gt", "angle_deg", "offset_cm"]
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"ghi {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
