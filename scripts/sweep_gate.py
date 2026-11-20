"""sweep_gate.py — quét cấu hình plane gate (24)(25) trên các scene Replica dev (lệch #53, WORKING_LOG).

Mỗi cấu hình chạy `run_gate` vào thư mục biến thể riêng `proposed/variants/sweep_<tag>/` (dùng lại điểm fusion của proposed,
fuse không phụ thuộc tham số gate) rồi chấm bằng `_eval_variant` (P2Plane, PlaneRecall, F, Chamfer). Không ghi đè
`evaluation/metrics.csv`; kết quả gộp ở `--out`. Chặn scene không thuộc dev để không vô tình quét trên tập test.

Dùng: python scripts/sweep_gate.py --scenes hotel_0 frl_apartment_0 --out outputs/eval_results/replica_gate_sweep_dev.csv
"""

import argparse
import copy
import csv
import itertools
import os
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pipeline  # noqa: E402,F401  (import torch trước pycolmap/open3d)
from pipeline.alignment.stage import load_colmap_cameras  # noqa: E402
from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common.io import SceneLayout, ensure_dir  # noqa: E402
from pipeline.eval import geometry as geo  # noqa: E402
from pipeline.eval import lengths as ln  # noqa: E402
from pipeline.eval import region as rg  # noqa: E402
from pipeline.eval import stage as ev  # noqa: E402
from pipeline.eval.plane_gt import load_plane_gt  # noqa: E402
from pipeline.eval.variants import VariantLayout  # noqa: E402
from pipeline.plane_gate.stage import run_gate  # noqa: E402

DEV = {"hotel_0", "frl_apartment_0"}
GRIDS = {
    "small": {"tau_w": [0.0, 0.25, 0.5], "alpha": [0.5, 1.0], "max_planes": [8, 20]},
    # max_planes cố định 8: lưới nhỏ cho thấy 8 → 20 đổi P2Plane < 0,001 cm
    # lệch #53: bộ dò cải tiến, hai phạm vi cổng (struct theo ĐC (24), all gồm mặt đồ đạc = lệch #54)
    "refined": {"detector": ["refined"], "gate_scope": ["struct", "all"], "refined.ransac_m": [0.01, 0.02],
                "refined.cluster_eps_m": [0.05, 0.10], "refined.min_points": [500, 2000], "tau_w": [0.0, 0.5], "alpha": [0.5, 1.0]},
    "wide": {"tau_r": [0.02, 0.03, 0.05, 0.08, 0.12], "tau_n_deg": [10, 15, 25], "tau_w": [0.0, 0.25, 0.5, 0.75], "alpha": [0.25, 0.5, 0.75, 1.0]},
}
COLS = ["scene", "tag", "tau_r", "tau_n_deg", "tau_w", "alpha", "max_planes", "p2plane_cm", "plane_recall", "n_planes_scored", "n_gt_planes", "f_score", "chamfer_cm",
        "detector", "gate_scope", "refined.ransac_m", "refined.cluster_eps_m", "refined.min_points", "refined.merge_deg", "refined.merge_m", "n_gate_planes", "frac_gate_pass", "gate_s"]
METRICS = ["p2plane_cm", "plane_recall", "n_planes_scored", "n_gt_planes", "f_score", "chamfer_cm"]


def configs(grid):
    for v in itertools.product(*grid.values()):
        d = dict(zip(grid, v))
        yield "_".join(f"{k}{x}" for k, x in d.items()), d


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenes", nargs="+", required=True)
    ap.add_argument("--config", default=str(REPO / "configs" / "default.yaml"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--grid", choices=sorted(GRIDS), default="small")
    ap.add_argument("--keep", action="store_true", help="giữ refined_points.ply của từng cấu hình (mặc định xoá sau khi chấm để không đầy ổ)")
    a = ap.parse_args(argv)
    bad = set(a.scenes) - DEV
    if bad:
        print(f"[LỖI] {sorted(bad)} không thuộc tập dev {sorted(DEV)}: không quét trên tập test")
        return 1
    cfg0 = cfgmod.load_config(a.config)
    out = Path(a.out)
    ensure_dir(out.parent)
    done = set()
    if out.is_file():                                                       # chạy tiếp sau khi dừng giữa chừng
        with open(out, encoding="utf-8") as f:
            done = {(r["scene"], r["tag"]) for r in csv.DictReader(f)}
    else:
        with open(out, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=COLS).writeheader()
    n = 0
    for s in a.scenes:
        base = SceneLayout(REPO / "data" / "scenes" / "replica" / s)
        segs = ln.test_segments(ln.read_measurements(base.ground_truth / "measurements.csv"))
        gt_cams = ev.gt_camera_centers(base)
        faro = geo.load_points(base.ground_truth / "gt_points.ply")
        region = rg.build_region(base, cfg0, gt_cams, faro, load_colmap_cameras)
        plane_gt = load_plane_gt(REPO / "data" / "raw" / "replica" / s, cfgmod.require(cfg0, "eval.plane"))
        for tag, d in configs(GRIDS[a.grid]):
            if (s, tag) in done:
                continue
            lay = VariantLayout(base.root, f"sweep_{tag}" if a.keep else "sweep_tmp")
            ensure_dir(lay.fusion)
            for f in ("fused_points.ply", "fusion_log.npz"):           # fuse không phụ thuộc gate: dùng lại bằng hard link
                if not (lay.fusion / f).exists():
                    os.link(base.fusion / f, lay.fusion / f)
            cfg = copy.deepcopy(cfg0)
            for k, v in d.items():
                if k.startswith("refined."):
                    cfg["plane"]["refined"][k.split(".", 1)[1]] = v
                else:
                    cfg["plane"][k] = v
            st = run_gate(lay, cfg, lambda m: None)
            ev.cloud_path = lambda layout, name, _p=lay.plane_refinement / "refined_points.ply": _p   # shortcut: chấm đúng file của cấu hình này
            r = ev._eval_variant("sweep", lay, cfg, segs, gt_cams, faro, load_colmap_cameras, lambda m: None, region, plane_gt)
            row = {"scene": s, "tag": tag, **d, **{k: r.get(k) for k in METRICS},
                   "n_gate_planes": st["n_struct_planes"], "frac_gate_pass": st["frac_gate_pass"], "gate_s": st["seconds"]}
            with open(out, "a", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=COLS).writerow(row)
            n += 1
            if not a.keep:
                shutil.rmtree(lay.plane_refinement, ignore_errors=True)
            print(f"{s} {tag}: P2Plane {row['p2plane_cm']:.3f} cm, recall {row['plane_recall']:.3f}, F {row['f_score']:.3f}, "
                  f"{st['n_struct_planes']} mặt cổng, qua cổng {st['frac_gate_pass'] * 100:.1f}%, gate {st['seconds']} s", flush=True)
    print(f"ghi thêm {n} dòng vào {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
