#!/usr/bin/env python3
"""
gate_variants.py — chạy các biến thể của stage `gate` (M4 đợt 3d) và chấm bằng chỉ số của chính cổng + F-score/Chamfer; áp quy tắc nhận ĐẶT TRƯỚC
(`docs/evidence/m4_improve/gate_fix/PLAN.md`).

Fusion không đổi (đọc `proposed/fusion` hiện có); mỗi biến thể chỉ chạy lại `gate`, ghi vào `proposed/variants/<tên>/plane_refinement/` (không đụng `proposed/`, có băm kiểm).
Đáp án Faro căn như `eval`: Kabsch cắt tỉa theo camera B0, rồi ICP cứng MỘT lần trên cloud chưa qua cổng, dùng chung cho mọi biến thể (cô lập tác động của cổng).

    python scripts/gate_variants.py --preset core --out-root data/sweeps/m4_gate         # gate_base, gate_A, gate_Ab, gate_B100, gate_B300 trên 6 scene
    python scripts/gate_variants.py --name gate_AB --set plane.floor_rule=lowest plane.floor_band_m=0 plane.min_walls=1 plane.gate_normal_knn=100 --out-root data/sweeps/m4_gate
    python scripts/gate_variants.py --summary data/sweeps/m4_gate/gate_variants.csv     # chỉ in bảng và quyết định
"""

from __future__ import annotations

import argparse
import copy
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import pipeline  # noqa: E402,F401  (import torch trước cv2/open3d/pycolmap)

# isort: split
import numpy as np  # noqa: E402
import sweep_thresholds as st  # noqa: E402
import yaml  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402
from pipeline.common.io import read_json  # noqa: E402
from pipeline.common.ply import read_ply  # noqa: E402
from pipeline.eval.geometry import icp_rigid, voxel_downsample  # noqa: E402
from pipeline.eval.variants import VariantLayout  # noqa: E402
from pipeline.plane_gate.stage import run_gate  # noqa: E402

SCENES = ["42897599", "42898849", "42897566", "45662981", "42445022", "42444738"]
A_SET = {"plane.floor_rule": "lowest", "plane.floor_band_m": 0.0, "plane.min_walls": 1, "plane.extra_wall_passes": 4}
PRESETS = {"gate_base": {}, "gate_A": A_SET, "gate_Ab": {**A_SET, "plane.floor_band_m": 0.10},
           "gate_B100": {"plane.gate_normal_knn": 100}, "gate_B300": {"plane.gate_normal_knn": 300}}
COLUMNS = ["scene", "variant", "n_floor", "n_wall", "n_ceiling", "n_horizontal_other", "n_other", "n_floor_far", "pass_frac", "theta_cond_frac", "n_passed", "acc_passed",
           "acc_all", "med_before_cm", "med_after_cm", "frac_improved", "acc_cm", "comp_cm", "chamfer_cm", "precision", "recall", "f_score", "seconds", "error"]
DELTA_F, DELTA_CH, DELTA_F_SCENE, DELTA_ACC, DELTA_IMP, THETA_GAIN = -0.005, 0.02, -0.010, -0.02, -0.02, 1.5       # ngưỡng của quy tắc đặt trước (PLAN.md §4)


@dataclass(frozen=True)
class GateVariantLayout(VariantLayout):
    """Như `VariantLayout` nhưng `fusion` trỏ về `proposed/fusion` gốc: chỉ `gate` chạy lại, đầu ra ở `proposed/variants/<tên>/plane_refinement`."""

    @property
    def fusion(self) -> Path:
        return self.proposed / "fusion"


def apply_overrides(cfg: Dict, overrides: Dict[str, object]) -> Dict:
    c = copy.deepcopy(cfg)
    for k, v in overrides.items():
        section, key = k.split(".")
        if key not in c[section]:
            raise KeyError(f"khoá cấu hình không có: {k}")
        c[section][key] = v
    return c


