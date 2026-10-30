# pipeline/export/

Trạng thái (M1d + công cụ đo): có `measure.py` (đo hai điểm theo (30), có CLI; thư viện đầu mút, thước dây, so sánh cho `scripts/pick_endpoints.py`, GUI chọn điểm **chưa chạy thật**) và `mesh.py` (stage `export`: pháp tuyến PCA hướng camera, Poisson, cắt mật độ thấp, xoay hướng lên về +Y, ghi `model.glb`). Đã chạy thật trên 42444738.

## Vai trò

Node **GLB Mesh Output** của dataflow. Biến point cloud đã làm phẳng thành mesh GLB đơn vị mét, và cung cấp công cụ đo hai
điểm thay cho thao tác chạm trong Unity (mốc đầu chưa làm Unity, ĐC §19.1). **Phương pháp dựng mesh không có trong đề cương**:
Poisson (Open3D) + trimesh là quyết định của nhóm. Chỉ số hình học (34)–(35) tính trên **điểm** `P`, không tính trên mesh.

## Input/Output

| | Đường dẫn (trong thư mục scene) | Nội dung | Đơn vị |
|---|---|---|---|
| vào | `proposed/plane_refinement/refined_points.ply` | điểm sau (25) | m |
| vào | `proposed/plane_refinement/planes.json`, `proposed/alignment/scale.json` | hướng lên `up`, `s_m` (tâm camera COLMAP × `s_m` để hướng pháp tuyến) | m |
| ra | `proposed/export/model.glb`, `model_points.ply` | mesh và điểm trong cùng hệ mô hình | m, trục +Y là lên, sàn y = 0 |
| ra | `proposed/export/measurements.json` | hộp bao, số đỉnh/mặt, phép biến đổi hệ COLMAP×s_m → mô hình, danh sách đoạn đã đo (`segments`, hiện rỗng) | m |
| ra | `run_meta.json` | thời gian, peak VRAM, hash cấu hình, mã lỗi | |
| ra (`scripts/pick_endpoints.py`) | `evaluation/logs/endpoints_<variant>.json` | đầu mút chọn tay trên mô hình (định dạng bên dưới); luồng eval đọc file này | m |
| ra (`scripts/pick_endpoints.py tape`) | `ground_truth/tape_measurements.json` | GT thước dây: mỗi đoạn `measure.tape_readings` lần đo và trung vị; `tape --write-csv` ghi `ground_truth/measurements.csv` [ĐC §9] | m |

### Định dạng `endpoints_<variant>.json` (hợp đồng với `eval/`)

```json
{"version": 1, "scene": "arkitscenes/42444738", "variant": "proposed",
 "frame": "model: mét, +Y lên, sàn y=0",
 "points_file": "proposed/export/model_points.ply", "points_sha256": "<sha256 của file điểm>",
 "created": "2026-10-31T01:21:32", "updated": "2026-10-31T01:21:36",
 "segments": [
   {"id": "S01", "a": [x, y, z], "b": [x, y, z], "length_m": 0.7391,
    "variant": "proposed", "source": "manual", "a_index": 123, "b_index": 456, "note": ""}]}
```

- `id` trùng `id` trong `ground_truth/measurements.csv` (khoá ghép cặp với GT). Cờ `used_as_anchor` chỉ nằm ở `measurements.csv`; đoạn mốc scale phải bị loại khỏi chỉ số test.
- `frame` do công cụ tự đặt theo `points_file` (`frame_of_points_file`): `model_points.ply` / `model.glb` → `"model: mét, +Y lên, sàn y=0"`; file khác (point cloud của biến thể, ví dụ
  `baselines/colmap/metric/fused_metric.ply`, `baselines/vggt/metric/points_metric.ply`) → `"variant_cloud"`. `eval` đọc cả hai: hệ model được đổi về hệ COLMAP × `s_m` bằng
  `proposed/export/measurements.json["frame"]` (`x_cm = Rᵀ(x_model − t)`); chỉ đúng cho B0, B3, proposed, abl_quality. B1 ở hệ chuỗi VGGT nên phải chọn trực tiếp trên `points_metric.ply`
  hoặc để `eval` truyền từ `endpoints_proposed.json` bằng phép cứng theo tâm camera (xem [eval](../eval/README.md)).
