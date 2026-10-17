#!/usr/bin/env python3
"""
select_scenes.py — Chọn scene ARKitScenes và chia train/val/heldout theo venue (visit_id).

Nguồn chính: THƯ MỤC THẬT trên đĩa + metadata.csv (không dùng selected_scenes.csv; file đó chỉ để đối chiếu).
Kế hoạch §4.0b (docs/PLAN_v4.md). Không tải gì, không sửa dữ liệu raw.

Cách chạy (từ thư mục gốc repo, trong env 3d_metric):
    python scripts/select_scenes.py                 # seed 42, ghi data/splits.csv, data/splits.lock, data/rejected.csv
    python scripts/select_scenes.py --dry-run       # chỉ in kết quả, không ghi file

Quy tắc chia: val = 6 scene thư mục Validation; held-out = 5 scene từ Training theo venue (seed 42, bỏ venue của
scene dev 42444738); train = còn lại. Venue có 2 scene nằm trọn trong một tập. Kết quả được KHOÁ bằng
data/splits.lock (sha256); chạy lại phải cho đúng cùng danh sách, nếu khác thì từ chối ghi đè.

Mã thoát: 0 nếu thành công (hoặc kết quả trùng bản đã khoá), 1 nếu lỗi hoặc kết quả khác bản đã khoá.
"""

import argparse
import csv
import os
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pipeline  # noqa: E402,F401  (import torch trước, xem pipeline/__init__.py)
from pipeline.common import splits as sp  # noqa: E402

FOLDS = ("Training", "Validation")
VALID_SKY = ("Up", "Left", "Down", "Right")
DEFAULT_ROOT = REPO / "data" / "raw" / "arkitscenes"
DEFAULT_SELECTED = REPO.parent / "Download" / "ARKitScenes" / "ARKitScenes" / "selected_scenes.csv"


def read_metadata(root: Path):
    path = root / "metadata.csv"
    with open(path, "r", newline="", encoding="utf-8") as f:
        return {r["video_id"]: r for r in csv.DictReader(f)}


def list_scene_dirs(root: Path):
    """[(video_id, fold)] theo thư mục thật Training/ và Validation/."""
    out = []
    for fold in FOLDS:
        d = root / fold
        if d.is_dir():
            out += [(name, fold) for name in sorted(os.listdir(d)) if (d / name).is_dir()]
    return out


def check_scene(video_id, fold_dir, meta):
    """Trả về lý do loại (str) hoặc None nếu scene hợp lệ."""
    row = meta.get(video_id)
    if row is None:
        return "không có trong metadata.csv"
    if row["fold"] != fold_dir:
        return f"fold trong metadata ({row['fold']}) khác thư mục ({fold_dir})"
    if row["has_laser_scanner_point_clouds"] != "True":
        return "has_laser_scanner_point_clouds không phải True"
    if not re.fullmatch(r"\d+", row["visit_id"] or ""):
        return f"visit_id không hợp lệ: {row['visit_id']!r}"
    if row["sky_direction"] not in VALID_SKY:
        return f"sky_direction không hợp lệ: {row['sky_direction']!r} (xem tay)"
    return None


def scan(root: Path):
    """Trả về (scenes hợp lệ, danh sách bị loại). Scene hỏng điều kiện bị loại, không làm dừng."""
    meta = read_metadata(root)
    scenes, rejected = [], []
    for video_id, fold in list_scene_dirs(root):
        why = check_scene(video_id, fold, meta)
        if why:
            rejected.append({"video_id": video_id, "dir": fold, "reason": why})
        else:
            m = meta[video_id]
            scenes.append({"video_id": video_id, "visit_id": m["visit_id"], "fold": fold,
                           "sky_direction": m["sky_direction"]})
    return scenes, rejected


def compare_with_selected(selected_csv: Path, scenes, meta):
    """Đối chiếu tham khảo với selected_scenes.csv (không dùng để quyết định)."""
    if not selected_csv.is_file():
        return None
    with open(selected_csv, "r", newline="", encoding="utf-8") as f:
        sel = {r["video_id"]: r for r in csv.DictReader(f)}
    on_disk = {s["video_id"] for s in scenes}
    missing = sorted(set(sel) - on_disk)
    not_listed = sorted(on_disk - set(sel))
    return {
        "n_selected": len(sel),
        "listed_not_on_disk": [(v, meta.get(v, {}).get("visit_id"), meta.get(v, {}).get("has_laser_scanner_point_clouds"),
                                meta.get(v, {}).get("is_in_upsampling")) for v in missing],
        "on_disk_not_listed": not_listed,
    }