def run_scene(root: Path, cfg: Dict, scene: str, variants: Dict[str, Dict], done: Optional[set] = None, log=print) -> List[Dict]:
    ctx = st.eval_context(root, cfg, f"arkitscenes/{scene}")
    base = ctx["base"]
    before_hash = st._hash_dir(base.proposed)
    f0 = read_ply(base.fusion / "fused_points.ply")
    xyz = np.stack([f0["x"], f0["y"], f0["z"]], axis=1).astype(np.float64)
    r_mat, t_vec, faro = ctx["r"], ctx["t"], ctx["region"].faro
    icp_t, _ = icp_rigid(voxel_downsample((xyz - t_vec) @ r_mat, ctx["voxel"]), voxel_downsample(faro, ctx["voxel"]), ctx["icp"])
    tree = cKDTree(faro)

    def dist(p):
        return tree.query(((p - t_vec) @ r_mat) @ icp_t[:3, :3].T + icp_t[:3, 3])[0]

    d_before = dist(xyz)
    rows: List[Dict] = []
    for name, ov in variants.items():
        if done and (scene, name) in done:
            continue
        row: Dict = {"scene": scene, "variant": name}
        t0 = time.time()
        try:
            c = apply_overrides(cfg, ov)
            lay = GateVariantLayout(base.root, name)
            stats = run_gate(lay, c, log=lambda m: None)
            ref = read_ply(lay.plane_refinement / "refined_points.ply")
            xyz2 = np.stack([ref["x"], ref["y"], ref["z"]], axis=1).astype(np.float64)
            g = ref["g"].astype(bool)
            d_after = dist(xyz2)
            planes = read_json(lay.plane_refinement / "planes.json")["planes"]
            lab = [p["label"] for p in planes]
            band = float(c["plane"]["floor_band_m"]) if c["plane"]["floor_rule"] == "lowest" else 0.0
            fl = [p["height_m"] for p in planes if p["label"] == "floor"]
            row.update(n_floor=lab.count("floor"), n_wall=lab.count("wall"), n_ceiling=lab.count("ceiling"), n_horizontal_other=lab.count("horizontal_other"), n_other=lab.count("other"),
                       n_floor_far=int(sum(h - min(fl) > band + 1e-9 for h in fl)) if fl else 0, pass_frac=float(g.mean()),
                       theta_cond_frac=stats["condition_pass_fraction"]["theta<tau_n"], n_passed=int(g.sum()), acc_all=float((d_before <= 0.05).mean()),
                       acc_passed=float((d_before[g] <= 0.05).mean()) if g.any() else None,
                       med_before_cm=float(np.median(d_before[g]) * 100) if g.any() else None, med_after_cm=float(np.median(d_after[g]) * 100) if g.any() else None,
                       frac_improved=float((d_after[g] < d_before[g] - 1e-6).mean()) if g.any() else None, **st.eval_cloud(ctx, xyz2))
        except Exception as e:                                                  # một biến thể lỗi không làm mất cả scene
            row["error"] = f"{type(e).__name__}: {e}"
        row["seconds"] = round(time.time() - t0, 1)
        rows.append(row)
        log(f"[gate-var] {scene} {name}: qua cổng {row.get('pass_frac', float('nan')):.4f}, chính xác điểm qua {row.get('acc_passed') or float('nan'):.3f}, "
            f"F {row.get('f_score', float('nan')):.3f}, sàn/tường/ngang khác {row.get('n_floor')}/{row.get('n_wall')}/{row.get('n_horizontal_other')} ({row['seconds']} s) {row.get('error', '')}")
    if st._hash_dir(base.proposed) != before_hash:
        raise RuntimeError(f"{scene}: proposed/ bị đổi (không được xảy ra)")
    return rows


def _tab(rows: List[Dict]) -> Dict[str, Dict[str, Dict[str, float]]]:
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    for r in rows:
        if r.get("error"):
            continue
        out.setdefault(r["variant"], {})[r["scene"]] = {k: (float(v) if v not in ("", None) else float("nan")) for k, v in r.items() if k not in ("scene", "variant", "error")}
    return out


