#!/usr/bin/env python3
"""
explore_dataset.py — Khám phá dữ liệu ARKitScenes + Replica đã validate,
xuất thống kê phục vụ thiết kế module confidence fusion (q^blur, q^exposure...).

Cài đặt phụ thuộc:
    pip install opencv-python-headless open3d numpy

Cách chạy:
    python3 explore_dataset.py \
        --arkitscenes_root data/raw/arkitscenes \
        --replica_root data/raw/replica \
        --output_csv reports/eda_stats.csv \
        --sample_stride 10

QUAN TRỌNG: hỗ trợ cả asset ARKitScenes dạng thư mục đã giải nén lẫn file .zip
chưa giải nén (xem AssetReader) — không cần giải nén thủ công trước khi chạy.

Chỉ nên chạy SAU KHI validate_dataset.py báo các scene là OK.
"""

import argparse
import csv
import glob
import os
import sys
import zipfile

import cv2
import numpy as np

try:
    import open3d as o3d
    HAS_OPEN3D = True
except ImportError:
    HAS_OPEN3D = False
    print("[WARN] open3d chưa cài — số liệu mesh sẽ để trống. "
          "Cài bằng: pip install open3d", file=sys.stderr)

ARKIT_RGB_DIR = "lowres_wide"
ARKIT_DEPTH_DIR = "lowres_depth"
DEPTH_MM_TO_M = 1.0 / 1000.0  # ARKitScenes depth thường lưu ở đơn vị mm (uint16)


class AssetReader:
    """Đọc file bên trong 1 asset ARKitScenes, hỗ trợ cả thư mục đã giải nén lẫn
    file .zip chưa giải nén (tên hiển thị có thể không có đuôi .zip trên Windows).
    Dùng qua "with" để tự đóng zip sau khi xong."""

    def __init__(self, scene_dir, asset_name):
        self.kind = None
        self.zf = None
        self.dir_path = None

        dir_path = os.path.join(scene_dir, asset_name)
        if os.path.isdir(dir_path):
            self.kind = "dir"
            self.dir_path = dir_path
            return

        candidates = [dir_path if dir_path.lower().endswith(".zip") else dir_path + ".zip",
                      dir_path]
        for c in candidates:
            if os.path.isfile(c) and zipfile.is_zipfile(c):
                self.kind = "zip"
                self.zf = zipfile.ZipFile(c)
                return

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def exists(self):
        return self.kind is not None

    def list_pngs(self):
        if self.kind == "dir":
            return sorted(f for f in os.listdir(self.dir_path) if f.lower().endswith(".png"))
        if self.kind == "zip":
            return sorted(n for n in self.zf.namelist() if n.lower().endswith(".png"))
        return []

    def read(self, entry, flags=cv2.IMREAD_UNCHANGED):
        if self.kind == "dir":
            return cv2.imread(os.path.join(self.dir_path, entry), flags)
        if self.kind == "zip":
            data = self.zf.read(entry)
            arr = np.frombuffer(data, dtype=np.uint8)
            return cv2.imdecode(arr, flags)
        return None

    def close(self):
        if self.zf is not None:
            self.zf.close()


def blur_score(img_gray):
    """Variance of Laplacian — Pech-Pacheco et al., ICPR 2000.
    Điểm càng thấp -> ảnh càng mờ. Dùng làm cơ sở định lượng cho q^blur."""
    return cv2.Laplacian(img_gray, cv2.CV_64F).var()


def exposure_score(img_gray):
    """Tỉ lệ pixel cháy sáng/tối — baseline đơn giản cho q^exposure."""
    total = img_gray.size
    overexposed = float(np.sum(img_gray >= 250)) / total
    underexposed = float(np.sum(img_gray <= 5)) / total
    return overexposed, underexposed


def explore_arkitscenes_scene(scene_dir, sample_stride=10):
    scene_id = os.path.basename(scene_dir.rstrip("/"))

    blur_scores, over_scores, under_scores = [], [], []
    with AssetReader(scene_dir, ARKIT_RGB_DIR) as rgb_reader:
        rgb_entries = rgb_reader.list_pngs()[::sample_stride]
        for entry in rgb_entries:
            img = rgb_reader.read(entry, cv2.IMREAD_GRAYSCALE)
            if img is None:
                continue
            blur_scores.append(blur_score(img))
            over, under = exposure_score(img)
            over_scores.append(over)
            under_scores.append(under)

    depth_chunks = []
    with AssetReader(scene_dir, ARKIT_DEPTH_DIR) as depth_reader:
        depth_entries = depth_reader.list_pngs()[::sample_stride]
        for entry in depth_entries:
            d = depth_reader.read(entry, cv2.IMREAD_UNCHANGED)
            if d is None:
                continue
            valid = d[d > 0]
            if valid.size:
                depth_chunks.append(valid.astype(np.float32) * DEPTH_MM_TO_M)
    depth_concat = np.concatenate(depth_chunks) if depth_chunks else np.array([])

    mesh_files = glob.glob(os.path.join(scene_dir, "*.ply"))
    n_vertices, bbox_diag = 0, None
    if mesh_files and HAS_OPEN3D:
        mesh = o3d.io.read_triangle_mesh(mesh_files[0])
        n_vertices = len(mesh.vertices)
        if n_vertices:
            bbox = mesh.get_axis_aligned_bounding_box()
            bbox_diag = float(np.linalg.norm(bbox.get_extent()))

    return {
        "dataset": "arkitscenes",
        "scene_id": scene_id,
        "n_frames_sampled": len(rgb_entries),
        "blur_mean": float(np.mean(blur_scores)) if blur_scores else None,
        "blur_min": float(np.min(blur_scores)) if blur_scores else None,
        "overexposed_ratio_mean": float(np.mean(over_scores)) if over_scores else None,
        "underexposed_ratio_mean": float(np.mean(under_scores)) if under_scores else None,
        "depth_min_m": float(depth_concat.min()) if depth_concat.size else None,
        "depth_max_m": float(depth_concat.max()) if depth_concat.size else None,
        "depth_median_m": float(np.median(depth_concat)) if depth_concat.size else None,
        "mesh_vertices": n_vertices,
        "mesh_triangles": None,
        "mesh_bbox_diagonal_m": bbox_diag,
    }


