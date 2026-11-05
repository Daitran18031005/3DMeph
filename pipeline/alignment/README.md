# pipeline/alignment/

Trạng thái (M1c): có `ransac.py` (RANSAC + Umeyama, đổi mét), `anchor.py` (tam giác hoá DLT từng đầu mút mốc độc lập từ click 2D, mỗi đầu mút ≥ 2 ảnh, không cần chung một ảnh) và `stage.py`
(stage `align`: Sim(3) từng chunk theo hai phương pháp `align.method`, `scale.json`, B0 mét). **Mặc định `orientation_depth` là LỆCH so với ĐC §15.1** (căn tâm camera), xem Tham số và Công thức, cộng `scripts/click_anchor_2d.py` (cửa sổ OpenCV để click mốc). Stage chỉ chạy khi
`scale_anchor.json` đã có `L_model` (do `click_anchor_2d.py` điền); `align.ransac.max_error_ratio` đang là 1,5, giá trị TẠM cho M1.

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
| ra | `proposed/alignment/align_result.json` | số chunk nhận/loại, rmse trung vị và lớn nhất | đv COLMAP |
| ra | `baselines/colmap/metric/fused_metric.ply` | B0 mét: `fused.ply` × `s_m` | m |
| ra | điểm đã ở mét (dùng cho fusion) | `X_mét` | m |

## Công thức

- **`orientation_depth` (LỆCH ĐC §15.1):** `R = SVD-trung bình của R_wc,COLMAP,i · R_cw,VGGT,i` (loại view lệch hơn `median + 3·max(1,4826·MAD, 1°)`), `s = median_{(i,k)} ‖X_k − C_i‖ / ‖P_{i,k} − c_i‖` (cùng tia nên tỉ lệ khoảng cách = tỉ lệ depth), `t = median_i (y_i − s R x_i)`. Các hằng số 3·MAD và 1° là [Suy luận]. Scale lấy từ chính điểm MVS nên khi đo lệch VGGT so với COLMAP có một phần tự khớp. Với `align.scale_from = points` (mặc định từ 05/11) `s` thay bằng scale Umeyama điểm VGGT ↔ điểm MVS (`points_scale`); `R` và `t` vẫn như trên, `s_distances` được ghi thêm vào `chunk_XX_sim3.json` để so.
- Umeyama Sim(3) (13)–(17) (`centers`): `y ≈ s R x + t`; `Σxy = U D Vᵀ`, `R = U S Vᵀ`, `s = tr(DS)/σx²`, `t = μy − s R μx`;
  `S = I` nếu `det U · det V ≥ 0`, ngược lại `diag(1, …, 1, −1)`.
- RANSAC trên cặp tâm camera để bền với camera VGGT ước lượng sai (ĐC §15.1): ví dụ 12 cặp, 2 cặp sai, giữ 10 inlier.
  Công cụ chính theo đề cương là pycolmap (`align_reconstructions_via_proj_centers`); bản numpy trong repo làm oracle và dự phòng.
- Mốc scale: `s_m = L_real / L_model` (4), một lần cho cả scene. `L_model` lấy bằng cách click 2D từng đầu mút ở ≥ 2 keyframe rồi tam giác
  hóa độc lập bằng camera COLMAP (không dùng pose GT, tránh rò rỉ scale).
- Về mét: `X_mét = s_m (s R X_VGGT + t)` (18); `s_tổng = s · s_m`. Ví dụ: bàn 0,215 đv VGGT × 3,20 × 2,00 = 1,376 m ≈ 1,38 m.
- **Mốc không được tính vào phép đo test** (cột `used_as_anchor`): báo "sai số 0 cm" trên chính đoạn mốc là vô nghĩa (ĐC §8.1).

## Tham số

