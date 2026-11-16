#!/usr/bin/env python3
"""
aggregate_eval.py — gộp `evaluation/metrics.csv` của từng scene thành bảng chéo scene ở `outputs/eval_results/` (chỉ đọc, M4).

Bảng Validation và scene dev (train) tách riêng; scene held-out bị bỏ qua (chưa chạy, và không được gộp trước lượt chạy duy nhất).
Kèm sai số chiều dài bán tự động (bán kính 5 cm, Kabsch, đủ mẫu số) từ `--length-csv` (`scripts/length_error.py`, per_scene.csv) nếu có.

    python scripts/aggregate_eval.py --length-csv docs/evidence/m4_improve/length_error_doimoc/kabsch/per_scene.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from pipeline.common import splits as sp  # noqa: E402

GEOM = ["acc_cm", "comp_cm", "chamfer_cm", "precision", "recall", "f_score", "ate_rigid_cm", "ate_sim3_cm"]
LEN = ["n_test", "n_valid", "median_cm", "mae_cm", "pct_lt5cm"]


def read(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8")))


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenes-root", default=str(REPO / "data" / "scenes" / "arkitscenes"))
    ap.add_argument("--length-csv")
    ap.add_argument("--exclude", nargs="*", default=["47204552"], help="scene loại khỏi bảng (mặc định 47204552: SfM vỡ, người dùng đồng ý loại)")
    ap.add_argument("--out", default=str(REPO / "outputs" / "eval_results"))
    a = ap.parse_args(argv)
    splits = sp.load_splits(REPO / "data" / "splits.csv")
    length = {(r["scene"], r["variant"]): r for r in read(Path(a.length_csv))} if a.length_csv else {}
    rows = []
    for m in sorted(Path(a.scenes_root).glob("*/evaluation/metrics.csv")):
        sc = m.parts[-3]
        split = splits.get(sc)
        if split not in (sp.SPLIT_TRAIN, sp.SPLIT_VAL) or sc in a.exclude:          # held-out: không gộp
            continue
        for r in read(m):
            lr = length.get((sc, r["variant"]), {})
            rows.append({"split": split, "scene": sc, "variant": r["variant"], **{k: r.get(k, "") for k in GEOM}, **{f"len5_{k}": lr.get(k, "") for k in LEN}})
    assert rows, "không thấy metrics.csv nào"
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    keys = list(rows[0])
    with open(out / "per_scene.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    summ = []
    for split in (sp.SPLIT_VAL, sp.SPLIT_TRAIN):
        for v in dict.fromkeys(r["variant"] for r in rows):
            g = [r for r in rows if r["split"] == split and r["variant"] == v]
            if not g:
                continue
            s = {"split": split, "variant": v, "n_scenes": len(g), **{k: round(float(np.nanmean([num(r[k]) for r in g])), 4) for k in GEOM}}
            nt, nv = np.nansum([num(r["len5_n_test"]) for r in g]), np.nansum([num(r["len5_n_valid"]) for r in g])
            s.update(len5_valid=f"{nv:.0f}/{nt:.0f}" if nt > 0 else "")
            summ.append(s)
    with open(out / "summary.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0]))
        w.writeheader()
        w.writerows(summ)
    for s in summ:
        print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
