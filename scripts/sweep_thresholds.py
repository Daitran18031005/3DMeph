#!/usr/bin/env python3
"""
sweep_thresholds.py — quét ngưỡng fusion/gate trên scene Validation để khoá tham số (kế hoạch M4, PLAN §10 và §4.9).

Quét MỘT YẾU TỐ MỖI LẦN quanh giá trị mặc định (ĐC/PLAN): `fusion.tau_e`, `fusion.tau_sigma`, `plane.tau_r`, `plane.tau_n_deg`, `plane.tau_w`, `plane.alpha`.
Mỗi cấu hình chạy `fuse` rồi `gate` vào `proposed/variants/sweep/` (không đụng `proposed/`; có băm kiểm trước/sau) và đo F-score, Chamfer của đám mây sau cổng
so với Faro bằng đúng đường của stage `eval`: phép căn Kabsch cắt tỉa theo camera B0, vùng đánh giá `eval.region.mode` (mặc định `visible_gt`), `evaluate_geometry` (có ICP cứng scale = 1).

Quy tắc chọn, CỐ ĐỊNH trước khi chạy (kế hoạch M4, người dùng duyệt 09–10/11; không chỉnh theo kết quả). Với mỗi tham số, một giá trị khác mặc định được chọn CHỈ KHI đồng thời:
  (i)   F-score trung bình trên các scene tăng ≥ `F_GAIN` (0,010) so với mặc định;
  (ii)  F-score tăng ở ≥ 2/3 số scene;
  (iii) Chamfer trung bình không tệ hơn mặc định quá `CHAMFER_TOL` (5%) tương đối.
Nhiều giá trị đạt thì lấy F-score trung bình cao nhất. Không giá trị nào đạt thì GIỮ mặc định (ĐC). Chỉ scene Validation (hoặc train để báo cáo); held-out bị chặn theo `data/splits.csv`.

Cách chạy (từ thư mục gốc repo, env 3d_metric):
    python scripts/sweep_thresholds.py --split val --out-root data/sweeps/m4_thresholds
    python scripts/sweep_thresholds.py --scenes 42445022 --out-root data/sweeps/m4_smoke      # thử trên một scene
    python scripts/sweep_thresholds.py --summary data/sweeps/m4_thresholds/sweep.csv           # chỉ in bảng và quyết định, không chạy

Mã thoát: 0 ok; 1 lỗi đầu vào; 2 phát hiện `proposed/` bị đổi (không được xảy ra).
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import math
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pipeline  # noqa: E402,F401  (import torch trước cv2/open3d/pycolmap)

# isort: split
import numpy as np  # noqa: E402

from pipeline.alignment.stage import load_colmap_cameras  # noqa: E402
from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402
from pipeline.common.io import scene_layout  # noqa: E402
from pipeline.eval import geometry as geo  # noqa: E402
from pipeline.eval import lengths as ln  # noqa: E402
from pipeline.eval import region as rg  # noqa: E402
from pipeline.eval.stage import gt_camera_centers  # noqa: E402
from pipeline.eval.variants import VariantLayout, base_layout, camera_centers  # noqa: E402
from pipeline.fusion.stage import run_fuse  # noqa: E402
from pipeline.plane_gate.stage import run_gate  # noqa: E402

GRID: Dict[str, List[float]] = {
    "fusion.tau_e": [1.0, 2.0, 4.0],
    "fusion.tau_sigma": [0.10, 0.20, 0.40],
    "plane.tau_r": [0.03, 0.05, 0.08],
    "plane.tau_n_deg": [10.0, 15.0, 25.0],
    "plane.tau_w": [0.20, 0.35, 0.50],
    "plane.alpha": [0.25, 0.50, 1.00],
}
F_GAIN, CHAMFER_TOL, MIN_SCENE_FRAC = 0.010, 0.05, 2.0 / 3.0
COLUMNS = ["scene", "param", "value", "n_gate_pass", "frac_gate_pass", "acc_cm", "comp_cm", "chamfer_cm", "precision", "recall", "f_score", "region_gt_kept_frac", "seconds", "error"]
FUSION_KEYS = ("fusion.tau_e", "fusion.tau_sigma")


def config_list(cfg: Dict) -> List[Tuple[str, Optional[float]]]:
    """[("default", None)] + mọi giá trị khác mặc định của GRID, sắp để cấu hình cùng tham số fusion đứng cạnh nhau (fuse một lần cho nhiều lần gate)."""
    out: List[Tuple[str, Optional[float]]] = [("default", None)]
    for p, vals in GRID.items():
        d = float(cfgmod.require(cfg, p))
        if not any(abs(v - d) < 1e-12 for v in vals):
            raise ValueError(f"mặc định {p} = {d} không nằm trong lưới {vals}")
        out += [(p, v) for v in vals if abs(v - d) >= 1e-12]
    return sorted(out, key=lambda x: (x[0] in FUSION_KEYS, x[0], x[1] or 0.0))


def apply(cfg: Dict, param: str, value: Optional[float]) -> Dict:
    c = copy.deepcopy(cfg)
    if param != "default":
        section, key = param.split(".")
        c[section][key] = float(value)
    return c


def _hash_dir(path: Path) -> Dict[str, str]:
    """Băm các file trực tiếp trong `proposed/` (không đệ quy vào variants/) để kiểm không bị ghi đè."""
    if not path.is_dir():
        return {}
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for d in ("fusion", "plane_refinement") for p in sorted((path / d).glob("*")) if p.is_file()}


def eval_context(root: Path, cfg: Dict, scene: str, load_cameras: Callable = load_colmap_cameras) -> Dict:
    """Chuẩn bị chấm hình học một scene đúng như stage `eval`: Kabsch cắt tỉa theo camera B0, vùng `visible_gt` dùng chung, tham số ICP."""
    vid = scene.split("/")[-1]
    base = base_layout(scene_layout(root / cfgmod.require(cfg, "paths.data_root"), "arkitscenes", vid))
    gt = gt_camera_centers(base)
    faro = geo.load_points(base.faro / "faro_scene_frame.ply")
    region = rg.build_region(base, cfg, gt, faro, load_cameras)
    k, iters = float(cfgmod.require(cfg, "eval.align.trim_k")), int(cfgmod.require(cfg, "eval.align.trim_max_iters"))
    cen = camera_centers(base, "B0", load_cameras)
    views = sorted(set(cen) & set(gt))
    r, t, _, _ = ln.kabsch_rigid_trimmed(np.array([gt[v] for v in views]), np.array([cen[v] for v in views]), k, iters)   # mô hình = R·GT + t
    voxel, delta, icp = (float(cfgmod.require(cfg, f"eval.{x}")) for x in ("voxel_m", "delta_m", "icp_max_dist_m"))
    return {"base": base, "region": region, "r": r, "t": t, "voxel": voxel, "delta": delta, "icp": icp}


def eval_cloud(ctx: Dict, cloud: np.ndarray) -> Dict:
    """acc, comp, Chamfer, precision, recall, F của một point cloud mét (đường ICP của `eval`) trong vùng đánh giá của scene."""
    region = ctx["region"]
    model_r, _ = region.filter_model((cloud - ctx["t"]) @ ctx["r"])
    g = geo.evaluate_geometry(model_r, region.faro, region.box, ctx["voxel"], ctx["delta"], ctx["icp"])["icp"]
    return {k_: g[k_] for k_ in ("acc_cm", "comp_cm", "chamfer_cm", "precision", "recall", "f_score")}


def run_scene(root: Path, cfg: Dict, scene: str, load_cameras: Callable = load_colmap_cameras, log: Callable[[str], None] = print,
              done: Optional[set] = None) -> List[Dict]:
    """Chạy mọi cấu hình của một scene, trả về danh sách dòng CSV (bỏ cấu hình có trong `done`)."""
    ctx = eval_context(root, cfg, scene, load_cameras)
    base, region = ctx["base"], ctx["region"]
    lay = VariantLayout(base.root, "sweep")
    before = _hash_dir(base.proposed)
    rows: List[Dict] = []
    fused_key: Optional[Tuple[float, float]] = None
    for param, value in config_list(cfg):
        if done and (scene, param, f"{value:g}" if value is not None else "") in done:
            continue
        c = apply(cfg, param, value)
        row = {"scene": scene, "param": param, "value": "" if value is None else f"{value:g}"}
        t0 = time.time()
        try:
            key = (float(c["fusion"]["tau_e"]), float(c["fusion"]["tau_sigma"]))
            if key != fused_key:
                run_fuse(lay, c, log=lambda m: None, load_cameras=load_cameras)
                fused_key = key
            gate = run_gate(lay, c, log=lambda m: None, load_cameras=load_cameras)
            cloud = geo.load_points(lay.plane_refinement / "refined_points.ply")
            row.update(n_gate_pass=gate.get("n_gate_pass"), frac_gate_pass=gate.get("frac_gate_pass"), region_gt_kept_frac=region.gt_kept_frac, **eval_cloud(ctx, cloud))
        except Exception as e:                                         # một cấu hình lỗi không làm mất cả scene; lỗi ghi vào CSV
            row["error"] = f"{type(e).__name__}: {e}"
        row["seconds"] = round(time.time() - t0, 1)
        rows.append(row)
        log(f"[sweep] {scene} {param}={row['value'] or 'mặc định'}: F {row.get('f_score', float('nan')):.3f} Chamfer {row.get('chamfer_cm', float('nan')):.1f} cm "
            f"qua cổng {row.get('frac_gate_pass', float('nan')):.3%} ({row['seconds']} s) {row.get('error', '')}")
    if _hash_dir(base.proposed) != before:
        raise RuntimeError(f"{scene}: proposed/ bị đổi trong lúc quét (không được xảy ra)")
    return rows


def decide(rows: List[Dict]) -> List[Dict]:
    """Áp quy tắc cố định (docstring module) lên các dòng CSV. Chỉ tính scene có đủ dữ liệu cho mặc định và giá trị đang xét."""
    ok = [r for r in rows if not r.get("error") and r.get("f_score") not in ("", None)]
    default = {r["scene"]: r for r in ok if r["param"] == "default"}
    out = []
    for p in GRID:
        by_val: Dict[str, Dict[str, Dict]] = {}
        for r in ok:
            if r["param"] == p:
                by_val.setdefault(r["value"], {})[r["scene"]] = r
        cands = []
        for v, per in sorted(by_val.items(), key=lambda kv: float(kv[0])):
            sc = sorted(set(per) & set(default))
            if not sc:
                continue
            d_f = [float(per[s]["f_score"]) - float(default[s]["f_score"]) for s in sc]
            mean_f_d = float(np.mean([float(default[s]["f_score"]) for s in sc]))
            mean_f_v = float(np.mean([float(per[s]["f_score"]) for s in sc]))
            ch_d = float(np.mean([float(default[s]["chamfer_cm"]) for s in sc]))
            ch_v = float(np.mean([float(per[s]["chamfer_cm"]) for s in sc]))
            n_better = int(sum(x > 0 for x in d_f))
            passed = (mean_f_v - mean_f_d >= F_GAIN - 1e-12 and n_better >= math.ceil(MIN_SCENE_FRAC * len(sc) - 1e-9)
                      and ch_v <= ch_d * (1.0 + CHAMFER_TOL) + 1e-12)
            cands.append({"value": v, "n_scenes": len(sc), "mean_f": mean_f_v, "mean_f_default": mean_f_d, "d_f": mean_f_v - mean_f_d, "n_better": n_better,
                          "chamfer": ch_v, "chamfer_default": ch_d, "d_chamfer_rel": ch_v / ch_d - 1.0 if ch_d else float("nan"), "passed": passed})
        good = [c for c in cands if c["passed"]]
        best = max(good, key=lambda c: c["mean_f"]) if good else None
        out.append({"param": p, "chosen": best["value"] if best else None, "candidates": cands})
    return out


def print_decisions(dec: List[Dict]) -> None:
    print(f"quy tắc: F tăng ≥ {F_GAIN}, tăng ở ≥ 2/3 scene, Chamfer không tệ hơn {CHAMFER_TOL:.0%}; không đạt thì giữ mặc định")
    for d in dec:
        print(f"{d['param']:18s} → " + (f"CHỌN {d['chosen']}" if d["chosen"] is not None else "giữ mặc định"))
        for c in d["candidates"]:
            print(f"    {c['value']:>6s}: F {c['mean_f']:.4f} ({c['d_f']:+.4f}), tốt hơn ở {c['n_better']}/{c['n_scenes']} scene, "
                  f"Chamfer {c['chamfer']:.1f} cm ({c['d_chamfer_rel']:+.1%}) {'ĐẠT' if c['passed'] else '-'}")


def read_rows(path: Path) -> List[Dict]:
    if not path.is_file():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_row(path: Path, row: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.is_file()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in COLUMNS})


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Quét ngưỡng fusion/gate trên scene Validation (M4)")
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--split", default="val", choices=["train", "val"], help="tập scene (held-out bị chặn)")
    ap.add_argument("--scenes", nargs="+", help="chỉ các video_id này (mặc định: cả tập)")
    ap.add_argument("--out-root", default="data/sweeps/m4_thresholds", help="CSV nằm ở <out-root>/sweep.csv (ngoài git)")
    ap.add_argument("--summary", metavar="CSV", help="chỉ in bảng và quyết định từ CSV, không chạy")
    args = ap.parse_args(argv)

    if args.summary:
        rows = read_rows(Path(args.summary))
        if not rows:
            print(f"[LỖI] không có dòng nào trong {args.summary}")
            return 1
        print_decisions(decide(rows))
        return 0

    root = Path(args.root)
    cfg = cfgmod.load_config(root / "configs" / "default.yaml")
    splits = sp.load_splits(root / "data" / "splits.csv")
    want = sp.SPLIT_VAL if args.split == "val" else sp.SPLIT_TRAIN
    scenes = [f"arkitscenes/{v}" for v, s in sorted(splits.items()) if s == want and (not args.scenes or v in args.scenes)]
    if not scenes:
        print("[LỖI] không có scene nào khớp (held-out bị chặn)")
        return 1
    out_root = Path(args.out_root) if Path(args.out_root).is_absolute() else root / args.out_root
    csv_path = out_root / "sweep.csv"
    done = {(r["scene"], r["param"], r["value"]) for r in read_rows(csv_path) if not r.get("error")}
    ready = [s for s in scenes if (root / cfgmod.require(cfg, "paths.data_root") / s / "ground_truth" / "faro" / "faro_scene_frame.ply").is_file()
             and (root / cfgmod.require(cfg, "paths.data_root") / s / "proposed" / "alignment" / "scale.json").is_file()]
    for s in sorted(set(scenes) - set(ready)):
        print(f"[bỏ qua] {s}: chưa có faro_scene_frame.ply hoặc proposed/alignment/scale.json (chưa căn Faro hoặc chưa chạy align)")
    if not ready:
        print("[LỖI] không scene nào đủ dữ liệu")
        return 1
    print(f"[sweep] {len(ready)} scene × {len(config_list(cfg))} cấu hình; đã có {len(done)} dòng hợp lệ trong {csv_path}")
    for s in ready:
        try:
            for row in run_scene(root, cfg, s, done=done):
                append_row(csv_path, row)
        except RuntimeError as e:
            print(f"[LỖI] {e}")
            return 2
    print_decisions(decide(read_rows(csv_path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
