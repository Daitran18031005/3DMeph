# configs/

`default.yaml` chứa mọi tham số của pipeline, tách khỏi code để dễ ghi lại trong chương Thực nghiệm. Mỗi khoá được mô tả ở README của module
sở hữu nó (tiền tố khoá → module):

| Tiền tố | README |
|---|---|
| `keyframe.*` | [pipeline/keyframe](../pipeline/keyframe/README.md) |
| `quality.*` | [pipeline/common](../pipeline/common/README.md) |
| `colmap.*` | [pipeline/colmap](../pipeline/colmap/README.md) |
| `vggt.*` | [pipeline/vggt](../pipeline/vggt/README.md) |
| `align.*` | [pipeline/alignment](../pipeline/alignment/README.md) |
| `fusion.*` | [pipeline/fusion](../pipeline/fusion/README.md) |
| `plane.*` | [pipeline/plane_gate](../pipeline/plane_gate/README.md) |
| `export.*` | [pipeline/export](../pipeline/export/README.md) |
| `eval.*` | [pipeline/eval](../pipeline/eval/README.md) |
| `loss.*`, `paths.*` | bảng bên dưới |

`scripts/check_docs.py` đối chiếu hai chiều: khoá có trong `default.yaml` phải có trong README sở hữu, và khoá ghi trong README phải có thật.

## Quy ước giá trị

- **Có số kèm nguồn**: lấy từ đề cương (ĐC §x hoặc công thức (n)) và ghi nhãn "ví dụ" nếu đề cương gọi là ví dụ/minh họa. Các ngưỡng này vẫn
  phải khoá trên Validation (ĐC §12).
- **`null`**: đề cương không có số hoặc số phải đo trên dữ liệu (`quality.v_ref.vga`, `quality.g_ref.vga`, `keyframe.blur.q_drop`,
  `align.ransac.max_error_ratio`, `colmap.matcher_overlap`, `colmap.max_image_size`, `loss.alpha_r`). Mã gọi `require()` sẽ báo lỗi thay vì đoán.
- **Số 581** trong đề cương (`V_ref` trung vị 40 scene, đo trên `lowres_wide` 256×192, gồm cả scene sẽ làm held-out) **không** được dùng làm
  cấu hình; `V_ref`, `G_ref` đo lại trên `vga_wide` của 6 scene Validation.
- Ký hiệu theo đề cương: `tau_e`, `tau_sigma` (không phải `λ`); hai hệ số α khác nhau là `plane.alpha` (25) và `loss.alpha_r` (29).

## Quy trình khoá tham số

1. Đo `V_ref`, `G_ref` trên `vga_wide` của 6 scene Validation (`data/splits.csv`, split = `val`); ghi kèm `measured_on`, số scene, ngày đo.
2. Thử lưới ngưỡng (ví dụ `plane.tau_r ∈ {3, 5, 8} cm`) trên 6 scene Validation, chọn theo F-score (ĐC §12), ghi vào `default.yaml`.
3. Chạy held-out và Replica **đúng một lần** với tham số đã khoá; không quay lại sửa ngưỡng sau khi thấy kết quả test.

## Tham số

Các khoá không thuộc module nào:

| Khoá | Giá trị | Nguồn |
|---|---|---|
| `loss.alpha_r` | null | (29): hệ số phạt `L_reg` của confidence head; mốc sau, chưa dùng |
| `paths.colmap_exe` | `${COLMAP_EXE}` | biến môi trường; mặc định `../colmap/bin/colmap.exe` so với repo |
| `paths.data_root` | data/scenes | cây thư mục Mục 9 (ĐC §9) |
| `paths.splits` | data/splits.csv | danh sách train/val/heldout (đã sinh bằng `scripts/select_scenes.py`) |
