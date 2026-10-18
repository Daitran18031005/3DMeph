# scripts/

Script chuẩn bị dữ liệu (chạy một lần hoặc theo batch). Dùng Python của env `3d_metric`.

## Đang có

| Script | Làm gì | Ghi chú |
|---|---|---|
| `validate_dataset.py` | kiểm tra toàn vẹn và định dạng ARKitScenes + Replica | đọc trực tiếp từ zip; mặc định ghi `reports/statistics/validation_report.csv` |
| `explore_dataset.py` | EDA: blur, exposure, depth, mesh | mặc định ghi `reports/statistics/eda_stats.csv`; đo trên `lowres_wide` 256×192 |
| `extract_sparse_keyframe.py` | lọc thô keyframe (bản thử nghiệm cũ) | đã có `argparse` và `main()`, không còn đường dẫn cứng; sẽ được `pipeline/keyframe` thay thế |
| `download_arkitscenes.py` | tải ARKitScenes theo đợt `--batch A\|B\|C\|D\|all`: A `vga_wide`+intrinsics scene dev, B Faro visit của scene dev, C `vga_wide`+intrinsics 6 Validation, D Faro 6 visit Validation. Zip vào `data/raw/arkitscenes/<split>/<id>/` (không có cấp `raw/`), Faro vào `data/raw/arkitscenes/laser_scanner_point_clouds/<visit_id>/`. **Không giải nén, không xoá zip**, tuần tự từng file, resume (`curl -C -`, ghi `.part`), thử lại tự động (`--retry-all-errors`, bỏ kết nối đứng bằng `--speed-limit`/`--speed-time`, tối đa `--max_attempts` lần mỗi file, mỗi lần resume), kiểm dung lượng khớp `Content-Length` rồi mới đổi tên, ghi log CSV. `--dry-run` chỉ HEAD và in bảng dung lượng; bắt buộc `--yes` mới tải; ổ phải còn dư ≥ `--min_free_gib` (15 GiB). Chặn scene/visit held-out. Chỉ dùng quy ước URL của `download_data.py` (hàm `download_file` của nó không resume, không kiểm dung lượng) | đã tải đợt A, B, C, D ngày 18/10 (66,65 GiB, khớp HEAD); không có đợt cho held-out |
| `select_scenes.py` | chọn scene từ **thư mục thật + `metadata.csv`** (không dùng `selected_scenes.csv`), chia train/val/heldout theo `visit_id` với seed 42, ghi `data/splits.csv`, `data/splits.lock`, `data/rejected.csv` | đã chạy; chạy lại phải cho đúng cùng kết quả, khác thì từ chối ghi đè; `--dry-run` chỉ in |
| `measure_reference.py` | đo `V_ref`, `G_ref` trên `vga_wide` của 6 Validation (mỗi 10 khung; trung vị qua scene của trung bình mỗi scene), in bảng từng scene và so với số cũ 581 của đề cương (chỉ để so, không dùng). Danh sách scene lấy từ `splits.csv` (kiểm `splits.lock`); scene held-out/train bị từ chối trước khi đọc ảnh. `--write-config` chỉ ghi khi config còn `null` | đã chạy 18/10: V_ref 205,69, G_ref 29,01 (6 scene, 1 phút 28 giây); chỉ đọc raw |
| `adapters.py` | thư viện đọc dữ liệu thô dùng chung (không phải CLI): `AssetReader` (dir/zip, gom từ `validate_dataset.py` và `explore_dataset.py`), `Trajectory` (pose `.traj` có nội suy slerp, tâm camera theo (5)), intrinsics `.pincam` và đổi tỉ lệ (`highres_depth` 1920×1440), `unproject_depth` (depth mm → điểm world, depth hợp lệ (6)), đọc PLY Faro theo chunk (`iter_ply_xyz`, kiểm `header + n×44 = kích thước`), `list_scans`, `voxel_downsample_stream` | `tests/test_adapters.py` (19 test); quy ước trục camera OpenCV là [chưa kiểm chứng] cho ARKitScenes, `faro_align.py` sẽ kiểm bằng dữ liệu |
| `check_docs.py` | kiểm README khớp `configs/default.yaml`, công thức, lệnh chạy được | xem bên dưới |

Lưu ý khi đọc `validate_dataset.py`: file `*.ply` trong thư mục scene mà script gọi là "mesh" là `*_3dod_mesh.ply`, mesh của ARKit/iPad, **không phải**
laser Faro.

## Sẽ có (M0b)

| Script | Làm gì |
|---|---|
| `faro_align.py` | căn point cloud Faro vào hệ scene |
| `annotate_segments.py` | chấm đầu mút mốc scale và các đoạn test, ghi `ground_truth/measurements.csv` |

Các script trong README cũ (`download_arkitscenes.py`, `download_replica.sh`, `adapters.py`) từng được liệt kê nhưng **chưa tồn tại**. Hiện
`download_arkitscenes.py` đã có (bảng "Đang có"); `adapters.py` cũng đã có (bảng "Đang có"); `download_replica.sh` hoãn cùng Replica (M5).

## check_docs.py

```bash
# check
python scripts/check_docs.py
```

Kiểm tra:
1. Khoá trong `configs/default.yaml` khớp hai chiều với các bảng "Tham số" của README module (tiền tố → module ở `configs/README.md`).
2. README module có đủ 8 mục của khung: Vai trò; Input/Output; Công thức; Tham số; Cách chạy riêng; Test vector và tiêu chí đạt; Lỗi thường gặp; Người phụ trách.
3. Số công thức trong ngoặc tròn thuộc (1)–(37); không còn tên hệ số fusion cũ (`λ` kèm chỉ số r hoặc d, danh sách trong script);
   số 581 chỉ xuất hiện như ví dụ hoặc "không dùng".
4. Link tương đối trong repo trỏ tới file có thật.
5. Các khối ```` ```bash ```` có dòng đầu `# check` được chạy thật; `# skip` là lệnh nặng hoặc chưa có (kèm lý do).
