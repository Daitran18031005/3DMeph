"""replica_test_stats.py — bảng và kiểm định plane gate trên 8 scene test Replica (lệch #53, quy tắc đặt trước).

Đạt mục tiêu ĐC §21 khi trung bình ΔP2Plane (so với B3) ≤ −15% **và** trung bình ΔF ≥ −0,01. Kèm Wilcoxon một phía theo scene
(H1: P2Plane biến thể < B3) và khoảng tin cậy bootstrap 95% của ΔP2Plane trung bình (10 000 lần, seed 0).

Dùng: python scripts/replica_test_stats.py --out outputs/eval_results/replica_test8_gate.csv
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

REPO = Path(__file__).resolve().parents[1]
TEST = ["room_0", "room_1", "room_2", "office_0", "office_1", "office_2", "office_3", "office_4"]
VARIANTS = ["proposed", "refined_struct", "refined_all", "abl_gate"]


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    rows = []
    for s in TEST:
        m = pd.read_csv(REPO / "data" / "scenes" / "replica" / s / "evaluation" / "metrics.csv").set_index("variant")
        b3 = m.loc["B3"]
        for v in VARIANTS:
            if v not in m.index:
                print(f"[CẢNH BÁO] {s}: thiếu {v}")
                continue
            r = m.loc[v]
            rows.append({"scene": s, "variant": v, "p2plane_b3": b3.p2plane_cm, "p2plane": r.p2plane_cm,
                         "d_p2plane_pct": 100 * (r.p2plane_cm - b3.p2plane_cm) / b3.p2plane_cm, "f_b3": b3.f_score, "f": r.f_score,
                         "d_f": r.f_score - b3.f_score, "d_recall": r.plane_recall - b3.plane_recall})
    d = pd.DataFrame(rows)
    d.to_csv(a.out, index=False)
    print(d.pivot(index="scene", columns="variant", values="d_p2plane_pct").round(2).to_string())
    rng = np.random.default_rng(0)
    for v in VARIANTS:
        x = d[d.variant == v]
        if len(x) < len(TEST):
            print(f"{v}: chỉ {len(x)}/{len(TEST)} scene, bỏ qua kiểm định")
            continue
        dp, df = x.d_p2plane_pct.to_numpy(), x.d_f.to_numpy()
        p = wilcoxon(x.p2plane - x.p2plane_b3, alternative="less").pvalue
        boot = rng.choice(dp, (10000, len(dp))).mean(axis=1)
        lo, hi = np.percentile(boot, [2.5, 97.5])
        ok = dp.mean() <= -15 and df.mean() >= -0.01
        print(f"{v}: ΔP2Plane TB {dp.mean():+.2f}% (CI95 {lo:+.2f}…{hi:+.2f}), thắng {int((dp < 0).sum())}/{len(dp)} scene, Wilcoxon một phía p = {p:.4f}; "
              f"ΔF TB {df.mean():+.4f} (min {df.min():+.4f}) ⇒ {'ĐẠT' if ok else 'KHÔNG ĐẠT'} quy tắc (≤ −15% và ΔF ≥ −0,01)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
