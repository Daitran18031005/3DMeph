#!/usr/bin/env python3
"""
sweep_keyframe.py — quét ngưỡng keyframe trên các scene Validation (kế hoạch M2): với mỗi (scene, cấu hình) chạy `keyframe` rồi `sfm`, ghi N_kf, tỉ lệ ảnh
đăng ký SfM, peak VRAM vào CSV, rồi chọn cấu hình theo quy tắc cố định (xem `choose_config`). Chỉ đọc raw; ghi ra `--out-root` (ngoài git), xoá thư mục chạy
sau mỗi lần để tiết kiệm đĩa (trừ khi `--keep`). Có thể chạy lại: các dòng đã có trong CSV được bỏ qua.

Cách chạy (từ thư mục gốc repo, env 3d_metric, cần GPU cho SfM):
    python scripts/sweep_keyframe.py --split val --out-root data/sweeps/grid1 --q-drop 0.2 0.35 0.5 --overlap-max 0.7 0.8 0.9
    python scripts/sweep_keyframe.py --summary data/sweeps/grid1/sweep.csv                  # chỉ tóm tắt và chọn, không chạy

Quy tắc chọn (cố định trước khi chạy, không chỉnh theo kết quả): chỉ xét cấu hình không lỗi, có 40 ≤ N_kf ≤ 80 ở MỌI scene và KHÔNG phải thưa đều
ở scene nào (thưa đều làm đứt chuỗi SfM, không tính là bộ lọc hợp lệ); trong số đó lấy
cấu hình có TRUNG VỊ tỉ lệ đăng ký (qua scene; mỗi scene lấy trung bình các lần lặp) cao nhất; hoà thì ít keyframe tổng hơn, rồi q_drop thấp hơn.
Đạt M2 khi trung vị ≥ 90%. Không cấu hình nào đủ điều kiện thì in số thật và thoát mã 2 (không tự hạ tiêu chí).

Mã thoát: 0 đã chọn được; 1 lỗi đầu vào; 2 không cấu hình nào đủ điều kiện.
"""

from __future__ import annotations

import argparse
import copy
import csv
import itertools
import shutil
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pipeline  # noqa: E402,F401  (import torch trước cv2/open3d/pycolmap)

# isort: split
import numpy as np  # noqa: E402

from pipeline import run as pr  # noqa: E402
from pipeline.colmap.run_colmap import run_sfm  # noqa: E402
from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402
from pipeline.common.errors import StageError  # noqa: E402
from pipeline.keyframe.extract import extract_keyframes  # noqa: E402

COLUMNS = ["scene", "cfg_id", "q_drop", "overlap_max", "overlap_min", "exposure_q_drop", "rep", "n_frames", "n_candidates", "n_after_blur", "n_after_exposure",
           "n_after_overlap", "n_overlap_breaks", "thinned", "n_kf", "n_registered", "ratio", "n_models", "n_points3D", "reproj_px", "keyframe_s", "sfm_s",
           "sfm_peak_vram_mib", "error"]
N_MIN, N_MAX = 40, 80


def cfg_id(q_drop: float, o_max: float, o_min: float, exp_drop: float, target_max: Optional[int] = None) -> str:
    return f"q{q_drop:g}_omax{o_max:g}_omin{o_min:g}_e{exp_drop:g}" + (f"_t{target_max}" if target_max else "")


def make_cfg(base: Dict, out_root: Path, q_drop: float, o_max: float, o_min: float, exp_drop: float, target_max: Optional[int] = None) -> Dict:
    cfg = copy.deepcopy(base)
    if target_max:
        cfg["keyframe"]["target_max"] = int(target_max)
    cfg["keyframe"]["blur"]["q_drop"] = q_drop
    cfg["keyframe"]["overlap"] = {"max": o_max, "min": o_min}
    cfg["keyframe"]["exposure"]["q_drop"] = exp_drop
    cfg["paths"]["data_root"] = str(out_root / cfg_id(q_drop, o_max, o_min, exp_drop, target_max))
    return cfg