def build_rows(scenes, split_of, seed):
    return [{"video_id": s["video_id"], "visit_id": s["visit_id"], "split": split_of[s["video_id"]],
             "sky_direction": s["sky_direction"],
             "source_dir": f"data/raw/arkitscenes/{s['fold']}/{s['video_id']}", "seed": seed} for s in scenes]


def write_rejected(rejected, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["video_id", "dir", "reason"], lineterminator="\n")
        w.writeheader()
        w.writerows(rejected)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Chọn scene ARKitScenes và chia train/val/heldout theo venue")
    ap.add_argument("--arkitscenes_root", default=str(DEFAULT_ROOT))
    ap.add_argument("--out", default=str(REPO / "data" / "splits.csv"))
    ap.add_argument("--rejected", default=str(REPO / "data" / "rejected.csv"))
    ap.add_argument("--selected_csv", default=str(DEFAULT_SELECTED), help="chỉ để đối chiếu, không dùng quyết định")
    ap.add_argument("--seed", type=int, default=sp.DEFAULT_SEED)
    ap.add_argument("--n_heldout", type=int, default=sp.DEFAULT_N_HELDOUT)
    ap.add_argument("--dev_scene", default="42444738", help="scene dev, luôn thuộc train")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in, không ghi file")
    args = ap.parse_args(argv)

    root = Path(args.arkitscenes_root)
    scenes, rejected = scan(root)
    meta = read_metadata(root)
    print(f"[INFO] Quét {root}: {len(scenes)} scene hợp lệ, {len(rejected)} bị loại")
    for r in rejected:
        print(f"  [LOẠI] {r['video_id']} ({r['dir']}): {r['reason']}")

    split_of = sp.select_splits(scenes, seed=args.seed, n_heldout=args.n_heldout, dev_scene=args.dev_scene)
    rows = build_rows(scenes, split_of, args.seed)
    counts = Counter(split_of.values())
    n_venue = len({s["visit_id"] for s in scenes})
    print(f"[INFO] {len(scenes)} scene / {n_venue} venue → train {counts['train']}, val {counts['val']}, "
          f"heldout {counts['heldout']} (seed {args.seed})")

    cmp = compare_with_selected(Path(args.selected_csv), scenes, meta)
    if cmp is None:
        print(f"[INFO] Không thấy {args.selected_csv}; bỏ qua đối chiếu (chỉ để tham khảo).")
    else:
        print(f"[INFO] Đối chiếu selected_scenes.csv ({cmp['n_selected']} dòng; chỉ để tham khảo):")
        print(f"  có trong file nhưng KHÔNG có trên đĩa: {cmp['listed_not_on_disk']}  (video_id, visit_id, laser, upsampling)")
        print(f"  có trên đĩa nhưng KHÔNG có trong file: {len(cmp['on_disk_not_listed'])} scene {cmp['on_disk_not_listed']}")

    out = Path(args.out)
    if args.dry_run:
        print("[DRY-RUN] Không ghi file.")
        return 0

    if out.is_file() and sp.lock_path_for(out).is_file():
        # Đã khoá: kết quả mới phải trùng đúng bản đã khoá, không ghi đè.
        tmp = out.with_suffix(".new.csv")
        sp.write_splits(rows, tmp)
        try:
            same = sp.file_sha256(tmp) == sp.file_sha256(out)
        finally:
            tmp.unlink(missing_ok=True)
        try:
            sp.verify_lock(out)
        except sp.LockError as e:
            print(f"[LỖI] {e}")
            return 1
        if not same:
            print("[LỖI] Kết quả mới KHÁC bản đã khoá (data/splits.lock). Từ chối ghi đè; held-out đã khoá không được đổi.")
            return 1
        print(f"[OK] Kết quả trùng đúng bản đã khoá: {out} (không ghi lại).")
    else:
        sp.write_splits(rows, out)
        lock = sp.write_lock(out, args.seed)
        print(f"[OK] Đã ghi {out} và {lock}")

    write_rejected(rejected, Path(args.rejected))
    print(f"[OK] Đã ghi {args.rejected} ({len(rejected)} dòng)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
