# pipeline/alignment/

Trạng thái (M0a): có `ransac.py` (RANSAC + Umeyama, đổi mét) và test theo ví dụ đề cương. Chưa có stage đọc model
COLMAP/VGGT thật và ghi `chunk_XX_sim3.json` (M1).

## Vai trò

Node **Scale Alignment** của dataflow. Đưa mỗi chunk VGGT về cùng hệ toạ độ với COLMAP, rồi đổi sang **mét** bằng đúng
một mốc dài 1–2 m (ĐC §15, Hình 16). Không có bước này app sẽ hiển thị số đo ở đơn vị tuỳ ý (ĐC §2).

## Input/Output

| | Đường dẫn (trong thư mục scene) | Nội dung | Đơn vị |
|---|---|---|---|
| vào | tâm camera VGGT `x_i = −Rᵀt` từ `baselines/vggt/chunk_XX/vggt_raw.npz` | **tâm camera**, không phải point map hay depth | đv VGGT |
| vào | tâm camera COLMAP `y_i` từ `baselines/colmap/sfm/sparse/0` | | đv COLMAP |
| vào | `ground_truth/scale_anchor.json` | mốc 1–2 m: `L_real`, đầu mút, `used_as_anchor=1` | m |
| ra | `proposed/alignment/chunk_XX_sim3.json`: `s, R, t, n_pairs, n_inliers, rmse` | Sim(3) VGGT→COLMAP **mỗi chunk một lần** | s: đv COLMAP/đv VGGT |
| ra | `proposed/alignment/scale.json`: `s_m, L_real, L_model, anchor_id` | hệ số mét của cả scene | m/đv COLMAP |
| ra | điểm đã ở mét (dùng cho fusion) | `X_mét` | m |

## Công thức

- Umeyama Sim(3) (13)–(17): `y ≈ s R x + t`; `Σxy = U D Vᵀ`, `R = U S Vᵀ`, `s = tr(DS)/σx²`, `t = μy − s R μx`;
  `S = I` nếu `det U · det V ≥ 0`, ngược lại `diag(1, …, 1, −1)`.
- RANSAC trên cặp tâm camera để bền với camera VGGT ước lượng sai (ĐC §15.1): ví dụ 12 cặp, 2 cặp sai, giữ 10 inlier.
  Công cụ chính theo đề cương là pycolmap (`align_reconstructions_via_proj_centers`); bản numpy trong repo làm oracle và dự phòng.
- Mốc scale: `s_m = L_real / L_model` (4), một lần cho cả scene. `L_model` lấy bằng cách click 2D ở ≥ 2 keyframe rồi tam giác
  hóa bằng camera COLMAP (không dùng pose GT, tránh rò rỉ scale).
- Về mét: `X_mét = s_m (s R X_VGGT + t)` (18); `s_tổng = s · s_m`. Ví dụ: bàn 0,215 đv VGGT × 3,20 × 2,00 = 1,376 m ≈ 1,38 m.
- **Mốc không được tính vào phép đo test** (cột `used_as_anchor`): báo "sai số 0 cm" trên chính đoạn mốc là vô nghĩa (ĐC §8.1).

## Tham số

| Khoá | Giá trị | Nguồn |
|---|---|---|
| `align.min_pairs` | 3 | ĐC §15.1 (n ≥ 3 cặp tâm camera) |
| `align.ransac.max_error_ratio` | null | chưa có căn cứ; ngưỡng inlier = tỷ lệ này × khoảng cách camera trung vị |
| `align.anchor_file` | ground_truth/scale_anchor.json | ĐC §9 |

## Cách chạy riêng

```bash
# skip (chưa có CLI, dự kiến M1)
python -m pipeline.alignment --scene arkitscenes/42444738
```

## Test vector và tiêu chí đạt

- `tests/test_geometry.py`: 4 camera `x=(0;0),(2;0),(2;1),(0;1)`, `y=(1,0;2,0),(1,0;8,4),(−2,2;8,4),(−2,2;2,0)` cho
  `s=3,20`, `R` xoay 90° ngược chiều kim đồng hồ, `t=(1,0; 2,0)`; số trung gian `σx²=1,25`, `D=(3,2; 0,8)`.
- `tests/test_alignment.py`: RANSAC loại đúng 2 cặp sai trong 12; chuỗi mét 0,215→0,688→1,376 và `s_tổng=6,40`; 1,62 đv × 2,00 = 3,24 m.
- Tiêu chí đạt (M1): rmse tâm camera sau căn được ghi log; chunk dưới 3 cặp inlier bị loại khỏi fusion.

## Lỗi thường gặp

- Căn bằng point map hoặc depth thay vì tâm camera: sai so với đề cương (kế hoạch cũ đã sửa).
- Dùng chiều dài bàn làm mốc rồi báo "sai số bàn = 0 cm".
- Lấy mốc là khoảng cách giữa hai camera: rò rỉ scale; mốc phải là một đoạn 1–2 m dễ thấy, không nằm trên gương/kính.
- Quên đảo pose ARKit (world→camera) thành camera→world: tâm camera nằm ngoài phòng (ĐC §10.2).
- Mỗi chunk VGGT có gốc riêng nên **căn từng chunk**, không dùng một Sim(3) cho cả scene.
- Đề cương §7.1 nói ảnh gối "căn hai chunk" còn §15.1 căn VGGT→COLMAP; nhóm theo §15.1, ảnh gối chỉ để kiểm tra nhất quán.

## Người phụ trách

@username1 (theo `.github/CODEOWNERS`).