def _mean(d: Dict[str, Dict[str, float]], k: str, scenes: List[str]) -> float:
    return float(np.nanmean([d[s][k] for s in scenes]))


def check(tab: Dict, name: str, base: str = "gate_base", scenes: Optional[List[str]] = None) -> Dict:
    """Điều kiện của quy tắc (PLAN.md §4) cho biến thể `name` so với `base` trên các scene có đủ dữ liệu ở cả hai."""
    v, b = tab.get(name, {}), tab.get(base, {})
    sc = [s for s in (scenes or SCENES) if s in v and s in b]
    if not sc:
        return {"complete": False}
    n_imp = lambda d: sum(d[s]["med_after_cm"] < d[s]["med_before_cm"] for s in sc)                  # noqa: E731
    dF = {s: v[s]["f_score"] - b[s]["f_score"] for s in sc}
    res = {"complete": len(sc) == len(SCENES), "scenes": sc,
           "A1_tuong_va_san": all(v[s]["n_wall"] >= 1 and v[s]["n_floor_far"] == 0 for s in sc),
           "A2_acc_passed_d": _mean(v, "acc_passed", sc) - _mean(b, "acc_passed", sc),
           "A3_scenes_improved": (n_imp(v), n_imp(b)), "A3_frac_improved_d": _mean(v, "frac_improved", sc) - _mean(b, "frac_improved", sc),
           "A4_dF": float(np.mean(list(dF.values()))), "A4_dChamfer_rel": _mean(v, "chamfer_cm", sc) / _mean(b, "chamfer_cm", sc) - 1.0, "A4_worst_scene_dF": min(dF.values()),
           "B1_theta_ratio": _mean(v, "theta_cond_frac", sc) / _mean(b, "theta_cond_frac", sc), "pass_frac_ratio": _mean(v, "pass_frac", sc) / _mean(b, "pass_frac", sc)}
    res["A2"] = res["A2_acc_passed_d"] >= DELTA_ACC - 1e-12
    res["A3"] = res["A3_scenes_improved"][0] >= res["A3_scenes_improved"][1] and res["A3_frac_improved_d"] >= DELTA_IMP - 1e-12
    res["A4"] = res["A4_dF"] >= DELTA_F - 1e-12 and res["A4_dChamfer_rel"] <= DELTA_CH + 1e-12 and res["A4_worst_scene_dF"] >= DELTA_F_SCENE - 1e-12
    res["B1"] = res["B1_theta_ratio"] >= THETA_GAIN - 1e-12
    res["label_fix_ok"] = bool(res["A1_tuong_va_san"] and res["A2"] and res["A3"] and res["A4"])                  # quy tắc nhãn (A, Ab)
    res["knn_ok"] = bool(res["B1"] and res["A2"] and res["A3"] and res["A4"])                                     # quy tắc pháp tuyến (B100, B300)
    res["combo_ok"] = bool(res["A1_tuong_va_san"] and res["A2"] and res["A3"] and res["A4"])                      # quy tắc tổ hợp (AB)
    return res