def read_rows(path: Path) -> List[Dict]:
    if not path.is_file():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_row(path: Path, row: Dict) -> None:
    new = not path.is_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in COLUMNS})


def run_one(root: Path, base_cfg: Dict, out_root: Path, scene: str, q_drop: float, o_max: float, o_min: float, exp_drop: float, rep: int,
            keep: bool = False, log: Callable[[str], None] = lambda m: None, sfm: bool = True, target_max: Optional[int] = None) -> Dict:
    """keyframe + sfm cho một (scene, cấu hình, lần lặp). Lỗi stage được ghi vào cột `error`, không ném."""
    cfg = make_cfg(base_cfg, out_root, q_drop, o_max, o_min, exp_drop, target_max)
    info = pr.resolve_scene(root, scene, cfg)
    layout = info["layout"]
    row: Dict = {"scene": scene, "cfg_id": cfg_id(q_drop, o_max, o_min, exp_drop, target_max), "q_drop": q_drop, "overlap_max": o_max, "overlap_min": o_min,
                 "exposure_q_drop": exp_drop, "rep": rep}
    if layout.root.exists():
        shutil.rmtree(layout.root)
    try:
        t0 = time.time()
        st = extract_keyframes(info["raw_dir"], layout, cfg, info["sky_direction"], log=log)
        row.update(n_frames=st["n_frames"], n_candidates=st["n_candidates"], n_after_blur=st["n_after_blur"], n_after_exposure=st["n_after_exposure"],
                   n_after_overlap=st["n_after_overlap"], n_overlap_breaks=st["n_overlap_breaks"], thinned=0,
                   n_kf=st["n_dense"], keyframe_s=round(time.time() - t0, 1))        # n_kf = tập dày; sau SfM thay bằng số keyframe đã chọn
        if not sfm:
            return row
        sf = run_sfm(layout, cfg, cfgmod.resolve_colmap_exe(cfg), log)
        row.update(n_kf=sf["n_keyframes"], n_registered=sf["n_registered"], ratio=round(sf["registered_ratio"], 4), n_models=sf["n_models"], n_points3D=sf["n_points3D"],
                   reproj_px=sf["mean_reproj_error_px"], sfm_s=sf["seconds"], sfm_peak_vram_mib=sf["peak_vram_mib"])
    except StageError as e:
        row["error"] = e.code
    finally:
        if not keep and layout.root.exists():
            shutil.rmtree(layout.root, ignore_errors=True)
    return row


def summarize(rows: Sequence[Dict]) -> List[Dict]:
    """Gộp theo cấu hình: N_kf min/trung vị/max qua scene, trung vị và min tỉ lệ đăng ký (trung bình các lần lặp trong mỗi scene), cờ đủ điều kiện."""
    by_cfg: Dict[str, List[Dict]] = {}
    for r in rows:
        by_cfg.setdefault(r["cfg_id"], []).append(r)
    out = []
    for cid, rs in by_cfg.items():
        scenes = sorted({r["scene"] for r in rs})
        per_scene = []
        for s in scenes:
            rr = [r for r in rs if r["scene"] == s]
            bad = any(r.get("error") for r in rr)
            nkf = float(np.mean([float(r["n_kf"]) for r in rr if r.get("n_kf") not in ("", None)])) if any(r.get("n_kf") not in ("", None) for r in rr) else float("nan")
            ratio = float(np.mean([float(r["ratio"]) for r in rr if r.get("ratio") not in ("", None)])) if any(r.get("ratio") not in ("", None) for r in rr) else float("nan")
            thin = any(str(r.get("thinned")) in ("1", "True") for r in rr)
            per_scene.append({"scene": s, "error": bad, "n_kf": nkf, "ratio": ratio, "thinned": thin})
        nk = [p["n_kf"] for p in per_scene]
        ra = [p["ratio"] for p in per_scene]
        ok = (bool(per_scene) and not any(p["error"] or p["thinned"] for p in per_scene) and all(N_MIN <= n <= N_MAX for n in nk if n == n)
              and not any(n != n for n in nk))
        first = rs[0]
        out.append({"cfg_id": cid, "q_drop": float(first["q_drop"]), "overlap_max": float(first["overlap_max"]), "overlap_min": float(first["overlap_min"]),
                    "exposure_q_drop": float(first["exposure_q_drop"]), "n_scenes": len(scenes), "n_kf_min": float(np.nanmin(nk)), "n_kf_median": float(np.nanmedian(nk)),
                    "n_kf_max": float(np.nanmax(nk)), "n_kf_total": float(np.nansum(nk)), "ratio_median": float(np.nanmedian(ra)) if not np.all(np.isnan(ra)) else float("nan"),
                    "ratio_min": float(np.nanmin(ra)) if not np.all(np.isnan(ra)) else float("nan"), "all_in_range": ok, "per_scene": per_scene})
    return out


