# pipeline/keyframe/

Trạng thái (M0a): có `orientation.py` (xoay ảnh theo `sky_direction` và cập nhật intrinsics) cùng test. **Chưa có**:
trích khung, bộ lọc, ghi `keyframes.csv` (M1, M2).

## Vai trò

Node **Keyframes Input** của dataflow. Biến chuỗi ảnh RGB của một lượt quay thành 40–80 keyframe sạch, đã xoay đứng,
kèm tín hiệu chất lượng theo từng view. COLMAP chạy trên **cả** keyframe; VGGT chạy theo chunk (ĐC §7).

## Input/Output

| | Đường dẫn (trong `data/scenes/<dataset>/<scene_id>/`) | Nội dung |
|---|---|---|
| vào | `raw/source.json` | đường dẫn asset ARKitScenes, `sky_direction`, `visit_id` |
| vào | `lowres_wide.zip` hoặc `vga_wide.zip` + intrinsics + `.traj` (trong `data/raw/arkitscenes/…`) | RGB, `.pincam`, pose chỉ để tham chiếu |
| ra | `frames/keyframes/*.jpg` | keyframe đã xoay đứng |
| ra | `metadata/keyframes.csv` | cột `view_id, frame_ts, src_name, V, q_blur, q_exposure, sky_direction, rot_applied, w, h, fx, fy, cx, cy` (chỉ số **view i**) |
| ra | `metadata/camera.json` | intrinsics sau xoay |

Chỉ dùng RGB làm input; LiDAR và pose ARKit chỉ để tham chiếu (ĐC §10).

## Công thức

- Overlap = (W − Δ)/W × 100% (1); mục tiêu 60–80% giữa hai keyframe liên tiếp.
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
| `keyframe.target_max` | 80 | ĐC §7 |
| `keyframe.rotate_from_sky` | true | quyết định của nhóm |
| `keyframe.overlap.max` | 0.8 | Suy luận từ ĐC §6.1 (trên mức này coi là trùng) |
| `keyframe.overlap.min` | 0.6 | Suy luận từ ĐC §6.1 (dưới mức này coi là mất kết nối) |
| `keyframe.blur.q_drop` | null | chưa có căn cứ; khoá trên 6 scene Validation |

`quality.*` (`V_ref`, `G_ref`, `dark_px`, `bright_px`, cửa sổ) nằm ở [common](../common/README.md).

## Cách chạy riêng

```bash
# skip (chưa có CLI riêng cho module này, dự kiến M1)
python -m pipeline.keyframe --scene arkitscenes/42444738
```

Dùng hàm xoay trong Python: `from pipeline.keyframe.orientation import upright`.

## Test vector và tiêu chí đạt

- `tests/test_orientation.py`: intrinsics thật của scene 42444738 (256×192, f=213,293, c=(128,371; 95,7593), `Left`) cho
  ra 192×256, f giữ nguyên, c'=(96,2407; 128,371); chiếu điểm 3D trước và sau xoay phải khớp; xoay ảnh khớp ánh xạ pixel.
- `tests/test_quality.py`: V=575/203/3 cho q_blur 0,99/0,35/0,005 theo ví dụ của đề cương (V_ref=581 chỉ để kiểm hàm, không dùng làm cấu hình).
- Tiêu chí đạt (M1–M2): 40 ≤ N_kf ≤ 80; `rot_applied` đúng; ảnh xoay hiển thị đứng (xem tay scene Left, Up, Down).

## Lỗi thường gặp

- Quên xoay ảnh ARKit (ảnh lưu theo hướng cảm biến): COLMAP và VGGT chạy trên ảnh nằm ngang cho kết quả xấu.
- Xoay ảnh nhưng không đổi intrinsics (đổi `fx↔fy`, `cx`, `cy`): hình học sai tinh vi.
- Dùng blur ngưỡng cố định trên ảnh khác độ phân giải: phương sai Laplacian phụ thuộc độ phân giải; `V_ref` chỉ hợp lệ
  cho đúng asset đã đo.
- `extract_sparse_keyframe.py` ở `scripts/` là bản thô cũ (chọn khung đều, ngưỡng cố định); không dùng cho kết quả.

## Người phụ trách

@username1, @username2 (theo `.github/CODEOWNERS`).
