#!/usr/bin/env python3
"""
refuse_mvs.py — chạy LẠI chỉ bước `stereo_fusion` (cấu hình `colmap.stereo_fusion`, d3 từ M4 đợt 3) trên depth map MVS có sẵn của một scene,
sau khi sao lưu kết quả "MVS lọc chặt" cũ. Không chạy lại SfM/PatchMatch, không cần GPU, ~10 s.

Sao lưu (không ghi đè nếu đã có, không xoá gì):
  baselines/colmap/mvs/fused.ply(.vis)        → fused_strict.ply(.vis)
  baselines/colmap/metric/fused_metric.ply    → fused_metric_strict.ply
  proposed/{alignment,fusion,plane_refinement}, evaluation/{metrics.csv,logs/align_*.json} → proposed/variants/strict_old/ và evaluation/variants/strict_old/
Rồi ghi `fused.ply` mới và cập nhật `mvs_result.json`. Sau đó chạy `python -m pipeline.run --from-stage align --to-stage eval` để dựng lại các biến thể trên MVS mới.

    python scripts/refuse_mvs.py --scene 42897599
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import List

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pipeline  # noqa: E402,F401  (import torch trước cv2/open3d/pycolmap)

# isort: split
from pipeline.colmap.run_colmap import _count_ply_vertices, run_stereo_fusion  # noqa: E402
from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402
from pipeline.common.io import SceneLayout, read_json, scene_layout, write_json  # noqa: E402


def backup_strict(layout: SceneLayout) -> List[str]:
    """Sao lưu kết quả MVS lọc chặt cũ (idempotent: đích đã có thì giữ nguyên). Trả về danh sách đích đã ghi mới."""
    made: List[str] = []

    def cp(src: Path, dst: Path) -> None:
        if not src.exists() or dst.exists():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst) if src.is_dir() else shutil.copy2(src, dst)
        made.append(str(dst))

    mvs = layout.colmap_mvs
    cp(mvs / "fused.ply", mvs / "fused_strict.ply")
    cp(mvs / "fused.ply.vis", mvs / "fused_strict.ply.vis")
    cp(layout.colmap_metric / "fused_metric.ply", layout.colmap_metric / "fused_metric_strict.ply")
    old = layout.proposed / "variants" / "strict_old"
    for d in ("alignment", "fusion", "plane_refinement"):
        cp(layout.proposed / d, old / d)
    ev = layout.evaluation / "variants" / "strict_old"
    cp(layout.evaluation / "metrics.csv", ev / "metrics.csv")
    for f in sorted((layout.evaluation / "logs").glob("align_*.json")):
        cp(f, ev / "logs" / f.name)
    return made


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--scene", required=True, help="video_id (train hoặc Validation; held-out bị chặn)")
    a = ap.parse_args(argv)
    root = Path(a.root)
    cfg = cfgmod.load_config(root / "configs" / "default.yaml")
    splits = sp.load_splits(root / "data" / "splits.csv")
    if splits.get(a.scene) not in (sp.SPLIT_TRAIN, sp.SPLIT_VAL):
        print(f"[LỖI] {a.scene} không phải train/Validation (held-out bị chặn) hoặc không có trong splits.csv")
        return 1
    lay = scene_layout(root / cfgmod.require(cfg, "paths.data_root"), "arkitscenes", a.scene)
    mvs = lay.colmap_mvs
    if not (mvs / "stereo" / "depth_maps").is_dir() or not (mvs / "fused.ply").is_file():
        print(f"[LỖI] thiếu {mvs / 'stereo' / 'depth_maps'} hoặc fused.ply: chạy stage mvs trước")
        return 1
    made = backup_strict(lay)
    print(f"[sao lưu] {len(made)} mục mới ({'; '.join(Path(m).name for m in made) or 'đã có từ trước'})")
    exe = os.environ.get("COLMAP_EXE") or str(root.parent / "colmap" / "bin" / "colmap.exe")
    run_stereo_fusion(lay, cfg, exe, print)
    if not (mvs / "fused.ply.vis").is_file():
        print("[LỖI] stereo_fusion không tạo fused.ply.vis")
        return 1
    n_old, n_new = _count_ply_vertices(mvs / "fused_strict.ply"), _count_ply_vertices(mvs / "fused.ply")
    res_path = mvs / "mvs_result.json"
    res = read_json(res_path) if res_path.is_file() else {}
    res.update(n_fused_points=n_new, fused_ply_mb=round((mvs / "fused.ply").stat().st_size / 1e6, 1), stereo_fusion=dict(cfgmod.get(cfg, "colmap.stereo_fusion") or {}),
               n_fused_points_strict=n_old, strict_backup="fused_strict.ply")
    write_json(res_path, res)
    print(f"[ok] fused.ply: {n_new:,} điểm (bản lọc chặt cũ {n_old:,}; ×{n_new / max(n_old, 1):.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
