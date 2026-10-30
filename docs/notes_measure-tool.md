# Ghi chú luồng 3: công cụ chọn hai điểm và so với thước dây (feature/measure-tool)

Để gộp vào `WORKING_LOG.md` sau (luồng này không sửa file đó).

## Đã làm (2026-10-31)

- `pipeline/export/measure.py`: thêm thư viện đầu mút (`endpoints_path`, `new/load/save_endpoints`, `add_segment`, `check_points_hash`), thước dây (`tape_median`, `add_tape`, `tape_to_rows`, `write_csv`) và `compare` (loại mốc, MAE/median/MAPE/%<ngưỡng bằng `pipeline/eval/metrics.py`, chỉ đọc). CLI cũ `--a --b` giữ nguyên.
- `scripts/pick_endpoints.py` (mới): `pick` (GUI Open3D, tái dùng `annotate_segments.pick_two_points`), `add`, `tape`, `compare`.
- `configs/default.yaml`: khối `measure:` (`tape_readings` 3, `anchor_min_m` 1,0, `anchor_max_m` 2,0, `under_cm` 5,0). Cả bốn lấy từ đề cương (§8.3, §8.1, §21), không có giá trị TẠM.
- `scripts/check_docs.py`: thêm 1 dòng `"measure": "pipeline/export/README.md"` vào `OWNERS`.
- Test: `tests/test_pick_endpoints.py` (15 test). Tài liệu: `pipeline/export/README.md`, `scripts/README.md`.

## Định dạng endpoints cho luồng eval

Xem `pipeline/export/README.md` mục "Định dạng `endpoints_<variant>.json`". Luồng eval chỉ cần đọc `["segments"]` (`id`, `a`, `b`, `length_m`), ghép theo `id` với `ground_truth/measurements.csv`, loại đoạn có `used_as_anchor=1` ở CSV.

## Chạy thật và chưa kiểm chứng

- Đã chạy thật (không GUI) trên bản sao `model_points.ply`, `model.glb`, `measurements.csv` của 42444738 trong thư mục scratchpad (không ghi vào `data/` thật): `load_points` đọc được cả PLY (144.863 điểm) và GLB (239.142 đỉnh); `add`, `compare`, chặn id trùng, chặn scene held-out chạy đúng. Số liệu trong lần chạy đó là toạ độ gõ tuỳ ý để thử đường ống, **không phải** kết quả đo.
- **GUI Open3D chưa chạy thật** (không có phiên tương tác). Chỉ kiểm vòng `pick_loop` bằng bản giả. Cần một người chạy `pick` trên máy có màn hình và kiểm: shift+chuột chọn đúng 2 điểm, toạ độ lưu khớp, màu theo trục y dễ nhìn.
- Chưa có số đo thước dây thật nên `compare --gt tape` mới chạy trên scene giả của test; `compare --gt csv` (GT Faro) chạy trên scene dev.

## Lệch so với kế hoạch, và đã hỏi chưa

- Sửa 1 dòng `scripts/check_docs.py` (ngoài danh sách file được sửa của luồng 3). Cần thiết để khối `measure:` qua kiểm hai chiều. Đã nêu trong kế hoạch được duyệt.
- Định dạng JSON: bọc object + `source` ASCII (thay `nguồn`) + `length_m`, `a_index`, `b_index`. Đã nêu trong kế hoạch được duyệt.

## Việc chưa làm

- Truyền cặp điểm sang biến thể khác (B0/B1/B3) bằng snap 2 cm sau khi căn theo tâm camera chung (PLAN §4.8 mục 3): thuộc `eval/`, luồng 1.
- Ghi `scale_anchor.json` cho phòng tự thu: tool chỉ đánh dấu `used_as_anchor=1` trong thước dây/CSV, còn `L_real` và `L_model` do `click_anchor_2d.py` + stage align xử lý.
- `pick` trên mesh GLB lấy đỉnh mesh, không có tuỳ chọn snap vào điểm gần nhất của point cloud.
