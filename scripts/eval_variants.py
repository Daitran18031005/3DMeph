#!/usr/bin/env python3
"""
eval_variants.py — chạy một BIẾN THỂ THỬ NGHIỆM của proposed (M4 đợt 2) và chấm hình học đúng đường của stage `eval`.

Với mỗi scene: `fuse` rồi `gate` với cấu hình mặc định + các `--set khoá=giá_trị` vào `proposed/variants/<name>/` (không đụng `proposed/`; có băm kiểm trước/sau),
chấm đám mây sau cổng so với Faro (Kabsch cắt tỉa theo camera B0, vùng `eval.region.mode`, ICP scale = 1: cùng hàm với `sweep_thresholds.py`)
và ghi `evaluation/variants/<name>/metrics.csv`. Chỉ scene train/Validation; held-out bị chặn theo `data/splits.csv`.

    python scripts/eval_variants.py --name proposed_b02 --scenes 42897599 42897566 --set fusion.max_shift_m=0.02
    python scripts/eval_variants.py --name check --scenes 42897599          # không --set: phải tái lập đúng số của `proposed` trong metrics.csv

Mã thoát: 0 ok; 1 lỗi đầu vào; 2 phát hiện `proposed/` bị đổi (không được xảy ra).
"""

from __future__ import annotations

import argparse
import copy
import csv
import sys
import time
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import pipeline  # noqa: E402,F401  (import torch trước cv2/open3d/pycolmap)

# isort: split
import sweep_thresholds as st  # noqa: E402
import yaml  # noqa: E402

from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402
from pipeline.eval import geometry as geo  # noqa: E402
from pipeline.eval.variants import VariantLayout  # noqa: E402
from pipeline.fusion.stage import run_fuse  # noqa: E402
from pipeline.plane_gate.stage import run_gate  # noqa: E402

COLUMNS = ["scene", "variant", "overrides", "n_points_fused", "n_points_final", "frac_gate_pass", "frac_shift_clamped", "acc_cm", "comp_cm", "chamfer_cm",
           "precision", "recall", "f_score", "region_gt_kept_frac", "seconds", "error"]


def parse_overrides(items: List[str]) -> Dict[str, object]:
    out: Dict[str, object] = {}
    for it in items:
        if "=" not in it or "." not in it.split("=")[0]:
            raise ValueError(f"--set cần dạng phần.khoá=giá_trị, nhận {it!r}")
        k, v = it.split("=", 1)
        out[k] = yaml.safe_load(v)
    return out


def apply_overrides(cfg: Dict, overrides: Dict[str, object]) -> Dict:
    c = copy.deepcopy(cfg)
    for k, v in overrides.items():
        section, key = k.split(".")
        if section not in c or key not in c[section]:
            raise KeyError(f"khoá cấu hình không có: {k} (thêm vào configs/default.yaml trước)")
        c[section][key] = v
    return c


def run_one(root: Path, cfg: Dict, scene: str, name: str, overrides: Dict[str, object], log=print) -> Dict:
    ctx = st.eval_context(root, cfg, scene)
    base = ctx["base"]
    lay = VariantLayout(base.root, name)
    before = st._hash_dir(base.proposed)
    c = apply_overrides(cfg, overrides)
    row: Dict = {"scene": scene, "variant": name, "overrides": ";".join(f"{k}={v}" for k, v in overrides.items())}
    t0 = time.time()
    try:
        fz = run_fuse(lay, c, log=lambda m: None)
        gate = run_gate(lay, c, log=lambda m: None)
        cloud = geo.load_points(lay.plane_refinement / "refined_points.ply")
        row.update(n_points_fused=fz.get("n_points_fused"), n_points_final=int(len(cloud)), frac_gate_pass=gate.get("frac_gate_pass"),
                   frac_shift_clamped=fz.get("frac_shift_clamped"), region_gt_kept_frac=ctx["region"].gt_kept_frac, **st.eval_cloud(ctx, cloud))
    except Exception as e:                                             # một scene lỗi không làm mất các scene khác
        row["error"] = f"{type(e).__name__}: {e}"
    row["seconds"] = round(time.time() - t0, 1)
    if st._hash_dir(base.proposed) != before:
        raise RuntimeError(f"{scene}: proposed/ bị đổi (không được xảy ra)")
    out = lay.evaluation / "variants" / name / "metrics.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in COLUMNS})
    log(f"[variant] {scene} {name}: F {row.get('f_score', float('nan')):.3f} acc {row.get('acc_cm', float('nan')):.2f} comp {row.get('comp_cm', float('nan')):.1f} "
        f"P {row.get('precision', float('nan')):.3f} R {row.get('recall', float('nan')):.3f} Chamfer {row.get('chamfer_cm', float('nan')):.1f} cm ({row['seconds']} s) {row.get('error', '')}")
    return row


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--name", required=True, help="tên biến thể = thư mục proposed/variants/<name>/ (không dùng 'sweep', 'abl_quality')")
    ap.add_argument("--scenes", nargs="+", required=True, help="video_id (train hoặc Validation)")
    ap.add_argument("--set", dest="sets", action="append", default=[], metavar="KHOÁ=GIÁ_TRỊ", help="ghi đè cấu hình, ví dụ fusion.max_shift_m=0.02 (lặp được)")
    args = ap.parse_args(argv)
    if args.name in ("sweep", "abl_quality", "proposed"):
        print(f"[LỖI] tên biến thể {args.name!r} đã dùng cho việc khác")
        return 1
    root = Path(args.root)
    cfg = cfgmod.load_config(root / "configs" / "default.yaml")
    splits = sp.load_splits(root / "data" / "splits.csv")
    bad = [v for v in args.scenes if splits.get(v) not in (sp.SPLIT_TRAIN, sp.SPLIT_VAL)]
    if bad:
        print(f"[LỖI] scene không phải train/Validation (held-out bị chặn) hoặc không có trong splits.csv: {bad}")
        return 1
    try:
        overrides = parse_overrides(args.sets)
        apply_overrides(cfg, overrides)
    except (ValueError, KeyError) as e:
        print(f"[LỖI] {e}")
        return 1
    rc = 0
    for v in args.scenes:
        try:
            if run_one(root, cfg, f"arkitscenes/{v}", args.name, overrides).get("error"):
                rc = 1
        except RuntimeError as e:
            print(f"[LỖI] {e}")
            return 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
