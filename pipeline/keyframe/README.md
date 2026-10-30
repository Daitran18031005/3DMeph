# pipeline/keyframe/

Trạng thái (M2): có `orientation.py` (xoay ảnh), `overlap.py` (overlap RGB: ORB + homography RANSAC, chọn keyframe theo overlap) và `extract.py` (stage `keyframe`:
ứng viên theo `keyframe.fps`, lọc `q_blur` và `q_exposure`, lọc overlap, xoay đứng, ghi tập **dày** `frames/candidates/`, `candidates.csv`, `camera.json`, `raw/source.json`).
Từ 30/10 stage này chỉ dựng tập ứng viên dày cho SfM; 40–80 keyframe (ĐC §7) được chọn ở stage `sfm` từ các ảnh đã đăng ký (xem [colmap](../colmap/README.md)). Ngưỡng cần khoá lại trên
6 Validation bằng `scripts/sweep_keyframe.py` với SfM mới. **Chưa có**: phát hiện vật động (đề cương không nêu cách).

## Vai trò

Node **Keyframes Input** của dataflow. Biến chuỗi ảnh RGB của một lượt quay thành 40–80 keyframe sạch, đã xoay đứng,
kèm tín hiệu chất lượng theo từng view. COLMAP chạy trên **cả** keyframe; VGGT chạy theo chunk (ĐC §7).

## Input/Output

| | Đường dẫn (trong `data/scenes/<dataset>/<scene_id>/`) | Nội dung |
|---|---|---|
| vào | `raw/source.json` | đường dẫn asset ARKitScenes, `sky_direction`, `visit_id` |
| vào | `lowres_wide.zip` hoặc `vga_wide.zip` + intrinsics + `.traj` (trong `data/raw/arkitscenes/…`) | RGB, `.pincam`, pose chỉ để tham chiếu |
| ra | `frames/candidates/*.jpg` | tập ứng viên dày đã xoay đứng (cho SfM); `frames/keyframes/` do stage `sfm` ghi |
| ra | `metadata/candidates.csv` | cùng cột với `keyframes.csv` (stage `sfm` ghi `keyframes.csv` đánh số lại): cột `view_id, frame_ts, src_name, V, q_blur, q_exposure, sky_direction, rot_applied, w, h, fx, fy, cx, cy` (chỉ số **view i**) |
| ra | `metadata/camera.json` | intrinsics sau xoay |

Chỉ dùng RGB làm input; LiDAR và pose ARKit chỉ để tham chiếu (ĐC §10).

## Công thức

- Overlap = (W − Δ)/W × 100% (1); mục tiêu 60–80% giữa hai keyframe liên tiếp. Đo chỉ từ RGB (`overlap.py`): ORB 1000 điểm + tỉ lệ Lowe 0,75 + homography RANSAC 3 px,
  overlap = phần diện tích khung A được khung B (chiếu vào A) phủ; dưới 15 inlier ⇒ 0 (mất kết nối) [Suy luận cho 15]. Với phép dịch ngang Δ cho đúng (W−Δ)/W (test: 64/128/192/320 px trên 640 px).
- Chọn theo overlap (`select_by_overlap`): từ khung giữ cuối, bỏ khung trùng (overlap > `overlap.max`), nhận khung đầu tiên không trùng; nếu khung đó đã mất kết nối
  (overlap < `overlap.min`) thì lùi một khung; không lùi được thì nhận và đếm một "đứt" [Suy luận].
- `q_blur = min(1, V / V_ref)` với `V = Var(∇²I)` (3).
- `q_exposure = 1 − (#pixel ≤ 5 + #pixel ≥ 250) / #pixel` (20).
- Số chunk cho VGGT `N_chunk = ⌈(N_kf − o)/(c − o)⌉` (2): xem [vggt](../vggt/README.md).
- **Xoay ảnh** (quyết định của nhóm, đã kiểm trên scene 42444738 có `sky=Left`): `Up`→0°, `Left`→90° CW,
  `Down`→180°, `Right`→90° CCW; `NA` không đoán, đánh dấu xem tay. Intrinsics (toạ độ pixel liên tục như COLMAP):
  - 90° CW: `w'=h, h'=w, fx'=fy, fy'=fx, cx'=h−cy, cy'=cx`
  - 90° CCW: `cx'=cy, cy'=w−cx` (kích thước và tiêu cự như trên)
  - 180°: `cx'=w−cx, cy'=h−cy`
  Sau xoay, hướng "lên" trong camera (quy ước OpenCV) là (0, −1, 0).