- `a`, `b`: toạ độ trong hệ `frame` ở trên (mét). `a_index`, `b_index`: chỉ số điểm đã chọn trong file đó (`null` nếu nhập bằng `add`). `source` hiện luôn là `manual`.
- `points_sha256`: nếu file điểm bị dựng lại thì toạ độ cũ không còn đúng; công cụ từ chối ghi thêm/so sánh khi hash lệch.
- Khoảng cách `length_m` = `‖B − A‖` theo (30). Phép cứng không đổi khoảng cách nên so với GT không cần đổi hệ.

## Công thức

- Đo hai điểm: `‖B − A‖₂ = √((x_B − x_A)² + (y_B − y_A)² + (z_B − z_A)²)` (30). Ví dụ A=(0,52; 0,75; 1,20), B=(1,90; 0,75; 1,20) cho 1,38 m.
  Mô hình đã ở mét nên không đổi đơn vị thêm.
- Dựng mesh: pháp tuyến từ PCA hướng về tâm camera; Poisson depth 8–9; cắt vùng mật độ thấp; ghi bằng `trimesh`. glTF dùng +Y là lên nên
  xoay thế giới (hướng lên `u` đã biết ở [plane_gate](../plane_gate/README.md)) về +Y khi ghi. Đây đều là suy luận của nhóm.

## Tham số

| Khoá | Giá trị | Nguồn |
|---|---|---|
| `export.poisson_depth` | 9 | Suy luận (8–9) |
| `export.up_axis` | y | glTF dùng +Y là lên |
| `export.density_quantile` | 0.05 | TẠM cho M1 [Suy luận]: bỏ đỉnh Poisson có mật độ dưới phân vị này |
| `measure.tape_readings` | 3 | ĐC §8.3: đo thước dây 3 lần, lấy trung vị |
| `measure.anchor_min_m` | 1.0 | ĐC §8.1: mốc scale dài 1–2 m |
| `measure.anchor_max_m` | 2.0 | ĐC §8.1 |
| `measure.under_cm` | 5.0 | ngưỡng của chỉ số %<ngưỡng (mục tiêu ĐC §21: median < 5 cm) |

## Cách chạy riêng

```bash
# check
python -m pipeline.export.measure --a 0.52 0.75 1.20 --b 1.90 0.75 1.20
```
```bash
# skip (cần model.glb thật từ stage export)
python -m pipeline.export.measure --glb data/scenes/arkitscenes/42444738/proposed/export/model.glb --a 0 0 0 --b 1 0 0
```

Chọn đầu mút trên mô hình và so với thước dây (`scripts/pick_endpoints.py`; thư viện ở `measure.py`):

```bash
# skip (pick mở cửa sổ Open3D, cần màn hình; GUI chưa chạy thật)
python scripts/pick_endpoints.py pick --scene arkitscenes/42444738 --variant proposed
```
```bash
# skip (ghi file vào thư mục scene)
python scripts/pick_endpoints.py tape --scene arkitscenes/42444738 --id S01 --readings 1.234 1.236 1.235
python scripts/pick_endpoints.py compare --scene arkitscenes/42444738 --gt tape
```

`compare` in sai số từng đoạn và MAE, median, MAPE, %<`measure.under_cm` (hàm của `eval/metrics.py`), loại đoạn mốc scale.

## Test vector và tiêu chí đạt

- `tests/test_m1d_stages.py`: elip 4×1×2 m với hướng lên +z thành GLB mở được bằng trimesh, hộp bao đúng và độ cao 2 m ở trục y; pháp tuyến lật về camera gần nhất; `rotation_up_to_y` đưa mọi `u` về +Y.
- `tests/test_measure.py`: `‖B − A‖ = 1,38 m`; `1,38² = 1,9044`; CLI in `1.380 m`.
- `tests/test_pick_endpoints.py` (15 test, GUI là bản giả): đọc/ghi endpoints và từ chối khi hash file điểm lệch; trung vị 3 lần đo và mốc 1–2 m; `compare` loại mốc (ví dụ GT 3,00 m, mô hình 3,04 m cho sai số 4 cm); vòng `pick`; CLI trên scene giả, chặn held-out.
- Tiêu chí đạt (M1): `model.glb` mở được bằng trimesh, kích thước hộp bao hợp lý theo mét; `measure` đo được ít nhất một đoạn.

## Lỗi thường gặp

- GLB không đúng hướng (trục lên không phải +Y): mesh nằm ngang khi xem.
- Mesh Poisson bịa mặt ở vùng thiếu điểm: cắt theo mật độ; kết quả chấm vẫn tính trên point cloud.
- Chấm sai số trên đoạn mốc (`used_as_anchor=1`): phải loại khỏi chỉ số test.

## Người phụ trách

@username3, @username4 (theo `.github/CODEOWNERS`).