| Khoá | Giá trị | Nguồn |
|---|---|---|
| `align.method` | orientation_depth | `centers` = ĐC §15.1 (tâm camera, RANSAC + Umeyama). `orientation_depth` = LỆCH ĐC (đã được người dùng duyệt 27/10): xoay R từ hướng camera, scale từ tỉ lệ khoảng cách camera→điểm MVS, tịnh tiến từ tâm camera. Lý do: 6/11 chunk trên 42444738 trải tâm camera < 0,6 m nên căn tâm camera kém điều kiện (lệch VGGT so với COLMAP trung vị 36,8 cm, p90 119 cm); phương pháp mới còn 8,9 cm, p90 21 cm (chưa phải sai số so với GT) |
| `align.scale_from` | points | Chỉ cho `orientation_depth`. `points`: scale khớp điểm VGGT ↔ điểm MVS của chunk (Umeyama (14)–(17), 4 vòng giữ 80% cặp ít lệch nhất [Suy luận]), giữ đúng khoảng cách giữa hai điểm. `distances`: trung vị tỉ lệ khoảng cách camera→điểm (cách cũ). Lý do (05/11, 42444738): `distances` thấp hơn scale điểm 3,8–18,8% theo chunk nên điểm VGGT co 4–17% (tỉ lệ độ dài VGGT/MVS 0,83–0,96, sau sửa 0,91–1,04); LỆCH ĐC §15.1 |
| `align.min_pairs` | 3 | ĐC §15.1 (n ≥ 3 cặp tâm camera); cũng là số view đăng ký tối thiểu của `orientation_depth` |
| `align.ransac.max_error_ratio` | 1.5 | TẠM cho M1: ngưỡng inlier = tỷ lệ này × khoảng cách camera COLMAP trung vị của chunk. Chọn trên 42444738 từ dãy 0,05–3,0: nhỏ nhất trên cao nguyên (≥ 1,5 giữ 112/112 cặp, nghiệm không đổi), CV chéo 50/50 và nhất quán ảnh gối tốt nhất; khoá lại ở M2 trên Validation |
| `align.anchor_file` | ground_truth/scale_anchor.json | ĐC §9 |

## Cách chạy riêng

```bash
# skip (cần stage sfm, vggt đã chạy; click bằng GUI)
python scripts/click_anchor_2d.py --scene arkitscenes/42444738
python -m pipeline.run --scene arkitscenes/42444738 --from-stage align --to-stage align
```

## Test vector và tiêu chí đạt

- `tests/test_geometry.py`: 4 camera `x=(0;0),(2;0),(2;1),(0;1)`, `y=(1,0;2,0),(1,0;8,4),(−2,2;8,4),(−2,2;2,0)` cho
  `s=3,20`, `R` xoay 90° ngược chiều kim đồng hồ, `t=(1,0; 2,0)`; số trung gian `σx²=1,25`, `D=(3,2; 0,8)`.
- `tests/test_alignment_stage.py`: chunk tổng hợp khôi phục đúng `s=3,2`, `R` xoay 90°, `t`; camera lệch 5 đv bị loại (11/12 inlier); chunk dưới 3 view đã đăng ký bị loại kèm lý do;
  `ratio = null` và thiếu chunk báo lỗi; `orientation_depth` khôi phục đúng `s`, `R` ngay cả khi tâm camera thẳng hàng và nhiễu (xoay sai < 0,5° trong khi `centers` sai hơn 3°), loại view lệch hướng, từ chối chunk ít view, `run_align` ghi `method`; `s_m = L_real / L_model` và B0 mét nhân đúng tỉ lệ.
- `tests/test_click_anchor_2d.py`: DLT chính xác khi không nhiễu, `L_model` đúng, nhiễu 1 px cho lệch < 5%, từ chối 1 ảnh; từng đầu mút tam giác hoá độc lập ở ảnh riêng (A ở 3 ảnh, B ở 2 ảnh khác, không ảnh nào có cả hai), từ chối đầu mút chỉ có 1 ảnh; `--from-json` ghi `L_model` giữ các khoá cũ và chặn ghi đè.
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