- Quy trình lọc (ĐC §7.2): mờ, trùng, tối/cháy, mất kết nối; vật động chỉ được liệt kê trong đề cương, không nêu
  cách phát hiện nên mốc đầu bỏ qua. Cách đo "trùng" và "mất kết nối" bằng overlap là suy luận của nhóm.

## Tham số

| Khoá | Giá trị | Nguồn |
|---|---|---|
| `keyframe.fps` | 2 | ĐC §7 (1–2 khung/giây) |
| `keyframe.target_min` | 40 | ĐC §7 |
| `keyframe.target_max` | 80 | ĐC §7 (40–80), áp ở stage `sfm` lên ảnh đã đăng ký (chọn đều theo thời gian). Thưa đều tập ứng viên xuống 80 trước SfM làm đứt chuỗi (M1: 46–65/80 ảnh; M2: 7,5–40% trên Validation), nên không còn làm ở stage `keyframe` |
| `keyframe.rotate_from_sky` | true | quyết định của nhóm |
| `keyframe.overlap.max` | 0.99 | Suy luận: tập ứng viên cho SfM chỉ bỏ khung gần như giống hệt (0,8 làm SfM đứt chuỗi); trước 30/10 là 0,8 (ĐC §6.1, mục tiêu 60–80%) |
| `keyframe.overlap.min` | 0.3 | Suy luận (dưới mức này coi là mất kết nối); nới từ 0,6 ở M2 để giữ đủ ảnh nối các đoạn |
| `keyframe.exposure.q_drop` | 0.5 | TẠM: ĐC §7.2 liệt kê lọc tối/cháy nhưng không có số; khoá theo phân phối `q_exposure` trên 6 Validation |
| `keyframe.blur.q_drop` | 0.35 | **tạm cho M1** (người dùng chọn 26/10; đo trên scene dev 42444738: loại 9/121 khung, q_blur trung vị 0,757); khoá lại trên 6 scene Validation ở M2. Ví dụ ĐC §7.3: q=0,35 giữ, q=0,005 loại |

`quality.*` (`V_ref`, `G_ref`, `dark_px`, `bright_px`, cửa sổ) nằm ở [common](../common/README.md).

## Cách chạy riêng

```bash
# skip (cần dữ liệu thật ở data/raw; mất vài giây, đã chạy thật 27/10)
python -m pipeline.run --scene arkitscenes/42444738 --from-stage keyframe --to-stage keyframe
```

Dùng hàm xoay trong Python: `from pipeline.keyframe.orientation import upright`.

## Test vector và tiêu chí đạt

- `tests/test_orientation.py`: intrinsics thật của scene 42444738 (256×192, f=213,293, c=(128,371; 95,7593), `Left`) cho
  ra 192×256, f giữ nguyên, c'=(96,2407; 128,371); chiếu điểm 3D trước và sau xoay phải khớp; xoay ảnh khớp ánh xạ pixel.
- `tests/test_quality.py`: V=575/203/3 cho q_blur 0,99/0,35/0,005 theo ví dụ của đề cương (V_ref=581 chỉ để kiểm hàm, không dùng làm cấu hình).
- Tiêu chí đạt (M1–M2): tập ứng viên ≥ `target_min`; sau SfM 40 ≤ N_kf ≤ 80; `rot_applied` đúng; ảnh xoay hiển thị đứng (xem tay scene Left, Up, Down).

## Lỗi thường gặp

- Quên xoay ảnh ARKit (ảnh lưu theo hướng cảm biến): COLMAP và VGGT chạy trên ảnh nằm ngang cho kết quả xấu.
- Xoay ảnh nhưng không đổi intrinsics (đổi `fx↔fy`, `cx`, `cy`): hình học sai tinh vi.
- Dùng blur ngưỡng cố định trên ảnh khác độ phân giải: phương sai Laplacian phụ thuộc độ phân giải; `V_ref` chỉ hợp lệ
  cho đúng asset đã đo.
- `extract_sparse_keyframe.py` ở `scripts/` là bản thô cũ (chọn khung đều, ngưỡng cố định); không dùng cho kết quả.

## Người phụ trách

@username1, @username2 (theo `.github/CODEOWNERS`).
