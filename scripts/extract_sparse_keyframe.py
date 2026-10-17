#!/usr/bin/env python3
"""
extract_sparse_keyframe.py — Lọc thô ~N ảnh từ một thư mục ảnh (bản thử nghiệm cũ).

LƯU Ý: module `pipeline/keyframe/` (xem pipeline/keyframe/README.md) sẽ thay script này:
nó xoay ảnh theo sky_direction, lọc blur/exposure/trùng/mất kết nối theo đề cương (ĐC §7).
Script này chỉ chọn khung đều theo bước nhảy và bỏ khung có phương sai Laplacian dưới
ngưỡng cố định, nên chỉ dùng để thử nhanh.

Cách chạy:
    python scripts/extract_sparse_keyframe.py --input_dir <thư mục ảnh> \
        --output_dir <thư mục ra> --target_frames 120
"""

import argparse
import os
import shutil

import cv2


def is_blurry(image_path, threshold=100.0):
    """Hàm kiểm tra độ nhòe của ảnh. Mức độ threshold có thể tinh chỉnh."""
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Tính toán phương sai của đạo hàm bậc 2 (Laplacian)
    focus_measure = cv2.Laplacian(gray, cv2.CV_64F).var()
    return focus_measure < threshold


def extract_sparse_keyframes(input_folder, output_folder, target_frames=120, blur_threshold=100.0):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Lấy danh sách tất cả các ảnh và sắp xếp theo thứ tự
    all_images = sorted([f for f in os.listdir(input_folder) if f.endswith(('.png', '.jpg', '.jpeg'))])
    total_images = len(all_images)

    if total_images == 0:
        print("Không tìm thấy ảnh nào trong thư mục!")
        return

    # Tính toán bước nhảy (Step)
    step = max(1, total_images // target_frames)

    saved_count = 0
    print(f"Tổng số ảnh gốc: {total_images}. Bắt đầu lọc lấy ~{target_frames} ảnh...")

    for i in range(0, total_images, step):
        img_name = all_images[i]
        img_path = os.path.join(input_folder, img_name)

        # Kiểm tra nếu ảnh bị nhòe thì bỏ qua, lấy ảnh kề tiếp theo thay thế
        if is_blurry(img_path, blur_threshold):
            print(f"Bỏ qua {img_name} vì quá mờ.")
            # Tìm ảnh nét hơn trong phạm vi gần đó
            fallback_found = False
            for j in range(1, 3):
                if i + j < total_images:
                    fallback_path = os.path.join(input_folder, all_images[i + j])
                    if not is_blurry(fallback_path, blur_threshold):
                        img_path = fallback_path
                        fallback_found = True
                        break
            if not fallback_found:
                continue  # Nếu xung quanh đều mờ thì bỏ hẳn đoạn này

        # Copy ảnh đủ tiêu chuẩn sang thư mục mới
        new_path = os.path.join(output_folder, f"keyframe_{saved_count:04d}.jpg")
        shutil.copy(img_path, new_path)
        saved_count += 1

    print(f"Hoàn tất! Đã lưu {saved_count} keyframes vào: {output_folder}")


def main():
    parser = argparse.ArgumentParser(description="Lọc thô keyframe từ thư mục ảnh (bản thử nghiệm cũ)")
    parser.add_argument("--input_dir", required=True, help="Thư mục chứa ảnh gốc")
    parser.add_argument("--output_dir", required=True, help="Thư mục ghi keyframe")
    parser.add_argument("--target_frames", type=int, default=120)
    parser.add_argument("--blur_threshold", type=float, default=100.0,
                        help="Phương sai Laplacian tối thiểu; phụ thuộc độ phân giải ảnh")
    args = parser.parse_args()
    extract_sparse_keyframes(args.input_dir, args.output_dir, args.target_frames, args.blur_threshold)


if __name__ == "__main__":
    main()
