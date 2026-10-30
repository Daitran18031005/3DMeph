"""Chạy lại feature → match → mapper với nhiều bộ tham số trên keyframes đã có; in tỉ lệ đăng ký của model lớn nhất.
Dùng: sfm_variants.py <scene_dir> <variant> [<variant> ...]"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pycolmap

scene = Path(sys.argv[1])
exe = os.environ["COLMAP_EXE"]
imgs = scene / "frames/keyframes"
n_img = len(list(imgs.glob("*.jpg")))
cam = __import__("json").load(open(scene / "metadata/camera.json"))
CAM_PINHOLE = ["--ImageReader.camera_model", "PINHOLE", "--ImageReader.single_camera", "1",
               "--ImageReader.camera_params", f"{cam['fx']},{cam['fy']},{cam['cx']},{cam['cy']}"]
CAM_SIMPLE_RADIAL = ["--ImageReader.camera_model", "SIMPLE_RADIAL", "--ImageReader.single_camera", "1",
                     "--ImageReader.camera_params", f"{(cam['fx'] + cam['fy']) / 2},{cam['cx']},{cam['cy']},0"]
MAP_V2 = ["--Mapper.init_min_tri_angle", "4", "--Mapper.init_min_num_inliers", "50", "--Mapper.abs_pose_min_num_inliers", "15",
          "--Mapper.abs_pose_min_inlier_ratio", "0.1"]

# tên: (đối số feature_extractor thêm, camera, matcher [tên, đối số thêm], đối số mapper thêm)
FEAT = ["--SiftExtraction.peak_threshold", "0.004", "--SiftExtraction.estimate_affine_shape", "1", "--SiftExtraction.domain_size_pooling", "1"]
MAP_V5 = ["--Mapper.init_min_tri_angle", "2", "--Mapper.init_min_num_inliers", "30", "--Mapper.abs_pose_min_num_inliers", "10",
          "--Mapper.abs_pose_min_inlier_ratio", "0.05", "--Mapper.min_num_matches", "10", "--Mapper.abs_pose_max_error", "16"]
V = {
    "exh_feat_v2": (FEAT, CAM_PINHOLE, ["exhaustive_matcher", []], MAP_V2),
    "exh_feat_v5": (FEAT, CAM_PINHOLE, ["exhaustive_matcher", []], MAP_V5),
    "exh":([], CAM_PINHOLE, ["exhaustive_matcher", []], []),
    "exh_v2": ([], CAM_PINHOLE, ["exhaustive_matcher", []], MAP_V2),
    "exh_feat": (["--SiftExtraction.peak_threshold", "0.004", "--SiftExtraction.estimate_affine_shape", "1", "--SiftExtraction.domain_size_pooling", "1"],
                 CAM_PINHOLE, ["exhaustive_matcher", []], []),
    "exh_radial": ([], CAM_SIMPLE_RADIAL, ["exhaustive_matcher", []], []),
    "seq30": ([], CAM_PINHOLE, ["sequential_matcher", ["--SequentialMatching.overlap", "30", "--SequentialMatching.quadratic_overlap", "0"]], []),
}
for name in sys.argv[2:]:
    feat, cm, (mname, margs), mapargs = V[name]
    work = scene / "baselines/colmap" / f"_sv_{name}"
    if work.exists():
        shutil.rmtree(work)
    (work / "sparse").mkdir(parents=True)
    db = work / "database.db"
    t0 = time.time()

    def run(args):
        p = subprocess.run([exe] + [str(a) for a in args], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode:
            print(name, "LỖI", args[0], (p.stdout + p.stderr)[-400:])
            sys.exit(1)

    run(["feature_extractor", "--database_path", db, "--image_path", imgs, "--FeatureExtraction.use_gpu", "1"] + cm + feat)
    run([mname, "--database_path", db, "--FeatureMatching.use_gpu", "1"] + margs)
    run(["mapper", "--database_path", db, "--image_path", imgs, "--output_path", work / "sparse"] + mapargs)
    sizes = sorted((pycolmap.Reconstruction(str(d)).num_reg_images() for d in (work / "sparse").iterdir() if d.is_dir()), reverse=True)
    top = sizes[0] if sizes else 0
    print(f"{name}: {time.time() - t0:.0f}s, models {len(sizes)}, largest {top}/{n_img} ({100 * top / n_img:.1f}%), sizes {sizes[:6]}", flush=True)
