# data/

Nguồn thật của danh sách scene là **thư mục trên đĩa + `metadata.csv`** (số liệu đo ngày 17/10/2026). Thư mục `data/raw/` rất lớn
(ARKitScenes 26 GB, Replica 40 GB) và không đưa lên git.

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `raw/arkitscenes/{Training,Validation}/<video_id>/` | asset thô: `lowres_wide.zip`, `lowres_wide_intrinsics.zip`, `lowres_wide.traj`, `lowres_depth.zip`, `highres_depth.zip`, `confidence.zip`, `<id>_3dod_mesh.ply` |
| `raw/arkitscenes/metadata.csv` | `video_id, visit_id, sky_direction, fold, has_laser_scanner_point_clouds, is_in_upsampling, is_in_threedod` |
| `raw/arkitscenes/laser_scanner_point_clouds/<visit_id>/` | laser Faro: `.ply` + `_pose.txt` (đã tải 7 visit: scene dev và 6 Validation; held-out **chưa tải**) |
| `raw/replica/<scene>/` | `mesh.ply` + `textures/`; **thiếu** `preseg`, `semantic`, `glass.sur` (ĐC §11) |
| `scenes/<dataset>/<scene_id>/` | cây thư mục một scene theo ĐC §9 (xem README gốc); sinh từ M1 |
| `self_collected/` | 6–8 phòng tự quay (cross-domain, chưa có) |
| `processed/` | kết quả chạy thử cũ (COLMAP trên 121 ảnh); không thuộc cây Mục 9 |
| `splits.csv`, `splits.lock`, `rejected.csv` | danh sách train/val/heldout, hash khoá, scene bị loại (đã sinh bằng `scripts/select_scenes.py`) |

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

## Chia tập (đã sinh bằng `scripts/select_scenes.py`, người dùng đã xác nhận)

**29 train / 6 val / 5 held-out**, chia theo `visit_id` (venue), seed **42**; lệch nhỏ so với 30/5/5 của ĐC Hình 9.
Kết quả ở `data/splits.csv` (cột `video_id, visit_id, split, sky_direction, source_dir, seed`), khoá bằng `data/splits.lock`
(sha256 của `splits.csv` với xuống dòng chuẩn hoá LF); `data/rejected.csv` ghi scene bị loại (hiện 0 dòng).

- val = 6 scene `Validation`; dùng để khoá `V_ref`, `G_ref`, `τ_e`, `τ_σ`, ngưỡng blur/overlap và ngưỡng plane gate.
- held-out = 5 scene lấy từ `Training` theo venue (venue 2 scene vào cùng nhau), loại venue của scene dev (421267, scene 42444738 luôn ở train):
  **43828368, 44796254, 47331622, 47332314, 47332795** (venue 437534, 464746, 466906, 471674, 469226). Chọn **chỉ bằng seed**, không dựa vào dung lượng Faro.
  Khoá bằng `splits.lock`; `compute_v_ref` và `compute_g_ref` (`pipeline/common/quality.py`) `raise HeldoutError` khi gặp scene held-out.
  Held-out nội bộ, **không gọi là official test** (ĐC §10). Chạy lại `select_scenes.py` phải cho đúng cùng danh sách, nếu khác thì từ chối ghi đè.
- train = phần còn lại (29 scene).

## Dữ liệu đã tải thêm (đợt A–D, ngày 18/10/2026, bằng `scripts/download_arkitscenes.py`)

| Đợt | Nội dung | Dung lượng (GiB, 1024³) | Trạng thái |
|---|---|---|---|
| A | `vga_wide` + intrinsics scene 42444738 (1.804 ảnh) | 0,69 | đã tải, khớp HEAD, CRC zip OK |
| B | Faro visit 421267: 6 `.ply` + 6 `_pose.txt` | 10,22 | đã tải, khớp HEAD, header PLY khớp |
| C | `vga_wide` + intrinsics 6 Validation (riêng 42897599 là 3,83) | 9,53 | đã tải, khớp HEAD, CRC 12 zip OK |
| D | Faro 6 visit Validation (421380, 422785, 423477, 434659, 468711, 471952): 27 `.ply` + 27 `_pose.txt` | 46,21 | đã tải, khớp HEAD, header PLY khớp |

Tổng 66,65 GiB; ổ D còn **25,16 GiB** trống. **Faro của 5 scene held-out chưa tải** (24,44 GiB đầy đủ; wrapper từ chối vì ổ phải còn dư ≥ 15 GiB).

Mỗi scan Faro có **số điểm khác nhau** (không phải mọi file đều 42.348.620 điểm): file 1,863 GB (= 1,735 GiB) có 42.348.620 điểm, 1,825 GB (1,699 GiB) có 41.467.500, 1,801 GB (1,677 GiB) có 40.935.479
(công thức `332 + điểm × 44 = kích thước`, 44 B/điểm gồm tọa độ double, RGBA, `quality`, `radius`). Tổng 6 file visit 421267: 249.503.198 điểm; 27 file Validation: 1.127.653.846 điểm.
Wrapper tải zip thẳng vào `data/raw/arkitscenes/<split>/<id>/` (không có cấp `raw/`, không giải nén) và Faro vào `data/raw/arkitscenes/laser_scanner_point_clouds/<visit_id>/`.

## Ghi chú về asset ARKitScenes

- Ghép RGB/depth/pose theo `frame_id` = phần sau dấu `_` đầu tiên của tên file bỏ đuôi (`47333462_5201.456.png` → `5201.456`).
- `.traj` là world→camera ở 10 Hz (scene 42444738: 595 pose cho 3.607 khung 60 Hz); đảo bằng (5) khi cần camera→world.
- Depth hợp lệ trong [0,05; 10] m (6); ngoài khoảng là cảm biến nhìn xuyên cửa sổ/gương, đánh dấu không hợp lệ, không nội suy.
- `*_3dod_mesh.ply` là mesh ARKit, **không phải** Faro.
