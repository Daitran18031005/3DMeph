# scripts/

Script chuẩn bị dữ liệu (chạy một lần hoặc theo batch). Dùng Python của env `3d_metric`.

## Đang có

| Script | Làm gì | Ghi chú |
|---|---|---|
| `validate_dataset.py` | kiểm tra toàn vẹn và định dạng ARKitScenes + Replica | đọc trực tiếp từ zip; mặc định ghi `reports/statistics/validation_report.csv` |
| `explore_dataset.py` | EDA: blur, exposure, depth, mesh | mặc định ghi `reports/statistics/eda_stats.csv`; đo trên `lowres_wide` 256×192 |
| `extract_sparse_keyframe.py` | lọc thô keyframe (bản thử nghiệm cũ) | đã có `argparse` và `main()`, không còn đường dẫn cứng; sẽ được `pipeline/keyframe` thay thế |
| `select_scenes.py` | chọn scene từ **thư mục thật + `metadata.csv`** (không dùng `selected_scenes.csv`), chia train/val/heldout theo `visit_id` với seed 42, ghi `data/splits.csv`, `data/splits.lock`, `data/rejected.csv` | đã chạy; chạy lại phải cho đúng cùng kết quả, khác thì từ chối ghi đè; `--dry-run` chỉ in |
| `check_docs.py` | kiểm README khớp `configs/default.yaml`, công thức, lệnh chạy được | xem bên dưới |

Lưu ý khi đọc `validate_dataset.py`: file `*.ply` trong thư mục scene mà script gọi là "mesh" là `*_3dod_mesh.ply`, mesh của ARKit/iPad, **không phải**
laser Faro.

## Sẽ có (M0b)

| Script | Làm gì |
|---|---|
| `adapters.py` | giao diện chung đọc RGB/intrinsics/pose/depth/Faro (gom `AssetReader` đang bị chép ở hai script) |
| `download_arkitscenes.py` | bọc `download_data.py` của ARKitScenes: tải zip thẳng vào `data/raw/arkitscenes/<split>/<id>/`, không giải nén; có `--dry-run` và bắt buộc `--yes` |
| `faro_align.py` | căn point cloud Faro vào hệ scene |
| `annotate_segments.py` | chấm đầu mút mốc scale và các đoạn test, ghi `ground_truth/measurements.csv` |

Các script trong README cũ (`download_arkitscenes.py`, `download_replica.sh`, `adapters.py`) từng được liệt kê nhưng **chưa tồn tại**; `download_replica.sh`
hoãn cùng Replica (M5).

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
