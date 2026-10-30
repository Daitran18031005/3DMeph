# pipeline/keyframe/

Trạng thái (M2): có `orientation.py` (xoay ảnh), `overlap.py` (overlap RGB: ORB + homography RANSAC, chọn keyframe theo overlap) và `extract.py` (stage `keyframe`:
ứng viên theo `keyframe.fps`, lọc `q_blur` và `q_exposure`, lọc overlap, xoay đứng, ghi tập **dày** `frames/candidates/`, `candidates.csv`, `camera.json`, `raw/source.json`).
Từ 30/10 stage này chỉ dựng tập ứng viên dày cho SfM; 40–80 keyframe (ĐC §7) được chọn ở stage `sfm` từ các ảnh đã đăng ký (xem [colmap](../colmap/README.md)). Ngưỡng cần khoá lại trên
6 Validation bằng `scripts/sweep_keyframe.py` với SfM mới. **Chưa có**: phát hiện vật động (đề cương không nêu cách).

Nguồn **video điện thoại** (mp4/MOV, dữ liệu tự thu, `extract_video_keyframes` + `adapters.VideoSource`): có và đã chạy test trên video tổng hợp; **[chưa kiểm chứng trên video điện thoại thật]**
(tag rotation, timestamp VFR, tiêu cự thật). Cùng bước lọc và cùng hợp đồng đầu ra với nguồn ARKitScenes (xem "Nguồn video" bên dưới).

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

Với dữ liệu tự thu (`--scene self_collected/<id>`), đầu vào là đúng một video `*.mp4|*.mov|*.m4v` trong `data/self_collected/<id>/` (không copy, không ghi vào `data/raw`);
đầu ra nằm ở `data/scenes/self_collected/<id>/` với cùng các file như bảng trên (`sky_direction` ghi `video`; `camera.json` thêm `intrinsics_source`, `focal35_mm`;
`raw/source.json` ghi đường dẫn video, kích thước gốc, `rotation_deg`, fps metadata).

## Nguồn video

- **Timestamp**: `CAP_PROP_POS_MSEC` của container, lấy một lượt `grab()`; nếu không tăng nghiêm ngặt thì suy từ fps metadata (ghi `timestamps_from_fps_meta` trong `source.json`).
- **Hướng xoay**: tag rotation của video (góc xoay theo chiều kim đồng hồ để ảnh đứng) thay cho `sky_direction`: 0→`none`, 90→`cw90`, 180→`rot180`, 270→`ccw90`;
  tự xoay của OpenCV bị tắt để cùng `upright_rot` xoay ảnh và cập nhật intrinsics như nguồn ARKit.
- **Intrinsics** [Suy luận]: video không có `.pincam`. `fx = fy = f = focal35 · √(w² + h²) / 43,27` (px, trên ảnh gốc), tâm ở giữa ảnh, rồi xoay đứng và nhân theo tỉ lệ hạ ảnh.
  `focal35` lấy từ `video.focal35_mm`, hoặc từ file `video.json` (`{"focal35_mm": 24}`) đặt cạnh video. Chưa đọc được tiêu cự từ EXIF/QuickTime vì môi trường không có
  `ffprobe`/`pymediainfo` và không thêm dependency. COLMAP tinh chỉnh tiêu cự từ giá trị khởi đầu này.
- **Độ phân giải và blur** [Suy luận]: `V` (3) phụ thuộc độ phân giải, `V_ref`/`G_ref` chỉ hợp lệ cho `vga_wide` 640×480 của Validation. Ảnh video được hạ về cạnh dài
  `video.long_edge` (INTER_AREA, không phóng to) rồi mới đo `V`, `q_blur`, `q_exposure`, và chính ảnh hạ này được ghi làm ứng viên (nên `q_texture` ở fusion cùng thang với `G_ref`).
  Không đo lại `V_ref` trên video điện thoại (luật dữ liệu: chỉ đo trên `vga_wide` Validation). Còn mở: thang này tương đương theo độ phân giải chứ chưa theo camera;
  khi có video thật cần xem phân phối `q_blur` trong `candidates.csv` (nếu cả đoạn quay nét đều có `q_blur` thấp hơn nhiều so với ~0,76 của scene dev thì `V_ref` đang lệch).
- Ứng viên giữ trong RAM (~0,9 MB/khung ở 640×480; video dài hơn ~15 phút nên nén JPEG tạm).

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

