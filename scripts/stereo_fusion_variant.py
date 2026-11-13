#!/usr/bin/env python3
"""
stereo_fusion_variant.py — chạy LẠI `stereo_fusion` trên depth map MVS có sẵn với tham số khác, ghi PLY biến thể (M4 đợt 2, hướng D).

Không chạy lại SfM/PatchMatch và không đụng `fused.ply`: ra `baselines/colmap/mvs/fused_<tag>.ply` và `fused_<tag>.ply.vis` (cấu hình `fusion.mvs_cloud: fused_<tag>.ply`
cho `fuse`). Cần `stereo/depth_maps` và `sparse` của stage mvs. COLMAP lấy từ `COLMAP_EXE` hoặc `../colmap/bin/colmap.exe`.

    python scripts/stereo_fusion_variant.py --scene 42897599 --tag d1 --opt min_num_pixels=3 max_reproj_error=4 max_depth_error=0.02 check_num_images=100
    python scripts/stereo_fusion_variant.py --scene 42897599 --tag d2 --input-type photometric
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pipeline  # noqa: E402,F401  (import torch trước cv2/open3d/pycolmap)

# isort: split
from pipeline.colmap.run_colmap import _count_ply_vertices, run_cmd  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402
from pipeline.common.io import scene_layout  # noqa: E402

OPTS = {"min_num_pixels", "max_num_pixels", "max_traversal_depth", "max_reproj_error", "max_depth_error", "max_normal_error", "check_num_images"}


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--scene", required=True, help="video_id (train hoặc Validation)")
    ap.add_argument("--tag", required=True, help="ra fused_<tag>.ply")
    ap.add_argument("--input-type", default="geometric", choices=["geometric", "photometric"])
    ap.add_argument("--opt", nargs="*", default=[], metavar="KHOÁ=GIÁ_TRỊ", help=f"StereoFusion.<khoá>: {sorted(OPTS)}")
    a = ap.parse_args(argv)
    root = Path(a.root)
    splits = sp.load_splits(root / "data" / "splits.csv")
    if splits.get(a.scene) not in (sp.SPLIT_TRAIN, sp.SPLIT_VAL):
        print(f"[LỖI] {a.scene} không phải train/Validation (held-out bị chặn) hoặc không có trong splits.csv")
        return 1
    args = []
    for o in a.opt:
        k, _, v = o.partition("=")
        if k not in OPTS or not v:
            print(f"[LỖI] --opt chỉ nhận {sorted(OPTS)} dạng khoá=giá_trị, nhận {o!r}")
            return 1
        args += [f"--StereoFusion.{k}", v]
    exe = os.environ.get("COLMAP_EXE") or str(root.parent / "colmap" / "bin" / "colmap.exe")
    mvs = scene_layout(root / "data" / "scenes", "arkitscenes", a.scene).colmap_mvs
    if not (mvs / "stereo" / "depth_maps").is_dir():
        print(f"[LỖI] thiếu {mvs / 'stereo' / 'depth_maps'}: chạy stage mvs trước")
        return 1
    out = mvs / f"fused_{a.tag}.ply"
    if out.name == "fused.ply":
        print("[LỖI] không ghi đè fused.ply")
        return 1
    t0 = time.time()
    run_cmd(exe, ["stereo_fusion", "--workspace_path", mvs, "--workspace_format", "COLMAP", "--input_type", a.input_type, "--output_path", out, *args], print, poll_vram=False)
    n0, n1 = _count_ply_vertices(mvs / "fused.ply"), _count_ply_vertices(out)
    print(f"[ok] {out.name}: {n1:,} điểm (fused.ply: {n0:,}; ×{n1 / max(n0, 1):.2f}), {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