def explore_replica_scene(scene_dir):
    scene_id = os.path.basename(scene_dir.rstrip("/"))
    mesh_files = sorted(set(
        glob.glob(os.path.join(scene_dir, "*.ply")) +
        glob.glob(os.path.join(scene_dir, "**", "mesh.ply"), recursive=True)
    ))

    n_vertices, n_triangles, bbox_diag = 0, 0, None
    if mesh_files and HAS_OPEN3D:
        mesh = o3d.io.read_triangle_mesh(mesh_files[0])
        n_vertices = len(mesh.vertices)
        n_triangles = len(mesh.triangles)
        if n_vertices:
            bbox = mesh.get_axis_aligned_bounding_box()
            bbox_diag = float(np.linalg.norm(bbox.get_extent()))

    return {
        "dataset": "replica",
        "scene_id": scene_id,
        "n_frames_sampled": None,
        "blur_mean": None,
        "blur_min": None,
        "overexposed_ratio_mean": None,
        "underexposed_ratio_mean": None,
        "depth_min_m": None,
        "depth_max_m": None,
        "depth_median_m": None,
        "mesh_vertices": n_vertices,
        "mesh_triangles": n_triangles,
        "mesh_bbox_diagonal_m": bbox_diag,
    }


def main():
    parser = argparse.ArgumentParser(description="EDA ARKitScenes + Replica cho 3DMeph")
    parser.add_argument("--arkitscenes_root", default="data/raw/arkitscenes")
    parser.add_argument("--replica_root", default="data/raw/replica")
    parser.add_argument("--output_csv", default="reports/eda_stats.csv")
    parser.add_argument("--sample_stride", type=int, default=10,
                         help="Chỉ lấy mẫu 1/N frame để tính blur/exposure cho nhanh")
    args = parser.parse_args()

    out_dir = os.path.dirname(args.output_csv)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    rows = []

    arkit_scene_dirs = []
    for split in ("Training", "Validation"):
        split_dir = os.path.join(args.arkitscenes_root, split)
        if os.path.isdir(split_dir):
            arkit_scene_dirs += [os.path.join(split_dir, d) for d in sorted(os.listdir(split_dir))]
    if not arkit_scene_dirs and os.path.isdir(args.arkitscenes_root):
        arkit_scene_dirs = [os.path.join(args.arkitscenes_root, d)
                             for d in sorted(os.listdir(args.arkitscenes_root))]

    print(f"[INFO] Khám phá {len(arkit_scene_dirs)} scene ARKitScenes (sample_stride={args.sample_stride})...")
    for scene_dir in arkit_scene_dirs:
        if not os.path.isdir(scene_dir):
            continue
        stats = explore_arkitscenes_scene(scene_dir, args.sample_stride)
        rows.append(stats)
        print(f"  {stats['scene_id']}: blur_mean={stats['blur_mean']}, "
              f"depth_range=({stats['depth_min_m']}, {stats['depth_max_m']})m, "
              f"mesh_vertices={stats['mesh_vertices']}")

    replica_scene_dirs = [os.path.join(args.replica_root, d)
                           for d in sorted(os.listdir(args.replica_root))] \
        if os.path.isdir(args.replica_root) else []

    print(f"\n[INFO] Khám phá {len(replica_scene_dirs)} scene Replica...")
    for scene_dir in replica_scene_dirs:
        if not os.path.isdir(scene_dir):
            continue
        stats = explore_replica_scene(scene_dir)
        rows.append(stats)
        print(f"  {stats['scene_id']}: mesh_vertices={stats['mesh_vertices']}, "
              f"bbox_diagonal={stats['mesh_bbox_diagonal_m']}m")

    fieldnames = ["dataset", "scene_id", "n_frames_sampled", "blur_mean", "blur_min",
                  "overexposed_ratio_mean", "underexposed_ratio_mean",
                  "depth_min_m", "depth_max_m", "depth_median_m",
                  "mesh_vertices", "mesh_triangles", "mesh_bbox_diagonal_m"]
    with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

    print(f"\n[DONE] Thống kê đã lưu tại {args.output_csv}")
    print("Gợi ý: xem cột blur_min thấp bất thường -> ứng viên tune ngưỡng q^blur "
          "trong module confidence fusion; overexposed/underexposed_ratio_mean cao "
          "-> ứng viên tune q^exposure.")


if __name__ == "__main__":
    main()