Khối `video` (nguồn video điện thoại; mọi khoá là [Suy luận], chưa chạy trên video thật):

| Khoá | Giá trị | Nguồn |
|---|---|---|
| `video.source_dir` | data/self_collected | quyết định của nhóm: thư mục chứa `<id>/` với đúng một file mp4/mov/m4v, tương đối so với gốc repo, ngoài git |
| `video.long_edge` | 640 | Suy luận: bằng cạnh dài của `vga_wide` (640×480) để dùng đúng `V_ref`/`G_ref`; chỉ hạ, không phóng to |
| `video.focal35_mm` | 26 | TẠM: camera chính điện thoại thường 24–28 mm tương đương 35 mm (ví dụ 1920×1080 cho f ≈ 1324 px, HFOV ≈ 71°); video không có metadata tiêu cự thì dùng số này |

`quality.*` (`V_ref`, `G_ref`, `dark_px`, `bright_px`, cửa sổ) nằm ở [common](../common/README.md).

## Cách chạy riêng

```bash
# skip (cần dữ liệu thật ở data/raw; mất vài giây, đã chạy thật 27/10)
python -m pipeline.run --scene arkitscenes/42444738 --from-stage keyframe --to-stage keyframe
```

```bash
# skip (nguồn video: đặt đúng một video vào data/self_collected/<id>/ trước; chưa chạy trên video điện thoại thật)
python -m pipeline.run --scene self_collected/<id> --from-stage keyframe --to-stage keyframe
```

Dùng hàm xoay trong Python: `from pipeline.keyframe.orientation import upright` (ARKit) hoặc `upright_rot` + `rotation_for_video` (video).

## Test vector và tiêu chí đạt

- `tests/test_orientation.py`: intrinsics thật của scene 42444738 (256×192, f=213,293, c=(128,371; 95,7593), `Left`) cho
  ra 192×256, f giữ nguyên, c'=(96,2407; 128,371); chiếu điểm 3D trước và sau xoay phải khớp; xoay ảnh khớp ánh xạ pixel.
- `tests/test_quality.py`: V=575/203/3 cho q_blur 0,99/0,35/0,005 theo ví dụ của đề cương (V_ref=581 chỉ để kiểm hàm, không dùng làm cấu hình).
- `tests/test_keyframe_video.py` (video tổng hợp mp4v 320×240, 30 khung/giây): timestamp tăng và khớp fps, đọc đúng khung theo chỉ số, hợp đồng file đầu ra đọc lại được,
  hạ về `video.long_edge` thì intrinsics nhân đúng tỉ lệ, tag rotation 90° (tiêm bằng monkeypatch vì OpenCV không ghi được tag) cho `cw90` và `cx'=h−cy`, `video.json` ghi đè tiêu cự,
  lỗi `E_MISSING_INPUT`/`E_TOO_FEW_KEYFRAMES`, `resolve_video_scene`. Chưa có test trên video điện thoại thật.
- Tiêu chí đạt (M1–M2): tập ứng viên ≥ `target_min`; sau SfM 40 ≤ N_kf ≤ 80; `rot_applied` đúng; ảnh xoay hiển thị đứng (xem tay scene Left, Up, Down).

## Lỗi thường gặp

- Quên xoay ảnh ARKit (ảnh lưu theo hướng cảm biến): COLMAP và VGGT chạy trên ảnh nằm ngang cho kết quả xấu.
- Xoay ảnh nhưng không đổi intrinsics (đổi `fx↔fy`, `cx`, `cy`): hình học sai tinh vi.
- Dùng blur ngưỡng cố định trên ảnh khác độ phân giải: phương sai Laplacian phụ thuộc độ phân giải; `V_ref` chỉ hợp lệ
  cho đúng asset đã đo.
- Video điện thoại: dùng số `V_ref` cũ trên ảnh chưa hạ độ phân giải (4K/1080p) làm `q_blur` lệch (phương sai Laplacian đổi theo độ phân giải); stage đã hạ về `video.long_edge` trước khi đo, đừng bỏ bước này.
- Video có tag rotation mà đọc bằng công cụ tự xoay (OpenCV mặc định): `VideoSource` tắt tự xoay để xoay và đổi intrinsics một chỗ; đừng xoay hai lần.
- `extract_sparse_keyframe.py` ở `scripts/` là bản thô cũ (chọn khung đều, ngưỡng cố định); không dùng cho kết quả.

## Người phụ trách

@username1, @username2 (theo `.github/CODEOWNERS`).
