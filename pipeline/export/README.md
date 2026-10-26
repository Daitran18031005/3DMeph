# pipeline/export/

Trạng thái (M0a): có `measure.py` (đo hai điểm theo (30), có CLI). Chưa có phần dựng mesh và ghi GLB (M1).

## Vai trò

Node **GLB Mesh Output** của dataflow. Biến point cloud đã làm phẳng thành mesh GLB đơn vị mét, và cung cấp công cụ đo hai
điểm thay cho thao tác chạm trong Unity (mốc đầu chưa làm Unity, ĐC §19.1). **Phương pháp dựng mesh không có trong đề cương**:
Poisson (Open3D) + trimesh là quyết định của nhóm. Chỉ số hình học (34)–(35) tính trên **điểm** `P`, không tính trên mesh.

## Input/Output

| | Đường dẫn (trong thư mục scene) | Nội dung | Đơn vị |
|---|---|---|---|
| vào | `proposed/plane_refinement/refined_points.ply` | điểm sau (25) | m |
| ra | `proposed/export/model.glb` (và `model.ply`) | mesh | m, trục +Y là lên |
| ra | `proposed/export/measurements.json` | các đoạn test đã đo, mốc, `s_m` | m |
| ra | `run_meta.json` | thời gian, peak VRAM, hash cấu hình, mã lỗi | |

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

## Cách chạy riêng

```bash
# check
python -m pipeline.export.measure --a 0.52 0.75 1.20 --b 1.90 0.75 1.20
```
```bash
# skip (cần model.glb thật; dự kiến M1)
python -m pipeline.export.measure --glb data/scenes/arkitscenes/42444738/proposed/export/model.glb --a 0 0 0 --b 1 0 0
```

## Test vector và tiêu chí đạt

- `tests/test_measure.py`: `‖B − A‖ = 1,38 m`; `1,38² = 1,9044`; CLI in `1.380 m`.
- Tiêu chí đạt (M1): `model.glb` mở được bằng trimesh, kích thước hộp bao hợp lý theo mét; `measure` đo được ít nhất một đoạn.

## Lỗi thường gặp

- GLB không đúng hướng (trục lên không phải +Y): mesh nằm ngang khi xem.
- Mesh Poisson bịa mặt ở vùng thiếu điểm: cắt theo mật độ; kết quả chấm vẫn tính trên point cloud.
- Chấm sai số trên đoạn mốc (`used_as_anchor=1`): phải loại khỏi chỉ số test.

## Người phụ trách

@username3, @username4 (theo `.github/CODEOWNERS`).
