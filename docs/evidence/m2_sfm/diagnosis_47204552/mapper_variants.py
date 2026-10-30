"""Chạy lại CHỈ mapper trên database có sẵn với các bộ tham số khác nhau; in số ảnh đăng ký của model lớn nhất và tổng."""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pycolmap

scene = Path(sys.argv[1])
which = sys.argv[2:] or None
exe = os.environ["COLMAP_EXE"]
db = scene / "baselines/colmap/sfm/database.db"
imgs = scene / "frames/keyframes"
n_img = len(list(imgs.glob("*.jpg")))

V = {
    "base": [],
    "v1_init": ["--Mapper.init_min_tri_angle", "4", "--Mapper.init_min_num_inliers", "50"],
    "v2_pose": ["--Mapper.init_min_tri_angle", "4", "--Mapper.init_min_num_inliers", "50", "--Mapper.abs_pose_min_num_inliers", "15",
                "--Mapper.abs_pose_min_inlier_ratio", "0.1"],
    "v3_tri": ["--Mapper.init_min_tri_angle", "4", "--Mapper.init_min_num_inliers", "50", "--Mapper.abs_pose_min_num_inliers", "15",
               "--Mapper.abs_pose_min_inlier_ratio", "0.1", "--Mapper.tri_ignore_two_view_tracks", "0", "--Mapper.min_num_matches", "10",
               "--Mapper.filter_min_tri_angle", "0.5", "--Mapper.tri_min_angle", "0.5"],
    "v4_tri_only": ["--Mapper.tri_ignore_two_view_tracks", "0", "--Mapper.filter_min_tri_angle", "0.5", "--Mapper.tri_min_angle", "0.5"],
}
for name, extra in V.items():
    if which and name not in which:
        continue
    out = scene / "baselines/colmap/_mv" / name
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    t0 = time.time()
    p = subprocess.run([exe, "mapper", "--database_path", str(db), "--image_path", str(imgs), "--output_path", str(out)] + extra,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    sizes = []
    for d in sorted(x for x in out.iterdir() if x.is_dir()):
        r = pycolmap.Reconstruction(str(d))
        sizes.append(r.num_reg_images())
    print(f"{name}: exit {p.returncode}, {time.time() - t0:.0f}s, models {len(sizes)}, largest {max(sizes) if sizes else 0}/{n_img} "
          f"({100 * (max(sizes) if sizes else 0) / n_img:.1f}%), sizes {sorted(sizes, reverse=True)[:8]}", flush=True)
