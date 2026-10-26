#!/usr/bin/env python3
"""
measure_reference.py — Đo V_ref và G_ref trên vga_wide của 6 scene Validation (kế hoạch §4.1).

  V_ref = trung vị qua scene của blur trung bình mỗi scene (phương sai Laplacian), lấy mẫu mỗi 10 khung  [ĐC §10.3, (3)]
  G_ref = trung vị qua scene của gradient cửa sổ 15×15 trung bình mỗi scene                              [ĐC §16.1, (20)]

Chỉ ĐỌC dữ liệu raw (zip vga_wide). Danh sách scene lấy từ data/splits.csv (kiểm splits.lock); scene held-out hoặc train
bị từ chối trước khi đọc ảnh. Không dùng số 581 (đề cương, đo trên lowres_wide, gồm cả scene held-out) hay 635,3.

Cách chạy (từ thư mục gốc repo, trong env 3d_metric):
    python scripts/measure_reference.py                    # đo và in bảng, KHÔNG ghi gì
    python scripts/measure_reference.py --write-config     # đo rồi ghi vào configs/default.yaml (chỉ khi còn `null`)

Mã thoát: 0 ok; 1 lỗi (khoá splits, held-out, thiếu dữ liệu, config không còn ở dạng chưa đo).
"""

import argparse
import csv
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pipeline  # noqa: E402,F401  (import torch trước, xem pipeline/__init__.py)
from pipeline.common import reference as ref  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402

OLD_PDF_V_REF = 581.0   # số cũ của đề cương: lowres_wide, 40 scene gồm cả held-out. Chỉ để so sánh, không dùng.

# Khối "chưa đo" trong configs/default.yaml (do M0a tạo)
UNMEASURED = re.compile(r"  v_ref:[^\n]*\n    vga: null\n  g_ref:[^\n]*\n    vga: null\n")


def config_block(res: dict, measured_date: str) -> str:
    common = (f"    measured_on: validation   # split = val trong splits.csv, asset {res['asset']}\n"
              f"    n_scenes: {res['n_scenes']}\n"
              f"    date: \"{measured_date}\"\n"
              f"    stride: {res['stride']}               # lấy mẫu mỗi {res['stride']} khung\n")
    return (f"  v_ref:                      # (3): trung vị qua scene của blur trung bình, đo trên vga_wide của 6 Validation\n"
            f"    vga: {res['v_ref']:.2f}\n{common}"
            f"  g_ref:                      # (20): trung vị qua scene của gradient cửa sổ {res['window']}×{res['window']} trung bình\n"
            f"    vga: {res['g_ref']:.2f}\n{common}")


def write_config(path: Path, res: dict, measured_date: str) -> None:
    text = path.read_text(encoding="utf-8")
    if not UNMEASURED.search(text):
        raise ValueError(f"{path.name}: v_ref/g_ref không còn ở dạng `null` (đã đo rồi?). Sửa tay nếu muốn đo lại, "
                         f"để tránh ghi đè số đã khoá.")
    path.write_text(UNMEASURED.sub(config_block(res, measured_date), text, count=1), encoding="utf-8", newline="\n")


def read_eda_lowres(csv_path: Path) -> dict:
    """blur_mean trên lowres_wide của EDA (chỉ để so sánh)."""
    if not csv_path.is_file():
        return {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        return {r["scene_id"]: float(r["blur_mean"]) for r in csv.DictReader(f) if r["dataset"] == "arkitscenes" and r["blur_mean"]}


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Đo V_ref, G_ref trên vga_wide của 6 Validation")
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--splits", default=None, help="mặc định <root>/data/splits.csv")
    ap.add_argument("--stride", type=int, default=ref.DEFAULT_STRIDE)
    ap.add_argument("--window", type=int, default=ref.DEFAULT_WINDOW)
    ap.add_argument("--config", default=None, help="mặc định <root>/configs/default.yaml")
    ap.add_argument("--eda_csv", default=None, help="mặc định <root>/reports/statistics/eda_stats.csv (chỉ để so sánh)")
    ap.add_argument("--write-config", action="store_true", help="ghi kết quả vào configs/default.yaml (chỉ khi còn null)")
    ap.add_argument("--date", default=None, help="ngày đo YYYY-MM-DD, mặc định hôm nay")
    args = ap.parse_args(argv)

    root = Path(args.root)
    splits_csv = Path(args.splits) if args.splits else root / "data" / "splits.csv"
    config = Path(args.config) if args.config else root / "configs" / "default.yaml"
    eda = read_eda_lowres(Path(args.eda_csv) if args.eda_csv else root / "reports" / "statistics" / "eda_stats.csv")
    measured_date = args.date or date.today().isoformat()

    try:
        res = ref.measure_reference(root, splits_csv, stride=args.stride, window=args.window)
    except (sp.HeldoutError, sp.LockError, ValueError, FileNotFoundError) as e:
        print(f"[LỖI] {type(e).__name__}: {e}")
        return 1

    print(f"Đo trên {res['asset']} của {res['n_scenes']} scene Validation (splits.csv đã khoá), lấy mẫu mỗi {res['stride']} khung, "
          f"cửa sổ {res['window']}×{res['window']}\n")
    print(f"{'scene':>9} {'venue':>7} {'khung':>6} {'mẫu':>5} | {'blur TB':>9} {'blur trung vị':>13} {'blur min':>9} | "
          f"{'texture TB':>10} {'texture min':>11} | {'blur lowres (EDA)':>17}")
    for v, s in res["per_scene"].items():
        low = f"{eda[v]:.1f}" if v in eda else "—"
        print(f"{v:>9} {s['visit_id']:>7} {s['n_frames']:>6} {s['n_sampled']:>5} | {s['blur_mean']:>9.2f} {s['blur_median']:>13.2f} "
              f"{s['blur_min']:>9.2f} | {s['grad_mean']:>10.3f} {s['grad_min']:>11.3f} | {low:>17}")
    v_ref, g_ref = res["v_ref"], res["g_ref"]
    print(f"\nV_ref (vga_wide, trung vị 6 scene) = {v_ref:.2f}")
    print(f"G_ref (vga_wide, trung vị 6 scene) = {g_ref:.3f}")
    diff = (v_ref - OLD_PDF_V_REF) / OLD_PDF_V_REF * 100
    print(f"So với số cũ của đề cương 581 (lowres_wide 256×192, 40 scene gồm held-out): V_ref mới {v_ref:.2f} "
          f"({'+' if diff >= 0 else ''}{diff:.1f}%, gấp {v_ref / OLD_PDF_V_REF:.2f} lần)")
    lows = [eda[v] for v in res["per_scene"] if v in eda]
    if len(lows) == len(res["per_scene"]):
        import statistics
        m = statistics.median(lows)
        print(f"Cùng 6 scene trên lowres_wide (EDA): trung vị {m:.1f} (khác 581 vì khác tập scene); vga_wide/lowres = {v_ref / m:.2f} lần "
              f"→ chênh do độ phân giải, đúng như lý do bỏ số 581")

    if args.write_config:
        try:
            write_config(config, res, measured_date)
        except ValueError as e:
            print(f"[LỖI] {e}")
            return 1
        print(f"\n[OK] Đã ghi quality.v_ref.vga = {v_ref:.2f} và quality.g_ref.vga = {g_ref:.2f} vào {config} "
              f"(measured_on validation, n_scenes {res['n_scenes']}, date {measured_date}, stride {res['stride']})")
    else:
        print("\n(Chỉ đo; chưa ghi config. Thêm --write-config để ghi.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
