import cv2
import os
import shutil

def is_blurry(image_path, threshold=100.0):
    """Hàm kiểm tra độ nhòe của ảnh. Mức độ threshold có thể tinh chỉnh."""
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Tính toán phương sai của đạo hàm bậc 2 (Laplacian)
    focus_measure = cv2.Laplacian(gray, cv2.CV_64F).var()
    return focus_measure < threshold

def extract_sparse_keyframes(input_folder, output_folder, target_frames=120):
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
        if is_blurry(img_path):
            print(f"Bỏ qua {img_name} vì quá mờ.")
            # Tìm ảnh nét hơn trong phạm vi gần đó
            fallback_found = False
            for j in range(1, 3): 
                if i+j < total_images:
                    fallback_path = os.path.join(input_folder, all_images[i+j])
                    if not is_blurry(fallback_path):
                        img_path = fallback_path
                        fallback_found = True
                        break
            if not fallback_found:
                continue # Nếu xung quanh đều mờ thì bỏ hẳn đoạn này

        # Copy ảnh đủ tiêu chuẩn sang thư mục mới
        new_path = os.path.join(output_folder, f"keyframe_{saved_count:04d}.jpg")
        shutil.copy(img_path, new_path)
        saved_count += 1

    print(f"Hoàn tất! Đã lưu {saved_count} keyframes chất lượng cao vào: {output_folder}")

# --- CÁCH SỬ DỤNG ---
# Trỏ thư mục chứa 540 ảnh ARKitScenes của bạn vào đây
input_dir = r"D:\Nghien_Cuu\3D_Metric\Project\vggt\Scene\Images\test\images" 
# Thư mục mới để chứa ảnh đã lọc (để chạy COLMAP)
output_dir = r"D:\Nghien_Cuu\3D_Metric\Project\3DMeph\data\processed"

# Lệnh chạy
extract_sparse_keyframes(input_dir, output_dir, target_frames=500)