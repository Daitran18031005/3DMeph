# data/

Nguồn thật của danh sách scene là **thư mục trên đĩa + `metadata.csv`** (số liệu đo ngày 17/10/2026). Thư mục `data/raw/` rất lớn
(ARKitScenes 26 GB, Replica 40 GB) và không đưa lên git.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `raw/arkitscenes/{Training,Validation}/<video_id>/` | asset thô: `lowres_wide.zip`, `lowres_wide_intrinsics.zip`, `lowres_wide.traj`, `lowres_depth.zip`, `highres_depth.zip`, `confidence.zip`, `<id>_3dod_mesh.ply` |
| `raw/arkitscenes/metadata.csv` | `video_id, visit_id, sky_direction, fold, has_laser_scanner_point_clouds, is_in_upsampling, is_in_threedod` |
| `raw/arkitscenes/laser_scanner_point_clouds/<visit_id>/` | laser Faro: `.ply` + `_pose.txt` (**chưa tải**, M0b) |
| `raw/replica/<scene>/` | `mesh.ply` + `textures/`; **thiếu** `preseg`, `semantic`, `glass.sur` (ĐC §11) |
| `scenes/<dataset>/<scene_id>/` | cây thư mục một scene theo ĐC §9 (xem README gốc); sinh từ M1 |
| `self_collected/` | 6–8 phòng tự quay (cross-domain, chưa có) |
| `processed/` | kết quả chạy thử cũ (COLMAP trên 121 ảnh); không thuộc cây Mục 9 |
| `splits.csv`, `splits.lock` | danh sách train/val/heldout và hash khoá (sinh ở M0b) |

Replica luôn là **test** và không dùng để train (ĐC §11). Tự thu: số đo của các phòng tự thu không dùng làm nhãn train (ĐC §18).

## ARKitScenes: 40 scene thật

- `Training/`: **34 scene** (`fold=Training`), `Validation/`: **6 scene** (`fold=Validation`). Cả 40: `has_laser_scanner_point_clouds=True`,
  `is_in_upsampling=True` (có `highres_depth`, dùng làm dự phòng khi chưa có Faro). `visit_id` đều hợp lệ.
- Thuộc **38 venue**: Training 32, Validation 6, **không venue nào chung**. Hai venue Training có 2 scene (phải cùng một tập):
  `472473` (47204780, 47204786) và `466899` (47331625, 47331627).
- `sky_direction`: Training Left 24, Up 7, Down 3; Validation Left 3, Up 1, Down 2. Không có `Right`, không có `NA`. Ảnh lưu theo hướng cảm biến;
  keyframe xoay về dạng đứng (Up→0°, Left→90° CW, Down→180°, Right→90° CCW).
- Validation: 42445022 (venue 421380, Left), 42897566 (422785, Up), 42897599 (423477, Left), 42898849 (434659, Left),
  45662981 (468711, Down), 47204552 (471952, Down).

### `selected_scenes.csv` không phải danh sách chính

File này ở `Download/ARKitScenes/ARKitScenes/selected_scenes.csv` (không nằm trong `data/`), 36 dòng, toàn `Training`. Đối chiếu với thư mục thật:
khớp 34/34 scene Training đang có, **lệch 2 dòng không có trên đĩa**:

| video_id | visit_id | laser | `is_in_upsampling` | Ghi chú |
|---|---|---|---|---|
| 48018156 | 483066 | True | False | cùng venue với 48018155 đang có; không có `highres_depth` |
| 48018164 | 483253 | **False** | False | không có laser, vi phạm điều kiện chọn |

6 scene Validation **không nằm trong** file. Vì vậy `select_scenes.py` quét thư mục thật và kiểm lại từng scene trong `metadata.csv`
(`fold` khớp thư mục, `has_laser_scanner_point_clouds=True`, `visit_id` là số nguyên, `sky_direction` hợp lệ); `selected_scenes.csv` chỉ để đối chiếu.

## Chia tập (kế hoạch, sinh ở M0b)

**29 train / 6 val / 5 held-out**, chia theo `visit_id` (venue), seed **42**; lệch nhỏ so với 30/5/5 của ĐC Hình 9.

- val = 6 scene `Validation`; dùng để khoá `V_ref`, `G_ref`, `τ_e`, `τ_σ`, ngưỡng blur/overlap và ngưỡng plane gate.
- held-out = 5 scene lấy từ `Training` theo venue (venue 2 scene vào cùng nhau), loại venue của scene dev (421267, scene 42444738 luôn ở train).
  Khoá bằng `splits.lock`; mọi hàm tính `V_ref`, `G_ref` từ chối scene held-out. Held-out nội bộ, **không gọi là official test** (ĐC §10).
- train = phần còn lại (29 scene).

## Dung lượng cần tải thêm (đã duyệt, chưa tải)

| Đợt | Nội dung | Dung lượng |
|---|---|---|
| A | `vga_wide` + intrinsics scene 42444738 | ≈ 0,74 GB |
| B | Faro visit 421267: 6 file `.ply` (≈ 1,8 GB mỗi file, 42.348.620 điểm) + `_pose.txt` | ≈ 10,98 GB |
| C | `vga_wide` + intrinsics 6 Validation (riêng 42897599 là 4,12 GB) | ≈ 10,23 GB |

Tổng ≈ 21,95 GB; ổ D: còn khoảng 55 GB. Mỗi đợt chạy `--dry-run` trước, rồi mới tải thật.

## Ghi chú về asset ARKitScenes

- Ghép RGB/depth/pose theo `frame_id` = phần sau dấu `_` đầu tiên của tên file bỏ đuôi (`47333462_5201.456.png` → `5201.456`).
- `.traj` là world→camera ở 10 Hz (scene 42444738: 595 pose cho 3.607 khung 60 Hz); đảo bằng (5) khi cần camera→world.
- Depth hợp lệ trong [0,05; 10] m (6); ngoài khoảng là cảm biến nhìn xuyên cửa sổ/gương, đánh dấu không hợp lệ, không nội suy.
- `*_3dod_mesh.ply` là mesh ARKit, **không phải** Faro.
