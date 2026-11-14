#!/usr/bin/env python3
"""
length_error.py — đo sai số chiều dài (mục tiêu: median < 5 cm sau MỘT lần neo scale) bằng phương pháp BÁN TỰ ĐỘNG, CHỈ ĐỌC kết quả có sẵn.

Cách đo (xấp xỉ, KHÔNG thay thế chấm tay đầu mút): đầu mút Faro của đoạn test (`ground_truth/measurements.csv`, bỏ `used_as_anchor = 1`) được đưa sang hệ từng biến thể bằng đúng phép căn của `eval`
(Kabsch cắt tỉa trên tâm camera, scale = 1), snap vào điểm gần nhất của đám điểm biến thể nếu cách ≤ `--radius` (mặc định 5 cm; `eval` mặc định 2 cm), rồi đo khoảng cách giữa hai điểm đã snap.
Đoạn "hợp lệ" = cả hai đầu mút có điểm trong bán kính. Mốc scale là `s_m` có sẵn (một mốc cho mọi biến thể); GT KHÔNG dùng để suy scale. Không đổi tham số nào.
Điểm snap có thể lệch vài cm so với đầu mút người chấm sẽ chọn, nên số này là xấp xỉ.

Bước 2 (độ nhạy theo mốc), quy tắc ĐẶT TRƯỚC: ứng viên mốc thay thế = đoạn test hợp lệ ở B0 có độ dài Faro trong [1,0; 2,5] m (quy tắc của đề cương); nếu < 3 ứng viên thì nới [0,7; 3,0] m;
lấy tối đa 3 đoạn đầu theo thứ tự id. Mốc thay thế `X` cho hệ số `f = L_real(X) / L_B0(X)` (L_B0 = chiều dài B0 đo được); mọi chiều dài dự đoán nhân `f`; tập đánh giá = đoạn test + đoạn mốc gốc, trừ X.
Hệ số s_m / s: tỉ số giữa scale từ mốc và scale quỹ đạo (Umeyama bền tâm camera COLMAP so với quỹ đạo ARKit); CHỈ để kiểm tra, không dùng suy scale.

    python scripts/length_error.py --out docs/evidence/m4_improve/length_error [--align icp]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pipeline  # noqa: E402,F401  (import torch trước cv2/open3d/pycolmap)

# isort: split
import numpy as np  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

from pipeline.alignment.stage import load_colmap_cameras  # noqa: E402
from pipeline.colmap import depth_io  # noqa: E402
from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402
from pipeline.common.geometry import umeyama_sim3  # noqa: E402
from pipeline.common.io import read_json, scene_layout  # noqa: E402
from pipeline.common.schema import read_keyframes_csv  # noqa: E402
from pipeline.eval import geometry as geo  # noqa: E402
from pipeline.eval import lengths as ln  # noqa: E402
from pipeline.eval.stage import gt_camera_centers  # noqa: E402
from pipeline.eval.variants import base_layout, camera_centers, cloud_path  # noqa: E402
from pipeline.fusion import stage as fs  # noqa: E402

SCENES = ["42897599", "42898849", "42897566", "45662981", "42445022", "42444738"]
VARIANTS = ["B0", "B1", "B3", "proposed"]
ANCHOR_RANGES = [(1.0, 2.5), (0.7, 3.0)]


def robust_scale_ratio(cams: Dict, gt: Dict, s_m: float) -> Optional[float]:
    """s_m / s với s = scale Umeyama bền (bỏ dần camera lệch) của tâm camera COLMAP so với quỹ đạo ARKit. Chỉ để KIỂM TRA."""
    views = sorted(set(cams) & set(gt))
    if len(views) < 5:
        return None
    src, dst = np.array([cams[v]["center"] for v in views]), np.array([gt[v] for v in views])
    keep = np.ones(len(views), bool)
    for _ in range(4):
        s, r, t = umeyama_sim3(src[keep], dst[keep])[:3]
        res = np.linalg.norm(s * (src @ r.T) + t - dst, axis=1)
        keep = res < max(0.25, 3 * float(np.median(res[keep])))
    s = umeyama_sim3(src[keep], dst[keep])[0]
    return float(s_m / s)


def variant_rows(layout, cfg, name: str, segs: List[Dict], gt: Dict, radius: float, align: str = "kabsch", faro: Optional[np.ndarray] = None):
    """(rows, R, t, cloud) của biến thể `name`: đầu mút Faro → hệ biến thể → snap ≤ radius. None nếu không có đám điểm.
    `align = kabsch`: đúng phép căn của `eval` (Kabsch cắt tỉa trên tâm camera, scale = 1).
    `align = icp`: như trên rồi tinh chỉnh bằng ICP cứng (scale = 1) của đám điểm vào Faro (cùng thủ tục ICP của chỉ số hình học). Chỉ dịch/xoay, KHÔNG đổi scale."""
    path = cloud_path(layout, name)
    if not path.is_file():
        return None
    cams = camera_centers(layout, name, load_colmap_cameras)
    views = sorted(set(cams) & set(gt))
    r, t, _, _ = ln.kabsch_rigid_trimmed(np.array([gt[v] for v in views]), np.array([cams[v] for v in views]),
                                         float(cfgmod.require(cfg, "eval.align.trim_k")), int(cfgmod.require(cfg, "eval.align.trim_max_iters")))
    cloud = geo.load_points(path)
    if align == "icp":
        vox = float(cfgmod.require(cfg, "eval.voxel_m"))
        tm, _ = geo.icp_rigid(geo.voxel_downsample((cloud - t) @ r, vox), geo.voxel_downsample(faro, vox), float(cfgmod.require(cfg, "eval.icp_max_dist_m")))
        r_i, t_i = tm[:3, :3].T, -tm[:3, :3].T @ tm[:3, 3]                     # nghịch đảo: Faro → hệ scene của mô hình
        r, t = r @ r_i, r @ t_i + t
    return ln.measure_auto(segs, r, t, cloud, radius), r, t, cloud


def topdown_map(path: Path, scene: str, segs: List[Dict], prop, faro: np.ndarray, radius: float) -> None:
    """Bản đồ nhìn từ trên (hệ scene ARKit: x, y; z là trục lên): Faro (xám), đám điểm proposed (xanh), đoạn test/mốc và đầu mút có (xanh lá) / không có (đỏ) điểm trong bán kính."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows, r, t, cloud = prop
    rng = np.random.default_rng(0)
    pick = lambda x, n: x[rng.choice(len(x), min(n, len(x)), replace=False)]                           # noqa: E731
    cs = (pick(cloud, 60000) - t) @ r                                                                  # mô hình → hệ scene
    fig, ax = plt.subplots(figsize=(9, 9), dpi=90)
    fp = pick(faro, 60000)
    ax.scatter(fp[:, 0], fp[:, 1], s=0.2, c="0.75", label="Faro")
    ax.scatter(cs[:, 0], cs[:, 1], s=0.2, c="tab:blue", alpha=0.35, label="proposed")
    for seg, row in zip(segs, rows):
        ok_a, ok_b = row["snapped_a"], row["snapped_b"]
        ax.plot([seg["a"][0], seg["b"][0]], [seg["a"][1], seg["b"][1]], "-", c="tab:purple" if seg["anchor"] else ("green" if ok_a and ok_b else "red"), lw=1, alpha=0.7)
        for key, ok in (("a", ok_a), ("b", ok_b)):
            ax.scatter(*seg[key][:2], marker="o" if ok else "x", c="green" if ok else "red", s=30, zorder=5)
        ax.annotate(row["id"], ((seg["a"][0] + seg["b"][0]) / 2, (seg["a"][1] + seg["b"][1]) / 2), fontsize=8, color="k")
    ax.set_aspect("equal")
    ax.set_title(f"{scene}: xanh lá = đầu mút có điểm proposed trong {radius * 100:.0f} cm, đỏ = không có, tím = mốc scale")
    ax.legend(loc="upper right", markerscale=12, fontsize=8)
    fig.savefig(path)
    plt.close(fig)


