# Bằng chứng M2: SfM trên 6 scene Validation (27/10 và 30/10/2026)

Lưu để đối chiếu về sau (đánh giá, báo cáo). Chỉ gồm file văn bản nhỏ; dữ liệu nặng (ảnh, model, depth map, 2,6 GB) nằm ở `data/sweeps/m2new/`
(ngoài git, **không xoá** nếu còn cần chạy lại VGGT/MVS/align trên Validation). Toàn vẹn: `SHA256SUMS.txt` (tạo lúc commit).

Môi trường: COLMAP 4.0.4 CUDA 12.9.1 (`COLMAP_EXE`), RTX 4060 Laptop 8 GB, driver 573.22, env conda `3d_metric`; cơ sở mã `f153e33` (đóng M1) cộng thay đổi M2 ở commit chứa thư mục này.

## 1. Trước khi sửa (27/10) — `before_27-10/`

Quét 26 cấu hình keyframe trên 6 Validation (`scripts/sweep_keyframe.py`, SfM mặc định COLMAP, matcher sequential). Kết quả: không cấu hình nào đạt đồng thời 40 ≤ N_kf ≤ 80 và không thưa đều;
tỉ lệ đăng ký trung vị 3,1–12,5% khi thưa xuống 80 khung và 31,1% (min 14,4%) khi giữ mọi khung (`grid2_sweep.csv`). Kết luận lúc đó: ngưỡng keyframe không phải nguyên nhân.

## 2. Chẩn đoán trên 47204552 (30/10) — `diagnosis_47204552/`

Tập dày: 250 ứng viên (`q_drop` 0,35; `overlap` 0,99/0,3; không thưa). Script: `diag_db.py` (đọc `database.db`), `mapper_variants.py` (chỉ chạy lại mapper), `sfm_variants.py` (feature → match → mapper).
Database và ảnh của lượt chẩn đoán nằm ở thư mục tạm của phiên, **không lưu**; tái tạo bằng `scripts/sweep_keyframe.py --target-max 1000 --overlap-max 0.99 --overlap-min 0.3 --keep` rồi chạy các script trên.

Số in ra từ `diag_db.py` (SfM mặc định): 5 model (31, 19, 18, 11, 11 ảnh); keypoint/ảnh trung vị 617; match inlier giữa ảnh liền kề trung vị 86, p10 20, 14/249 cặp < 15.
Cấu hình hình học của 569 cặp đã xác minh: 402 CALIBRATED, 117 PLANAR_OR_PANORAMIC, 50 UNCALIBRATED. Nhiều đoạn ảnh liền kề có 99+ match vẫn không đăng ký.

Tỉ lệ ảnh đăng ký của model lớn nhất (250 ảnh), mỗi dòng đổi một thứ:

| Thí nghiệm | Model lớn nhất | Số model |
|---|---|---|
| SfM mặc định (sequential) | 31/250 = 12,4% | 5 |
| mapper-only `v1_init` (init_min_tri_angle 4, init_min_num_inliers 50) | 12,4% | 7 |
| mapper-only `v2_pose` (+ abs_pose_min_num_inliers 15, ratio 0,1) | 16,8% | 11 |
| mapper-only `v3_tri` (+ tri_ignore_two_view_tracks 0, min_num_matches 10, tri_min_angle 0,5) | 16,8% | 11 |
| mapper-only `v4_tri_only` | 12,4% | 6 |
| `exh` (exhaustive) | 18,0% | 5 |
| `exh_v2` (exhaustive + mapper v2) | 36,4% | 7 |
| `exh_feat` (exhaustive + peak 0,004, affine shape, DSP) | 35,6% | 6 |
| `exh_radial` (exhaustive + SIMPLE_RADIAL) | 18,0% | 5 |
| `seq30` (sequential overlap 30, không quadratic) | 16,8% | 9 |
| `exh_feat_v2` | 79,6% | 3 |
| **`exh_feat_v5`** (exhaustive + SIFT giàu + mapper nới: bộ đang dùng) | **84,4%** | 4 |

