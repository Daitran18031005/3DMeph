# pipeline/common/

Mã dùng chung: cấu hình, đọc/ghi, hình học Sim(3), chỉ số chất lượng ảnh. Trạng thái (M0a): có đủ `config.py`, `io.py`,
`schema.py`, `geometry.py`, `quality.py`, `splits.py` (M0b) và test.

## Vai trò

- `config.py` nạp `configs/default.yaml`, thay `${BIẾN}` bằng biến môi trường (không có thì `None`, không đoán), cung cấp `require()` báo lỗi khi tham số còn `null`.
- `io.py` đọc/ghi JSON, cây thư mục một scene theo ĐC §9, định dạng ARKitScenes (`.traj`, `.pincam`, `frame_id`).
- `schema.py` hợp đồng I/O giữa các stage (tên cột, `Sim3Result`, `ScaleInfo`).
- `geometry.py` Umeyama, đảo pose, phép chiếu, xoay intrinsics, overlap, depth hợp lệ, khoảng cách hai điểm.
- `quality.py` `q_blur`, `q_exposure`, `q_texture`, hàm đổi sai số `f(x) = e^{−x/τ}`; `compute_v_ref`, `compute_g_ref` (trung vị qua scene,
  **chỉ nhận scene val**, scene held-out thì `raise HeldoutError`).
- `reference.py` `scene_stats`, `measure_reference`: đo `V_ref`/`G_ref` từ zip `vga_wide` theo `splits.csv` (`quality.mean_window_gradient` cho `G_ref`).
- `splits.py` chọn train/val/heldout theo venue (seed 42), ghi và kiểm `splits.lock` (sha256, xuống dòng chuẩn hoá LF), `guard_reference`.

`pipeline/__init__.py` `import torch` **trước mọi thư viện khác** (tránh lỗi DLL của pycolmap).

## Input/Output

| Hàm/Lớp | Vào | Ra |
|---|---|---|
| `load_config(path)` | `configs/default.yaml` | dict lồng nhau |
| `scene_layout(data_root, dataset, scene_id)` | | `SceneLayout` với các thư mục Mục 9 |
| `parse_traj_line`, `read_traj` | dòng `.traj`: `timestamp rx ry rz tx ty tz` | `(timestamp, R_cw, t_cw)` world→camera |
| `parse_pincam` | `w h fx fy cx cy` | dict |
| `umeyama_sim3(x, y)` | hai tập điểm (n, d) | `(s, R, t)` |

Định dạng file giữa stage (tên cột, đơn vị, chỉ số view hay (i,k)) xem bảng schema ở README gốc và `schema.py`.

## Công thức

- Umeyama Sim(3) (13)–(17); đảo pose `T_wc = T_cw⁻¹ = [[Rᵀ, −Rᵀt], [0, 1]]` (5); phép chiếu `λx = K[R|t]X` (10).
- Overlap (1); `q_blur` (3); `q_exposure`, `q_texture` (20); `f(x) = e^{−x/τ}` (21); depth hợp lệ `0,05 ≤ D ≤ 10 m` (6); khoảng cách hai điểm (30).
- Xoay intrinsics theo `sky_direction`: xem [keyframe](../keyframe/README.md).

## Tham số

Các khoá `quality.*` (cho `q_blur`, `q_exposure`, `q_texture`):

| Khoá | Giá trị | Nguồn |
|---|---|---|
| `quality.v_ref.vga` | 205.69 | (3): trung vị qua scene của blur trung bình, đo ngày 2026-10-18 trên `vga_wide` của 6 Validation (`scripts/measure_reference.py`). Số 581 của đề cương không dùng |
| `quality.v_ref.measured_on` | validation | tập đo: `split = val` trong `splits.csv` |
| `quality.v_ref.n_scenes` | 6 | số scene đã đo |
| `quality.v_ref.date` | 2026-10-18 | ngày đo |
| `quality.v_ref.stride` | 10 | lấy mẫu mỗi 10 khung [kế hoạch §4.1] |
| `quality.g_ref.vga` | 29.01 | (20): trung vị qua scene của gradient cửa sổ 15×15 trung bình, cùng lần đo. Gộp theo khung → scene → trung vị là [Suy luận], PDF chỉ nói "trung vị trên Validation" |
| `quality.g_ref.measured_on` | validation | như trên |
| `quality.g_ref.n_scenes` | 6 | |
| `quality.g_ref.date` | 2026-10-18 | |
| `quality.g_ref.stride` | 10 | |
| `quality.window` | 15 | ĐC §16.1: cửa sổ 15×15 px |
| `quality.dark_px` | 5 | (20): pixel ≤ 5 là quá tối |
| `quality.bright_px` | 250 | (20): pixel ≥ 250 là cháy sáng |

`paths.*` và `loss.*`: xem [configs/README.md](../../configs/README.md).

## Cách chạy riêng

```bash
# skip (cần pytest)
python -m pytest tests/test_geometry.py tests/test_io_and_config.py tests/test_quality.py -q
```

## Test vector và tiêu chí đạt

- `tests/test_geometry.py`: Umeyama 4 camera (s=3,20; R xoay 90° ngược chiều kim đồng hồ; t=(1,0; 2,0)); đảo pose dòng `.traj`
  `5201.456 0 0 -1.5708 -1.20 1.65 -1.40` cho tâm camera (1,65; 1,20; 1,40); chiếu K=500, 320, 240 cho (420; 190) px; overlap 70% và 50%;
  depth 2,05/14,2/0,02 → hợp lệ/không/không.
- `tests/test_quality.py`: `q_blur` 0,99/0,35/0,005 (V=575/203/3, chỉ để kiểm hàm); `q_exposure` 0,98 và 0,60; `q_texture` 1,00 và 0,30.
- `tests/test_io_and_config.py`: `frame_id` của `47333462_5201.456.png` là `5201.456`; cấu hình nạp được, tham số chưa đo là `null`, không có khoá `lambda`.

## Lỗi thường gặp

- `import open3d`/`cv2` trước `pycolmap` gây "DLL load failed": luôn import qua gói `pipeline`.
- Quên đảo pose `.traj` (world→camera): dùng thẳng `t` làm tâm camera thì camera nằm ngoài phòng (ĐC §10.2).
- Nhầm số 581 với giá trị cấu hình: đó là ví dụ của đề cương đo trên 256×192 (kèm cả scene sẽ làm held-out), không dùng làm `quality.v_ref`.
- Console Windows (cp1252) không in được tiếng Việt: script CLI tự ép UTF-8.

## Người phụ trách

@username1, @username2, @username3, @username4 (theo `.github/CODEOWNERS`).