def report(rows: List[Dict]) -> None:
    tab = _tab(rows)
    print(f"{'scene':9s} {'biến thể':10s} sàn/tường/trần/ngangkhác far  qua%   θ%   n_qua  chính xác(qua) trước→sau cm  cải thiện   F      Chamfer  P     R")
    for s in SCENES:
        for name in tab:
            m = tab[name].get(s)
            if m:
                print(f"{s:9s} {name:10s} {m['n_floor']:.0f}/{m['n_wall']:.0f}/{m['n_ceiling']:.0f}/{m['n_horizontal_other']:.0f} {m['n_floor_far']:.0f}   {m['pass_frac'] * 100:5.2f} {m['theta_cond_frac'] * 100:5.1f} "
                      f"{m['n_passed']:7.0f}  {m['acc_passed']:.3f}   {m['med_before_cm']:.2f}→{m['med_after_cm']:.2f}   {m['frac_improved']:.2f}   {m['f_score']:.3f}  {m['chamfer_cm']:.2f}   {m['precision']:.3f} {m['recall']:.3f}")
    print()
    for name in tab:
        if name == "gate_base":
            continue
        r = check(tab, name)
        if not r.get("scenes"):
            continue
        print(f"{name}: {'đủ 6 scene' if r['complete'] else 'chưa đủ scene ' + str(r['scenes'])}; tường&sàn đúng {r['A1_tuong_va_san']}; Δchính xác điểm qua {r['A2_acc_passed_d']:+.3f} ({'đạt' if r['A2'] else 'KHÔNG'}); "
              f"scene cải thiện {r['A3_scenes_improved'][0]} so với {r['A3_scenes_improved'][1]}, Δtỉ lệ cải thiện {r['A3_frac_improved_d']:+.3f} ({'đạt' if r['A3'] else 'KHÔNG'}); "
              f"ΔF {r['A4_dF']:+.4f}, ΔChamfer {r['A4_dChamfer_rel']:+.1%}, ΔF xấu nhất {r['A4_worst_scene_dF']:+.3f} ({'đạt' if r['A4'] else 'KHÔNG'}); "
              f"θ ×{r['B1_theta_ratio']:.2f} ({'đạt' if r['B1'] else 'KHÔNG'}), qua cổng ×{r['pass_frac_ratio']:.2f}")
        print(f"    → quy tắc nhãn: {'NHẬN' if r['label_fix_ok'] else 'không nhận'}; quy tắc pháp tuyến: {'NHẬN' if r['knn_ok'] else 'không nhận'}; quy tắc tổ hợp: {'NHẬN' if r['combo_ok'] else 'không nhận'}")


def read_rows(p: Path) -> List[Dict]:
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.is_file() else []


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--scenes", nargs="+", default=SCENES)
    ap.add_argument("--preset", choices=["core"], help="gate_base, gate_A, gate_Ab, gate_B100, gate_B300")
    ap.add_argument("--name", help="tên biến thể riêng (cùng --set)")
    ap.add_argument("--set", nargs="*", default=[], metavar="KHOÁ=GIÁ_TRỊ")
    ap.add_argument("--out-root", default="data/sweeps/m4_gate")
    ap.add_argument("--summary", metavar="CSV")
    a = ap.parse_args(argv)
    if a.summary:
        report(read_rows(Path(a.summary)))
        return 0
    variants: Dict[str, Dict] = dict(PRESETS) if a.preset else {}
    if a.name:
        if a.name in PRESETS or a.name in ("proposed", "abl_quality", "strict_old"):
            print(f"[LỖI] tên {a.name!r} đã dùng")
            return 1
        variants[a.name] = {k: yaml.safe_load(v) for k, v in (x.split("=", 1) for x in a.set)}
    if not variants:
        print("[LỖI] cần --preset core hoặc --name")
        return 1
    root = Path(a.root)
    cfg = cfgmod.load_config(root / "configs" / "default.yaml")
    splits = sp.load_splits(root / "data" / "splits.csv")
    bad = [v for v in a.scenes if splits.get(v) not in (sp.SPLIT_TRAIN, sp.SPLIT_VAL)]
    if bad:
        print(f"[LỖI] scene không phải train/Validation (held-out bị chặn): {bad}")
        return 1
    out = Path(a.out_root) if Path(a.out_root).is_absolute() else root / a.out_root
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "gate_variants.csv"
    done = {(r["scene"], r["variant"]) for r in read_rows(csv_path) if not r.get("error")}
    for sc in a.scenes:
        try:
            rows = run_scene(root, cfg, sc, variants, done=done)
        except RuntimeError as e:
            print(f"[LỖI] {e}")
            return 2
        new = not csv_path.is_file()
        with open(csv_path, "a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
            if new:
                w.writeheader()
            for r in rows:
                w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLUMNS})
    report(read_rows(csv_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
