#!/usr/bin/env python3
"""
validate_dataset.py — Kiểm tra tính toàn vẹn & format dữ liệu ARKitScenes + Replica
cho pipeline 3DMeph (COLMAP + VGGT + confidence fusion).

Cài đặt phụ thuộc:
    pip install opencv-python-headless open3d numpy

Cách chạy:
    python3 validate_dataset.py \
        --arkitscenes_root data/raw/arkitscenes \
        --replica_root data/raw/replica \
        --output_csv reports/validation_report.csv

QUAN TRỌNG: các asset ARKitScenes (confidence, highres_depth, lowres_depth,
lowres_wide, lowres_wide_intrinsics) có thể tải về dạng file .zip CHƯA giải nén
(Windows Explorer ẩn đuôi .zip mặc định nên tên hiển thị giống hệt thư mục).
Script này tự nhận diện cả 2 trường hợp — thư mục đã giải nén HOẶC file .zip —
và đọc trực tiếp từ trong zip mà không cần giải nén ra đĩa trước.

Nếu script báo lỗi hàng loạt bất thường (thiếu mọi asset ở mọi scene), chạy thêm
cờ --debug_first_scene để in cấu trúc thật của scene đầu tiên rồi đối chiếu lại
với các hằng số ARKIT_*_DIR bên dưới.
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
    print("[WARN] open3d chưa cài — bỏ qua kiểm tra chi tiết mesh. "
          "Cài bằng: pip install open3d", file=sys.stderr)


# ---------- Cấu hình tên asset (chỉnh nếu cấu trúc thực tế khác) ----------
ARKIT_RGB_DIR = "lowres_wide"
ARKIT_DEPTH_DIR = "lowres_depth"
ARKIT_HIGHRES_DEPTH_DIR = "highres_depth"
ARKIT_INTRINSICS_DIR = "lowres_wide_intrinsics"
ARKIT_CONFIDENCE_DIR = "confidence"
FRAME_COUNT_MISMATCH_TOLERANCE = 0.05  # cho phép lệch 5% giữa số RGB và depth


class AssetReader:
    """Đọc file bên trong 1 asset ARKitScenes, hỗ trợ cả 2 dạng:
    - thư mục đã giải nén (VD: scene_dir/lowres_wide/*.png)
    - file .zip chưa giải nén (VD: scene_dir/lowres_wide.zip, hoặc file tên
      "lowres_wide" nhưng thực chất là zip do Explorer ẩn đuôi)
    Dùng xong nhớ gọi .close() (hoặc dùng qua "with")."""

    def __init__(self, scene_dir, asset_name):
        self.kind = None      # "dir" | "zip" | None
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

    def list_entries(self):
        """Tất cả file bên trong, không lọc đuôi — dùng để đếm (VD: intrinsics)."""
        if self.kind == "dir":
            return sorted(f for f in os.listdir(self.dir_path)
                           if os.path.isfile(os.path.join(self.dir_path, f)))
        if self.kind == "zip":
            return sorted(n for n in self.zf.namelist() if not n.endswith("/"))
        return []

    def list_pngs(self):
        return [f for f in self.list_entries() if f.lower().endswith(".png")]

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


def list_scene_contents(scene_dir, max_items=25):
    """Tiện ích debug: in ra những gì thực sự có trong 1 scene."""
    print(f"\n--- Nội dung của {scene_dir} ---")
    if not os.path.isdir(scene_dir):
        print("  (thư mục không tồn tại)")
        return
    for item in sorted(os.listdir(scene_dir))[:max_items]:
        full = os.path.join(scene_dir, item)
        if os.path.isdir(full):
            tag = "DIR "
        elif zipfile.is_zipfile(full):
            tag = "ZIP "
        else:
            tag = "FILE"
        print(f"  [{tag}] {item}")


def _check_image_asset(scene_dir, asset_name, report, key_n, key_res=None):
    """Kiểm tra 1 asset dạng ảnh PNG (RGB/depth), ghi kết quả vào report."""
    with AssetReader(scene_dir, asset_name) as reader:
        if not reader.exists():
            report["issues"].append(f"thiếu {asset_name} (không thấy thư mục lẫn file .zip)")
            report[key_n] = 0
            return
        pngs = reader.list_pngs()
        report[key_n] = len(pngs)
        if not pngs:
            report["issues"].append(f"{asset_name} rỗng (0 file .png)")
            return
        img = reader.read(pngs[0])
        if img is None:
            report["issues"].append(f"ảnh đầu tiên trong {asset_name} không đọc được (nghi corrupt)")
        elif key_res:
            report[key_res] = f"{img.shape[1]}x{img.shape[0]}"


def validate_arkitscenes_scene(scene_dir):
    scene_id = os.path.basename(scene_dir.rstrip("/"))
    report = {"dataset": "arkitscenes", "scene_id": scene_id, "issues": []}

    if not os.path.isdir(scene_dir):
        report["issues"].append("thư mục scene không tồn tại")
        report["status"] = "ISSUES"
        return report

    _check_image_asset(scene_dir, ARKIT_RGB_DIR, report, "n_rgb", "rgb_resolution")
    _check_image_asset(scene_dir, ARKIT_DEPTH_DIR, report, "n_depth")

    if report.get("n_rgb", 0) and report.get("n_depth", 0):
        diff_ratio = abs(report["n_rgb"] - report["n_depth"]) / report["n_rgb"]
        if diff_ratio > FRAME_COUNT_MISMATCH_TOLERANCE:
            report["issues"].append(
                f"số RGB ({report['n_rgb']}) và depth ({report['n_depth']}) "
                f"lệch >{FRAME_COUNT_MISMATCH_TOLERANCE:.0%}"
            )

    # --- Highres depth (ground truth Faro) ---
    with AssetReader(scene_dir, ARKIT_HIGHRES_DEPTH_DIR) as reader:
        if not reader.exists():
            report["issues"].append(
                f"thiếu {ARKIT_HIGHRES_DEPTH_DIR} — scene này KHÔNG có ground truth Faro, "
                "không dùng cho L_p2s"
            )
            report["n_highres_depth"] = 0
        else:
            n_hr = len(reader.list_pngs())
            report["n_highres_depth"] = n_hr
            if n_hr == 0:
                report["issues"].append(f"{ARKIT_HIGHRES_DEPTH_DIR} rỗng")

    # --- Intrinsics ---
    with AssetReader(scene_dir, ARKIT_INTRINSICS_DIR) as reader:
        if not reader.exists() or len(reader.list_entries()) == 0:
            report["issues"].append(f"thiếu/rỗng {ARKIT_INTRINSICS_DIR}")

    # --- Confidence (không bắt buộc nhưng nên có) ---
    with AssetReader(scene_dir, ARKIT_CONFIDENCE_DIR) as reader:
        if not reader.exists():
            report["issues"].append(f"thiếu {ARKIT_CONFIDENCE_DIR} (không bắt buộc, ghi chú lại)")

    # --- Mesh ---
    mesh_files = glob.glob(os.path.join(scene_dir, "*.ply"))
    if not mesh_files:
        report["issues"].append("không tìm thấy file mesh .ply trong scene_dir")
        report["mesh_vertices"] = 0
    elif HAS_OPEN3D:
        mesh = o3d.io.read_triangle_mesh(mesh_files[0])
        n_vert = len(mesh.vertices)
        report["mesh_vertices"] = n_vert
        if n_vert == 0:
            report["issues"].append(f"mesh {os.path.basename(mesh_files[0])} rỗng — nghi hỏng")

    # --- Trajectory / pose ---
    if not glob.glob(os.path.join(scene_dir, "*.traj")):
        report["issues"].append("không tìm thấy file .traj (pose)")

    report["status"] = "OK" if not report["issues"] else "ISSUES"
    return report


def validate_replica_scene(scene_dir):
    scene_id = os.path.basename(scene_dir.rstrip("/"))
    report = {"dataset": "replica", "scene_id": scene_id, "issues": []}

    if not os.path.isdir(scene_dir):
        report["issues"].append("thư mục scene không tồn tại")
        report["status"] = "ISSUES"
        return report

    mesh_files = sorted(set(
        glob.glob(os.path.join(scene_dir, "*.ply")) +
        glob.glob(os.path.join(scene_dir, "**", "mesh.ply"), recursive=True)
    ))
    if not mesh_files:
        report["issues"].append("không tìm thấy mesh.ply")
        report["mesh_vertices"] = 0
    elif HAS_OPEN3D:
        mesh = o3d.io.read_triangle_mesh(mesh_files[0])
        n_vert = len(mesh.vertices)
        report["mesh_vertices"] = n_vert
        if n_vert == 0:
            report["issues"].append("mesh rỗng — nghi hỏng")

    if not glob.glob(os.path.join(scene_dir, "**", "textures"), recursive=True) and \
       not os.path.isdir(os.path.join(scene_dir, "textures")):
        report["issues"].append("không tìm thấy thư mục textures/ (bỏ qua nếu không cần)")

    report["status"] = "OK" if not report["issues"] else "ISSUES"
    return report


def main():
    parser = argparse.ArgumentParser(description="Validate ARKitScenes + Replica cho 3DMeph")
    parser.add_argument("--arkitscenes_root", default="data/raw/arkitscenes")
    parser.add_argument("--replica_root", default="data/raw/replica")
    parser.add_argument("--output_csv", default="reports/validation_report.csv")
    parser.add_argument(
        "--debug_first_scene", action="store_true",
        help="In cấu trúc thư mục của scene đầu tiên mỗi dataset để đối chiếu."
    )
    args = parser.parse_args()

    out_dir = os.path.dirname(args.output_csv)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    all_reports = []

    # --- ARKitScenes: quét cả Training/ và Validation/, fallback nếu tải phẳng ---
    arkit_scene_dirs = []
    for split in ("Training", "Validation"):
        split_dir = os.path.join(args.arkitscenes_root, split)
        if os.path.isdir(split_dir):
            arkit_scene_dirs += [os.path.join(split_dir, d) for d in sorted(os.listdir(split_dir))]
    if not arkit_scene_dirs and os.path.isdir(args.arkitscenes_root):
        arkit_scene_dirs = [os.path.join(args.arkitscenes_root, d)
                             for d in sorted(os.listdir(args.arkitscenes_root))]

    print(f"[INFO] Tìm thấy {len(arkit_scene_dirs)} scene ARKitScenes.")
    if args.debug_first_scene and arkit_scene_dirs:
        list_scene_contents(arkit_scene_dirs[0])

    for scene_dir in arkit_scene_dirs:
        if not os.path.isdir(scene_dir):
            continue
        r = validate_arkitscenes_scene(scene_dir)
        all_reports.append(r)
        suffix = f" — {'; '.join(r['issues'])}" if r["issues"] else ""
        print(f"  [{r['status']:8}] {r['scene_id']}{suffix}")

    # --- Replica ---
    replica_scene_dirs = [os.path.join(args.replica_root, d)
                           for d in sorted(os.listdir(args.replica_root))] \
        if os.path.isdir(args.replica_root) else []

    print(f"\n[INFO] Tìm thấy {len(replica_scene_dirs)} scene Replica.")
    if args.debug_first_scene and replica_scene_dirs:
        list_scene_contents(replica_scene_dirs[0])

    for scene_dir in replica_scene_dirs:
        if not os.path.isdir(scene_dir):
            continue
        r = validate_replica_scene(scene_dir)
        all_reports.append(r)
        suffix = f" — {'; '.join(r['issues'])}" if r["issues"] else ""
        print(f"  [{r['status']:8}] {r['scene_id']}{suffix}")

    # --- Ghi CSV ---
    fieldnames = ["dataset", "scene_id", "status", "n_rgb", "n_depth",
                  "n_highres_depth", "rgb_resolution", "mesh_vertices", "issues"]
    with open(args.output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_reports:
            row = {k: r.get(k, "") for k in fieldnames}
            row["issues"] = "; ".join(r.get("issues", []))
            writer.writerow(row)

    n_ok = sum(1 for r in all_reports if r["status"] == "OK")
    print(f"\n[SUMMARY] {n_ok}/{len(all_reports)} scene hợp lệ (không có issue). "
          f"Chi tiết đầy đủ: {args.output_csv}")
    if n_ok < len(all_reports):
        print("Các scene có ISSUES nên tải lại (nếu do mạng) hoặc loại khỏi "
              "selected_scenes.csv rồi chọn video_id thay thế.")


if __name__ == "__main__":
    main()