def choose_config(summary: Sequence[Dict], n_scenes: Optional[int] = None) -> Optional[Dict]:
    """Quy tắc chọn đã nêu ở đầu file; trả về dòng tóm tắt thắng hoặc None. `n_scenes`: bỏ cấu hình chưa chạy đủ số scene này."""
    cand = [s for s in summary if s["all_in_range"] and (n_scenes is None or s["n_scenes"] == n_scenes) and s["ratio_median"] == s["ratio_median"]]
    if not cand:
        return None
    return sorted(cand, key=lambda s: (-round(s["ratio_median"], 6), s["n_kf_total"], s["q_drop"]))[0]


def print_summary(summary: Sequence[Dict], n_scenes: Optional[int] = None) -> Optional[Dict]:
    print("cfg_id | số scene | N_kf min/trung vị/max | số scene phải thưa đều | tỉ lệ đăng ký trung vị / min | N_kf ∈ [40, 80] mọi scene và không thưa đều")
    for s in sorted(summary, key=lambda s: (s["q_drop"], s["overlap_max"], s["overlap_min"])):
        n_thin = sum(1 for p in s["per_scene"] if p["thinned"])
        ratio = "chưa chạy SfM" if s["ratio_median"] != s["ratio_median"] else f"{s['ratio_median'] * 100:.1f}% / {s['ratio_min'] * 100:.1f}%"
        print(f"{s['cfg_id']} | {s['n_scenes']} | {s['n_kf_min']:.0f}/{s['n_kf_median']:.0f}/{s['n_kf_max']:.0f} | {n_thin} | {ratio} | {'có' if s['all_in_range'] else 'không'}")
    best = choose_config(summary, n_scenes)
    if best is None:
        print("KHÔNG có cấu hình nào đủ điều kiện (N_kf ∈ [40, 80] ở mọi scene, không lỗi).")
        return None
    print(f"Chọn: {best['cfg_id']} (trung vị tỉ lệ đăng ký {best['ratio_median'] * 100:.1f}%, min {best['ratio_min'] * 100:.1f}%, N_kf {best['n_kf_min']:.0f}–{best['n_kf_max']:.0f}); "
          f"{'ĐẠT' if best['ratio_median'] >= 0.9 else 'CHƯA đạt'} tiêu chí trung vị ≥ 90%")
    for p in best["per_scene"]:
        print(f"   {p['scene']}: N_kf {p['n_kf']:.1f}, đăng ký {p['ratio'] * 100:.1f}%")
    return best


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Quét ngưỡng keyframe trên scene Validation (keyframe + sfm)")
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--split", default="val", choices=["train", "val"], help="tập scene (held-out bị chặn)")
    ap.add_argument("--scenes", nargs="+", help="chỉ các video_id này (mặc định: cả tập)")
    ap.add_argument("--out-root", default="data/sweeps/grid", help="thư mục ghi tạm (ngoài git); CSV nằm ở <out-root>/sweep.csv")
    ap.add_argument("--q-drop", type=float, nargs="+", default=[0.2, 0.35, 0.5])
    ap.add_argument("--overlap-max", type=float, nargs="+", default=[0.7, 0.8, 0.9])
    ap.add_argument("--overlap-min", type=float, nargs="+", default=[0.6])
    ap.add_argument("--exposure-q-drop", type=float, nargs="+", default=None, help="mặc định: giá trị trong default.yaml")
    ap.add_argument("--repeat", type=int, default=1, help="số lần lặp SfM mỗi (scene, cấu hình)")
    ap.add_argument("--keep", action="store_true", help="giữ thư mục chạy (tốn đĩa)")
    ap.add_argument("--target-max", type=int, default=None, help="ghi đè keyframe.target_max (số keyframe chọn sau SfM; ví dụ 1000 để giữ mọi ảnh đã đăng ký, KHÔNG hợp lệ theo ĐC §7)")
    ap.add_argument("--no-sfm", action="store_true", help="chỉ chạy `keyframe` (nhanh, không cần GPU): lập bản đồ N_kf trước khi tốn SfM")
    ap.add_argument("--summary", metavar="CSV", help="chỉ tóm tắt và chọn từ CSV, không chạy")
    args = ap.parse_args(argv)

    if args.summary:
        rows = read_rows(Path(args.summary))
        if not rows:
            print(f"[LỖI] không có dòng nào trong {args.summary}")
            return 1
        return 0 if print_summary(summarize(rows)) else 2

    root = Path(args.root)
    cfg = cfgmod.load_config(root / "configs" / "default.yaml")
    splits = sp.load_splits(root / "data" / "splits.csv")
    want = sp.SPLIT_VAL if args.split == "val" else sp.SPLIT_TRAIN
    scenes = [f"arkitscenes/{v}" for v, s in sorted(splits.items()) if s == want and (not args.scenes or v in args.scenes)]
    if not scenes:
        print("[LỖI] không có scene nào khớp")
        return 1
    exp_list = args.exposure_q_drop or [float(cfgmod.require(cfg, "keyframe.exposure.q_drop"))]
    out_root = root / args.out_root if not Path(args.out_root).is_absolute() else Path(args.out_root)
    csv_path = out_root / "sweep.csv"
    done = {(r["scene"], r["cfg_id"], str(r["rep"])) for r in read_rows(csv_path)}
    jobs = [j for j in itertools.product(args.q_drop, args.overlap_max, args.overlap_min, exp_list, range(args.repeat), scenes) if j[2] < j[1]]   # cần overlap.min < overlap.max
    print(f"[sweep] {len(scenes)} scene × {len(jobs) // len(scenes)} cấu hình/lần lặp = {len(jobs)} lượt; đã có {len(done)} dòng trong {csv_path}")
    t0 = time.time()
    for n, (q, om, omin, ex, rep, scene) in enumerate(jobs, 1):
        cid = cfg_id(q, om, omin, ex, args.target_max)
        if (scene, cid, str(rep)) in done:
            continue
        row = run_one(root, cfg, out_root, scene, q, om, omin, ex, rep, args.keep, sfm=not args.no_sfm, target_max=args.target_max)
        append_row(csv_path, row)
        print(f"[sweep] {n}/{len(jobs)} {scene} {cid} rep{rep}: N_kf {row.get('n_kf', '-')}, đăng ký {row.get('ratio', '-')}, lỗi {row.get('error') or '-'} ({time.time() - t0:.0f} s)")
    if args.no_sfm:
        print_summary(summarize(read_rows(csv_path)), len(scenes))               # chỉ bảng N_kf; chưa có tỉ lệ đăng ký để chọn
        return 0
    return 0 if print_summary(summarize(read_rows(csv_path)), len(scenes)) else 2


if __name__ == "__main__":
    sys.exit(main())