Kiểm trên hai scene khác với `exh_feat_v5`: 42898849 94,4% (251/266); dev 42444738 97,3% (108/111; trước đó 83,9%).
Cùng `exh_feat_v5` trên **80 khung thưa đều** (overlap 0,8/0,6): 47204552 7,5% (6/80), 42898849 40,0% (32/80), dev 96,2% (77/80) ⇒ SfM phải chạy trên tập dày.
Hạn chế: bộ mapper `v5` chỉ so nguyên bộ, chưa tách từng khoá; chọn trên 3 scene (không dùng held-out).

## 3. Sau khi sửa (30/10) — `after_30-10/`

Pipeline mới (`colmap.matcher: exhaustive`, `colmap.sift.*`, `colmap.mapper.*`, SfM trên `frames/candidates/`, chọn ≤ 80 keyframe sau SfM; xem `default.yaml.snapshot`).
Lệnh: `python scripts/sweep_keyframe.py --split val --out-root data/sweeps/m2new --q-drop 0.35 --overlap-max 0.99 --overlap-min 0.3 --keep` → `sweep.csv`.

| Scene | Ứng viên dày | Đăng ký | Tỉ lệ | Model | Keyframe | SfM (s) | Peak VRAM SfM (MiB) |
|---|---|---|---|---|---|---|---|
| 42445022 | 112 | 111 | 99,1% | 1 | 80 | 101 | 1.019 |
| 42897566 | 80 | 78 | 97,5% | 1 | 78 | 121 | 1.129 |
| 42897599 | 578 | 576 | 99,7% | 1 | 80 | 1.686 | 1.195 |
| 42898849 | 266 | 251 | 94,4% | 2 | 80 | 240 | 244 |
| 45662981 | 178 | 161 | 90,5% | 1 | 80 | 141 | 280 |
| 47204552 | 250 | 211 | 84,4% | 4 | 80 | 160 | 248 |

Trung vị 95,9%, nhỏ nhất 84,4%. (Cột "Ứng viên dày" suy từ n_registered/ratio; số gốc nằm ở `sfm_result.json` mỗi scene.)
Phép đo thêm trên Validation:
- VGGT, 42897599: 80 keyframe → 8 chunk, 147 s, peak allocated 6.021 MiB (`per_scene/42897599/`).
- MVS, 42897566: 78 depth map, `fused.ply` 227.272 điểm, 761 s, peak VRAM 263 MiB (nvidia-smi) (`per_scene/42897566/`).

## 4. Chưa có trong bằng chứng này

`align`, `fuse`, `gate`, `export` trên Validation (không có mốc scale); sai số so với GT; khoá `q_drop`/`overlap`/`exposure` bằng quét lại với SfM mới; chạy lại scene dev qua `sfm` mới.

## 5. Quét `q_drop` 0,2 / 0,35 / 0,5 với SfM mới (31/10) — `after_30-10/sweep_qdrop_0.2_0.35_0.5.csv`

Lệnh: `python scripts/sweep_keyframe.py --split val --out-root data/sweeps/m2new --q-drop 0.2 0.35 0.5 --overlap-max 0.99 --overlap-min 0.3` (một lần chạy mỗi cấu hình; `overlap`, `exposure` giữ nguyên).
Đăng ký SfM (ảnh dày) theo scene, thứ tự 42445022 / 42897566 / 42897599 / 42898849 / 45662981 / 47204552:

| `q_drop` | Từng scene (%) | Trung vị | Min | N_kf |
|---|---|---|---|---|
| 0,2 | 100,0 / 94,7 / 99,3 / 94,0 / 98,1 / 82,8 | **96,4%** | 82,8% | 80 ở cả 6 |
| 0,35 | 99,1 / 97,5 / 99,7 / 94,4 / 90,5 / 84,4 | 95,9% | 84,4% | 78–80 |
| 0,5 | 90,7 / 100,0 / 99,7 / 95,0 / 92,4 / 88,3 | 93,7% | **88,3%** | 74–80 |

Quy tắc cố định của `sweep_keyframe.py` (trung vị cao nhất, hoà thì ít keyframe hơn) chọn 0,2. Chênh 0,2 so với 0,35 là 0,5 điểm phần trăm trên một lần chạy mỗi cấu hình: trong khoảng dao động giữa các lần chạy
(đo ở M1: 93–94/112 ảnh khi lặp 3 lần), nên **không đủ để kết luận**. `q_drop` thấp giữ thêm khung mờ; ảnh hưởng tới VGGT/MVS chưa đo. 47204552 vẫn dưới 90% ở cả ba mức.
