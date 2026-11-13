#!/usr/bin/env python3
"""
sweep_noise.py — quét hai bộ lọc nhiễu sau fuse trên MVS d3 và chọn theo quy tắc đặt trước (M4 đợt 3). Một yếu tố một lần.

  f1  số view:   min_views ∈ {2, 3, 4, 6}
  f2  ngoại lai: std_ratio ∈ {1,0; 1,5; 2,0; 3,0} với k = 20; rồi k ∈ {10, 40} với std_ratio = 2,0 (k = 20 đã có)

Với mỗi scene đọc `proposed/fusion/fused_points.ply` (d3, chưa lọc), lọc bằng `pipeline.fusion.noise.noise_keep_mask` (đúng hàm mà `fuse` dùng khi bật khoá
`fusion.filter_*`), ghi vào `proposed/variants/noise_sweep/`, chạy `gate` và chấm hình học đúng đường của `eval` (dùng lại `sweep_thresholds.eval_context/eval_cloud`).

QUY TẮC CHỌN, đặt trước, không đổi sau khi thấy số. Trong mỗi bộ lọc chọn cấu hình NHẸ NHẤT (giữ nhiều điểm nhất, trung bình tỉ lệ giữ trên các scene) thoả đồng thời:
  1. precision trung bình của 42897599 và 42898849 tăng ≥ 0,05 so với không lọc;
  2. recall trung bình các scene giảm không quá 0,02;
  3. F trung bình không giảm quá 0,005, Chamfer trung bình không tệ hơn 5% tương đối, và scene đối chứng (42445022, 45662981, 42444738) không mất F quá 0,010.
Không cấu hình nào thoả thì GIỮ TẮT. Giảm rò rỉ: leave-one-scene-out — chọn trên các scene còn lại rồi đo trên scene bỏ ra; in cả hai.

    python scripts/sweep_noise.py --out-root data/sweeps/m4_noise
    python scripts/sweep_noise.py --summary data/sweeps/m4_noise/sweep_noise.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import pipeline  # noqa: E402,F401  (import torch trước cv2/open3d/pycolmap)

# isort: split
import numpy as np  # noqa: E402
import sweep_thresholds as st  # noqa: E402

from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402
from pipeline.common.ply import read_ply, write_ply  # noqa: E402
from pipeline.eval import geometry as geo  # noqa: E402
from pipeline.eval.variants import VariantLayout  # noqa: E402
from pipeline.fusion.noise import noise_keep_mask  # noqa: E402
from pipeline.plane_gate.stage import run_gate  # noqa: E402

SCENES = ["42897599", "42898849", "42897566", "45662981", "42445022", "42444738"]
TARGETS, CONTROLS = ["42897599", "42898849"], ["42445022", "45662981", "42444738"]
P_GAIN, R_LOSS, F_LOSS, CH_TOL, CTRL_LOSS = 0.05, 0.02, 0.005, 0.05, 0.010
# (id, bộ lọc, min_views, std_ratio, k)
CONFIGS = ([("none", "none", None, None, 20)]
           + [(f"f1_mv{m}", "f1", m, None, 20) for m in (2, 3, 4, 6)]
           + [(f"f2_s{s:g}_k20", "f2", None, s, 20) for s in (1.0, 1.5, 2.0, 3.0)]
           + [(f"f2_s2_k{k}", "f2", None, 2.0, k) for k in (10, 40)])
COLUMNS = ["scene", "config", "family", "min_views", "std_ratio", "k", "n_fused", "n_after_filter", "frac_kept", "n_final", "acc_cm", "comp_cm", "chamfer_cm",
           "precision", "recall", "f_score", "seconds", "error"]
METRICS = ["acc_cm", "comp_cm", "chamfer_cm", "precision", "recall", "f_score"]


def run_scene(root: Path, cfg: Dict, scene: str, done: Optional[set] = None, log=print) -> List[Dict]:
    ctx = st.eval_context(root, cfg, scene)
    base = ctx["base"]
    lay = VariantLayout(base.root, "noise_sweep")
    before = st._hash_dir(base.proposed)
    f = read_ply(base.fusion / "fused_points.ply")
    xyz = np.stack([f["x"], f["y"], f["z"]], axis=1).astype(np.float64)
    rows: List[Dict] = []
    for cid, fam, mv, sr, k in CONFIGS:
        if done and (scene, cid) in done:
            continue
        row = {"scene": scene, "config": cid, "family": fam, "min_views": mv, "std_ratio": sr, "k": k, "n_fused": len(xyz)}
        t0 = time.time()
        try:
            keep = noise_keep_mask(xyz, f["n_views"], mv, sr, k)
            out = lay.fusion
            out.mkdir(parents=True, exist_ok=True)
            write_ply(out / "fused_points.ply", {c: f[c][keep] for c in f})
            gate = run_gate(lay, cfg, log=lambda m: None)
            cloud = geo.load_points(lay.plane_refinement / "refined_points.ply")
            row.update(n_after_filter=int(keep.sum()), frac_kept=float(keep.mean()), n_final=int(len(cloud)), **st.eval_cloud(ctx, cloud))
            row["gate_frac"] = gate.get("frac_gate_pass")
        except Exception as e:                                         # một cấu hình lỗi không làm mất cả scene
            row["error"] = f"{type(e).__name__}: {e}"
        row["seconds"] = round(time.time() - t0, 1)
        rows.append(row)
        log(f"[noise] {scene} {cid}: giữ {row.get('frac_kept', float('nan')):.3f} P {row.get('precision', float('nan')):.3f} R {row.get('recall', float('nan')):.3f} "
            f"F {row.get('f_score', float('nan')):.3f} Chamfer {row.get('chamfer_cm', float('nan')):.1f} ({row['seconds']} s) {row.get('error', '')}")
    if st._hash_dir(base.proposed) != before:
        raise RuntimeError(f"{scene}: proposed/ bị đổi (không được xảy ra)")
    return rows


def _table(rows: List[Dict]) -> Dict[str, Dict[str, Dict]]:
    out: Dict[str, Dict[str, Dict]] = {}
    for r in rows:
        if r.get("error"):
            continue
        out.setdefault(r["scene"].split("/")[-1], {})[r["config"]] = {k: float(r[k]) for k in METRICS + ["frac_kept"]}
    return out


def passes(tab: Dict, cid: str, scenes: List[str]) -> Dict:
    """Ba nhóm điều kiện của quy tắc trên tập `scenes` (chỉ tính scene có dữ liệu cho cấu hình và cho 'none')."""
    s_all = [s for s in scenes if cid in tab.get(s, {}) and "none" in tab.get(s, {})]
    if not s_all:
        return {"ok": False}
    d = lambda s, m: tab[s][cid][m] - tab[s]["none"][m]                                            # noqa: E731
    tg = [s for s in TARGETS if s in s_all]
    dp = float(np.mean([d(s, "precision") for s in tg])) if tg else float("nan")
    dr = float(np.mean([d(s, "recall") for s in s_all]))
    df = float(np.mean([d(s, "f_score") for s in s_all]))
    ch = float(np.mean([tab[s][cid]["chamfer_cm"] for s in s_all]) / np.mean([tab[s]["none"]["chamfer_cm"] for s in s_all]) - 1.0)
    ctrl = {s: d(s, "f_score") for s in CONTROLS if s in s_all}
    ok = bool(tg and dp >= P_GAIN - 1e-12 and dr >= -R_LOSS - 1e-12 and df >= -F_LOSS - 1e-12 and ch <= CH_TOL + 1e-12 and all(v >= -CTRL_LOSS - 1e-12 for v in ctrl.values()))
    return {"ok": ok, "d_precision_targets": dp, "d_recall": dr, "d_f": df, "d_chamfer_rel": ch, "control_dF": ctrl, "frac_kept": float(np.mean([tab[s][cid]["frac_kept"] for s in s_all]))}


def choose(tab: Dict, family: str, scenes: List[str]) -> Optional[str]:
    """Cấu hình nhẹ nhất (frac_kept trung bình lớn nhất) của bộ lọc `family` thoả quy tắc trên `scenes`; None nếu không có."""
    cands = [(c[0], passes(tab, c[0], scenes)) for c in CONFIGS if c[1] == family]
    good = [(cid, r) for cid, r in cands if r["ok"]]
    return max(good, key=lambda x: x[1]["frac_kept"])[0] if good else None


def report(rows: List[Dict]) -> None:
    tab = _table(rows)
    scenes = [s for s in SCENES if s in tab]
    print(f"\nscene có dữ liệu: {scenes}")
    print("\nTrung bình theo cấu hình (so với không lọc), trên các scene có dữ liệu:")
    print(f"{'config':14s} {'giữ':>6s} {'ΔP(2 scene)':>12s} {'Δrecall':>8s} {'ΔF':>8s} {'Chamfer':>8s}  đối chứng ΔF  đạt")
    for cid, fam, *_ in CONFIGS[1:]:
        r = passes(tab, cid, scenes)
        if "d_f" not in r:
            continue
        print(f"{cid:14s} {r['frac_kept']:6.3f} {r['d_precision_targets']:+12.3f} {r['d_recall']:+8.3f} {r['d_f']:+8.4f} {r['d_chamfer_rel']:+8.1%}  "
              f"{', '.join(f'{v:+.3f}' for v in r['control_dF'].values())}  {'ĐẠT' if r['ok'] else '-'}")
    for fam in ("f1", "f2"):
        print(f"\nChọn trên cả {len(scenes)} scene, bộ lọc {fam}: {choose(tab, fam, scenes) or 'KHÔNG ĐẠT (giữ tắt)'}")
        print(f"Leave-one-scene-out, bộ lọc {fam}: (chọn trên các scene còn lại → đo trên scene bỏ ra)")
        for s in scenes:
            rest = [x for x in scenes if x != s]
            c = choose(tab, fam, rest)
            if c is None:
                print(f"   bỏ {s}: không cấu hình nào đạt trên {len(rest)} scene còn lại")
            else:
                m, n = tab[s][c], tab[s]["none"]
                print(f"   bỏ {s}: chọn {c} → trên {s}: ΔP {m['precision'] - n['precision']:+.3f}, Δrecall {m['recall'] - n['recall']:+.3f}, ΔF {m['f_score'] - n['f_score']:+.4f}, "
                      f"Chamfer {m['chamfer_cm']:.1f} so với {n['chamfer_cm']:.1f}")


def read_rows(p: Path) -> List[Dict]:
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.is_file() else []


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--scenes", nargs="+", default=SCENES, help="video_id (train/Validation; held-out bị chặn)")
    ap.add_argument("--out-root", default="data/sweeps/m4_noise")
    ap.add_argument("--summary", metavar="CSV", help="chỉ in bảng và quyết định từ CSV")
    a = ap.parse_args(argv)
    if a.summary:
        report(read_rows(Path(a.summary)))
        return 0
    root = Path(a.root)
    cfg = cfgmod.load_config(root / "configs" / "default.yaml")
    splits = sp.load_splits(root / "data" / "splits.csv")
    bad = [v for v in a.scenes if splits.get(v) not in (sp.SPLIT_TRAIN, sp.SPLIT_VAL)]
    if bad:
        print(f"[LỖI] scene không phải train/Validation (held-out bị chặn): {bad}")
        return 1
    out = Path(a.out_root) if Path(a.out_root).is_absolute() else root / a.out_root
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "sweep_noise.csv"
    done = {(r["scene"], r["config"]) for r in read_rows(csv_path) if not r.get("error")}
    for v in a.scenes:
        try:
            rows = run_scene(root, cfg, f"arkitscenes/{v}", done=done)
        except RuntimeError as e:
            print(f"[LỖI] {e}")
            return 2
        new = not csv_path.is_file()
        with open(csv_path, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            if new:
                w.writeheader()
            for r in rows:
                w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLUMNS})
    report(read_rows(csv_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