def pooled(rows_by_scene: Dict[str, List[Dict]]) -> Dict:
    allr = [r for rows in rows_by_scene.values() for r in rows]
    return ln.length_metrics(allr)


def endpoint_diagnosis(layout, cfg, scene: str, seg_id: str, key: str, q_model: np.ndarray, s_m: float, cams: Dict, kf: Dict[int, Dict], mvs_tree, mvs_counts, img_dir: Path, out_png: Path):
    """Chẩn đoán một đầu mút không có điểm trong bán kính (đã ở hệ mô hình = COLMAP × s_m)."""
    import cv2
    p_colmap = q_model / s_m
    vis = []
    for v, c in cams.items():
        k = kf.get(v)
        if k is None:
            continue
        xc = c["R"] @ p_colmap + c["t"]
        if xc[2] < 0.3:
            continue
        uvw = c["K"] @ xc
        u, vv = uvw[0] / uvw[2], uvw[1] / uvw[2]
        w, h = int(k["w"]), int(k["h"])
        if 0 <= u < w and 0 <= vv < h:
            vis.append((v, float(xc[2] * s_m), float(u), float(vv), float(min(u, w - u, vv, h - vv))))
    out = {"n_views_geometric": len(vis)}
    d_mvs, i_mvs = mvs_tree.query(q_model)
    out.update(mvs_nn_cm=float(d_mvs * 100), mvs_nn_n_views=int(mvs_counts[i_mvs]), n_mvs_within_10cm=int(len(mvs_tree.query_ball_point(q_model, 0.10))), n_mvs_within_20cm=int(len(mvs_tree.query_ball_point(q_model, 0.20))))
    good = [x for x in vis if 0.5 <= x[1] <= 6.0 and x[4] >= 20]
    if not good:
        out["best_view"] = None
        return out
    v, z, u, vv, _ = max(good, key=lambda x: x[4])
    out.update(best_view=int(v), best_depth_m=z)
    img = cv2.imread(str(img_dir / f"{v:04d}.jpg"))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    x0, y0, x1, y1 = int(max(u - 20, 0)), int(max(vv - 20, 0)), int(min(u + 21, gray.shape[1])), int(min(vv + 21, gray.shape[0]))
    gx, gy = cv2.Sobel(gray.astype(np.float32), cv2.CV_32F, 1, 0), cv2.Sobel(gray.astype(np.float32), cv2.CV_32F, 0, 1)
    out["gradient_mean"] = float(np.hypot(gx, gy)[y0:y1, x0:x1].mean())
    for kind in ("geometric", "photometric"):
        dm = depth_io.read_depth_map(layout.colmap_mvs / "stereo" / "depth_maps" / f"{v:04d}.jpg.{kind}.bin")
        out[f"{kind}_valid_frac"] = float((dm[y0:y1, x0:x1] > 0).mean()) if dm.shape == gray.shape else None
    crop = img[max(int(vv) - 80, 0):int(vv) + 80, max(int(u) - 80, 0):int(u) + 80].copy()
    cv2.circle(crop, (int(min(u, 80)), int(min(vv, 80))), 12, (0, 0, 255), 2)
    cv2.putText(crop, f"{scene[-4:]} {seg_id}{key} v{v}", (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
    cv2.imwrite(str(out_png), crop)
    return out


def cause_text(d: Dict) -> str:
    """Gợi ý nguyên nhân (HEURISTIC, chưa kiểm chứng) từ các số đo của `endpoint_diagnosis`."""
    if d.get("best_view") is None:
        return "không có ảnh nhìn rõ (ít view / ở rìa ảnh)"
    if d["n_views_geometric"] < 4:
        return f"ít view nhìn thấy ({d['n_views_geometric']})"
    if d.get("photometric_valid_frac") is not None and d["photometric_valid_frac"] < 0.3:
        return "PatchMatch không ra depth ở đây (vùng trơn, bị che hoặc phản chiếu)"
    if d.get("geometric_valid_frac") is not None and d["geometric_valid_frac"] < 0.3:
        return "depth bị lọc nhất quán hình học (có depth photometric nhưng không nhất quán giữa các ảnh)"
    if d["gradient_mean"] < 15:
        return "bề mặt trơn, ít hoạ tiết (gradient thấp)"
    return "có hoạ tiết và depth nhưng không có điểm hợp nhất: đầu mút ở mép/vật mảnh, hoặc điểm MVS bị lọc ở bước stereo_fusion"


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--scenes", nargs="+", default=SCENES)
    ap.add_argument("--radius", type=float, default=0.05, help="bán kính snap/hợp lệ (m)")
    ap.add_argument("--align", choices=["kabsch", "icp"], default="kabsch", help="phép căn Faro → mô hình: kabsch (đúng `eval`) hoặc icp (Kabsch rồi ICP cứng, scale = 1); ra thư mục con cùng tên")
    ap.add_argument("--out", default="docs/evidence/m4_improve/length_error")
    ap.add_argument("--max-maps", type=int, default=40, help="số đầu mút thiếu điểm tối đa vẽ ảnh chiếu mỗi scene")
    a = ap.parse_args(argv)
    root = Path(a.root)
    cfg = cfgmod.load_config(root / "configs" / "default.yaml")
    splits = sp.load_splits(root / "data" / "splits.csv")
    bad = [v for v in a.scenes if splits.get(v) not in (sp.SPLIT_TRAIN, sp.SPLIT_VAL)]
    if bad:
        print(f"[LỖI] scene không phải train/Validation (held-out bị chặn): {bad}")
        return 1
    out = (Path(a.out) if Path(a.out).is_absolute() else root / a.out) / a.align
    (out / "maps").mkdir(parents=True, exist_ok=True)
    seg_rows: List[Dict] = []
    scene_rows: List[Dict] = []
    ep_rows: List[Dict] = []
    sens_rows: List[Dict] = []
    ratios: Dict[str, Optional[float]] = {}
    store: Dict[str, Dict[str, List[Dict]]] = {v: {} for v in VARIANTS}      # biến thể → scene → hàng đoạn TEST
    for sc in a.scenes:
        lay = base_layout(scene_layout(root / cfgmod.require(cfg, "paths.data_root"), "arkitscenes", sc))
        segs = ln.read_measurements(lay.ground_truth / "measurements.csv")
        gt = gt_camera_centers(lay)
        cams_cm = load_colmap_cameras(lay)
        s_m = float(read_json(lay.alignment / "scale.json")["s_m"])
        ratios[sc] = robust_scale_ratio(cams_cm, gt, s_m)
        faro = geo.load_points(lay.faro / "faro_scene_frame.ply")
        res = {v: variant_rows(lay, cfg, v, segs, gt, a.radius, a.align, faro) for v in VARIANTS}
        by_id = {s["id"]: s for s in segs}
        for v, rr in res.items():
            if rr is None:
                continue
            rows, _, _, _ = rr
            for r in rows:
                seg_rows.append({"scene": sc, "variant": v, "segment": r["id"], "anchor": by_id[r["id"]]["anchor"], "gt_m": r["gt_m"], "nn_a_cm": r["nn_a_m"] * 100, "nn_b_cm": r["nn_b_m"] * 100,
                                 "valid": r["valid"], "pred_m": r["pred_m"], "err_cm": None if r["err_m"] is None else r["err_m"] * 100,
                                 "signed_err_cm": None if r["pred_m"] is None else (r["pred_m"] - r["gt_m"]) * 100})
            test_rows = [r for r in rows if not by_id[r["id"]]["anchor"]]
            store[v][sc] = test_rows
            m = ln.length_metrics(test_rows)
            nn = np.array([x for r in test_rows for x in (r["nn_a_m"], r["nn_b_m"])]) * 100
            scene_rows.append({"scene": sc, "variant": v, "n_test": len(test_rows), "n_valid": m["n_valid"], "frac_valid": m["n_valid"] / max(len(test_rows), 1), "median_cm": m["median_cm"], "mae_cm": m["mae_cm"],
                               "mape_pct": m["mape_pct"], "pct_lt5cm": m["pct_lt5cm"], "nn_median_cm": float(np.median(nn)), "frac_endpoints_within_radius": float((nn <= a.radius * 100).mean()), "s_m_over_s": ratios[sc]})
        # chẩn đoán đầu mút không có điểm trong bán kính ở biến thể proposed
        if res["proposed"] is not None:
            rows_p, r_p, t_p, _ = res["proposed"]
            kf = {int(r["view_id"]): r for r in read_keyframes_csv(lay.metadata / "keyframes.csv")}
            mvs_xyz = fs.read_ply_xyz(lay.colmap_mvs / "fused.ply") * s_m
            counts, _ = fs.read_vis(lay.colmap_mvs / "fused.ply.vis")
            tree = cKDTree(mvs_xyz)
            n_maps = 0
            for r in rows_p:
                seg = by_id[r["id"]]
                for key in ("a", "b"):
                    nnd = r[f"nn_{key}_m"]
                    row = {"scene": sc, "segment": r["id"], "anchor": seg["anchor"], "endpoint": key, "nn_cm": {v: (res[v][0][[x["id"] for x in res[v][0]].index(r["id"])][f"nn_{key}_m"] * 100 if res[v] is not None else None) for v in VARIANTS}}
                    if nnd > a.radius:
                        d = endpoint_diagnosis(lay, cfg, sc, r["id"], key, r_p @ seg[key] + t_p, s_m, cams_cm, kf, tree, counts, lay.keyframes,
                                               out / "maps" / f"{sc}_{r['id']}{key}.png") if n_maps < a.max_maps else {}
                        n_maps += 1 if d else 0
                        row.update(d)
                        row["cause"] = cause_text(d) if d else "(không vẽ: quá giới hạn --max-maps)"
                    ep_rows.append(row)
        if res["proposed"] is not None:
            topdown_map(out / "maps" / f"{sc}_topdown.png", sc, segs, res["proposed"], faro, a.radius)
        # bước 2: độ nhạy theo mốc
        if res["B0"] is not None:
            rows_b0 = {r["id"]: r for r in res["B0"][0]}
            cand = []
            for lo, hi in ANCHOR_RANGES:
                cand = [s["id"] for s in segs if not s["anchor"] and rows_b0[s["id"]]["valid"] and lo <= s["gt_m"] <= hi]
                if len(cand) >= 3:
                    break
            alts = sorted(cand)[:3]
            for v, rr in res.items():
                if rr is None:
                    continue
                base_m = ln.length_metrics([r for r in rr[0] if not by_id[r["id"]]["anchor"]])
                sens_rows.append({"scene": sc, "variant": v, "scenario": "mốc gốc", "factor": 1.0, "n_valid": base_m["n_valid"], "median_cm": base_m["median_cm"], "mae_cm": base_m["mae_cm"]})
                for x in alts:
                    f = rows_b0[x]["gt_m"] / rows_b0[x]["pred_m"]
                    sel = [dict(r, pred_m=r["pred_m"] * f, err_m=abs(r["pred_m"] * f - r["gt_m"])) for r in rr[0] if r["valid"] and r["id"] != x]
                    mm = ln.length_metrics(sel)
                    sens_rows.append({"scene": sc, "variant": v, "scenario": f"mốc {x}", "factor": f, "n_valid": mm["n_valid"], "median_cm": mm["median_cm"], "mae_cm": mm["mae_cm"]})
        print(f"[ok] {sc}: s_m/s = {ratios[sc]:.3f}" if ratios[sc] else f"[ok] {sc}")

    def write(name, rows):
        if rows:
            keys = list(dict.fromkeys(k for r in rows for k in r))
            with open(out / name, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                w.writerows([{k: ("" if r.get(k) is None else r.get(k)) for k in keys} for r in rows])
    write("per_segment.csv", seg_rows)
    write("per_scene.csv", scene_rows)
    write("endpoints_missing.csv", [dict(r, nn_cm=";".join(f"{k}={'' if v is None else round(v, 1)}" for k, v in r["nn_cm"].items())) for r in ep_rows])
    write("sensitivity.csv", sens_rows)
    print("\nGộp các scene (đoạn test, hợp lệ trong bán kính %.0f cm):" % (a.radius * 100))
    for v in VARIANTS:
        m = pooled(store[v])
        n_t = sum(len(x) for x in store[v].values())
        print(f"  {v:9s} hợp lệ {m['n_valid']}/{n_t}  median {m['median_cm']}  MAE {m['mae_cm']}  MAPE {m['mape_pct']}  <5cm {m['pct_lt5cm']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
