#!/usr/bin/env python3
"""
compare_variants.py — bảng "trước → sau" của các biến thể thử nghiệm (M4 đợt 2) so với baseline `proposed` và B0, đủ 6 scene, kèm điều kiện nhận chung.

Baseline lấy từ `docs/evidence/m4_improve/baseline_truoc_doi/baseline.csv` (chụp trước khi sửa mã); biến thể lấy từ
`data/scenes/arkitscenes/<scene>/evaluation/variants/<name>/metrics.csv` (do `eval_variants.py` ghi). Điều kiện nhận chung (đặt trước, không đổi):
F trung bình tăng ≥ 0,010 so với baseline proposed; Chamfer trung bình không tệ hơn 5% tương đối; KHÔNG scene đối chứng (42445022, 45662981, 42444738) mất F quá 0,010.

    python scripts/compare_variants.py --names proposed_b02 proposed_b05 --out docs/evidence/m4_improve/B/summary.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "docs" / "evidence" / "m4_improve" / "baseline_truoc_doi" / "baseline.csv"
SCENES = ["42897599", "42897566", "42898849", "42445022", "45662981", "42444738"]
CONTROL = ["42445022", "45662981", "42444738"]
METRICS = ["acc_cm", "comp_cm", "precision", "recall", "f_score", "chamfer_cm"]
F_GAIN, CHAMFER_TOL, CONTROL_LOSS = 0.010, 0.05, 0.010


def load(names: List[str]) -> Dict[str, Dict[str, Dict[str, float]]]:
    """{variant: {scene: {metric: value}}}; variant gồm 'B0', 'proposed' (baseline) và các tên thử nghiệm (thiếu scene thì bỏ qua)."""
    out: Dict[str, Dict[str, Dict[str, float]]] = {"B0": {}, "proposed": {}}
    for r in csv.DictReader(open(BASE, encoding="utf-8")):
        if r["variant"] in out:
            out[r["variant"]][r["scene"]] = {m: float(r[m]) for m in METRICS}
    for n in names:
        out[n] = {}
        for s in SCENES:
            p = REPO / "data" / "scenes" / "arkitscenes" / s / "evaluation" / "variants" / n / "metrics.csv"
            if p.is_file():
                rows = list(csv.DictReader(open(p, encoding="utf-8")))
                if rows and not rows[0].get("error") and rows[0].get("f_score"):
                    out[n][s] = {m: float(rows[0][m]) for m in METRICS}
    return out


def mean(d: Dict[str, Dict[str, float]], m: str) -> float:
    return sum(d[s][m] for s in SCENES) / len(SCENES)


def verdict(data: Dict, name: str) -> Dict:
    d, b = data[name], data["proposed"]
    if any(s not in d for s in SCENES):
        return {"complete": False}
    df = mean(d, "f_score") - mean(b, "f_score")
    ch = mean(d, "chamfer_cm") / mean(b, "chamfer_cm") - 1.0
    loss = {s: d[s]["f_score"] - b[s]["f_score"] for s in CONTROL}
    ok = df >= F_GAIN - 1e-12 and ch <= CHAMFER_TOL + 1e-12 and all(v >= -CONTROL_LOSS - 1e-12 for v in loss.values())
    return {"complete": True, "d_f": df, "d_chamfer_rel": ch, "control_dF": loss, "accepted": ok}


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--names", nargs="+", required=True)
    ap.add_argument("--out", help="ghi bảng dài (scene × variant × chỉ số) ra CSV")
    a = ap.parse_args(argv)
    data = load(a.names)
    rows = []
    for v in ["B0", "proposed"] + a.names:
        for s in SCENES:
            if s in data[v]:
                rows.append({"scene": s, "variant": v, **data[v][s]})
    print(f"{'scene':10s} {'variant':14s}  acc    comp   P      R      F      Chamfer")
    for s in SCENES:
        for v in ["B0", "proposed"] + a.names:
            if s in data[v]:
                x = data[v][s]
                print(f"{s:10s} {v:14s} {x['acc_cm']:5.2f} {x['comp_cm']:6.1f} {x['precision']:6.3f} {x['recall']:6.3f} {x['f_score']:6.3f} {x['chamfer_cm']:7.2f}")
    print("\nTrung bình 6 scene (chỉ in khi đủ scene):")
    for v in ["B0", "proposed"] + a.names:
        if all(s in data[v] for s in SCENES):
            print(f"  {v:14s} F {mean(data[v], 'f_score'):.4f}  Chamfer {mean(data[v], 'chamfer_cm'):.2f}  acc {mean(data[v], 'acc_cm'):.2f}  recall {mean(data[v], 'recall'):.3f}")
    for n in a.names:
        r = verdict(data, n)
        if r["complete"]:
            print(f"\n{n}: ΔF {r['d_f']:+.4f} (cần ≥ +{F_GAIN}); Chamfer {r['d_chamfer_rel']:+.1%} (cần ≤ +{CHAMFER_TOL:.0%}); "
                  f"đối chứng ΔF {{{', '.join(f'{s}: {v:+.3f}' for s, v in r['control_dF'].items())}}} (cần ≥ −{CONTROL_LOSS}) → "
                  f"{'ĐẠT điều kiện chung' if r['accepted'] else 'KHÔNG đạt điều kiện chung'}")
        else:
            print(f"\n{n}: chưa đủ 6 scene ({sorted(data[n])})")
    if a.out:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["scene", "variant"] + METRICS)
            w.writeheader()
            w.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
