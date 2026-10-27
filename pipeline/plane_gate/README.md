# pipeline/plane_gate/

Trạng thái (M1d): có `gate.py` (cổng, chiếu, ép phẳng cho ablation, góc; test bảng P1–P7 của đề cương) và `stage.py` (stage `gate`: hướng lên từ camera,
RANSAC tuần tự tìm mặt phẳng, nhãn sàn/trần/tường, cổng (24), chiếu (25), ghi file), có test tổng hợp. Đã chạy thật trên 42444738 (số đo ở `WORKING_LOG.md`).

## Vai trò

Node **Plane-Gated Filter** của dataflow. Kéo nhẹ điểm sát tường/sàn/trần về đúng mặt phẳng, **chỉ khi chắc đó là cấu trúc**;
bàn, ghế, rèm, cây để nguyên (ĐC §17). Mục tiêu: giảm plane error mà F-score vật thể phi phẳng không giảm.

Điểm **không qua cổng vẫn nằm trong kết quả**, giữ nguyên toạ độ (ĐC Hình 20 "g = 0 giữ nguyên điểm"). Ghi chú trên sơ đồ
dataflow ("chỉ điểm qua gate mới vào GLB") khác đề cương; mặc định theo đề cương.

## Input/Output

| | Đường dẫn (trong thư mục scene) | Nội dung | Đơn vị |
|---|---|---|---|
| vào | `proposed/fusion/fused_points.ply` | `x, y, z, w_k` | m |
| ra | `proposed/plane_refinement/refined_points.ply`: `x, y, z, w_k, g, plane_id` | điểm sau (25); điểm không qua cổng giữ nguyên (`g = 0`) | m |
| ra | `proposed/plane_refinement/planes.json` | hướng lên `up` (và cách tinh chỉnh), mỗi mặt phẳng: `n, d`, nhãn, độ cao, số inlier, tham số đã dùng | m |
| ra | `proposed/plane_refinement/gate_log.csv` | `point, plane_id, label, r_m, theta_deg, w_k, g, displacement_m` mỗi điểm | |
| ra | `proposed/plane_refinement/gate_result.json` | tỉ lệ qua cổng và tỉ lệ qua từng điều kiện | |

## Công thức

- Mặt phẳng `π: nᵀx + d = 0`, `‖n‖ = 1`; `r_k = |nᵀP_k + d|` (23).
- **Cổng** `g_k = 1[ r_k < τ_r ∧ θ_k < τ_n ∧ s_k ∈ S_struct ∧ w_k > τ_w ]` (24): đủ **bốn** điều kiện mới được kéo.
  `S_struct = {tường, sàn, trần}`; `θ_k` là góc giữa pháp tuyến cục bộ và `n` trong [0°, 90°]; `w_k` lấy từ [fusion](../fusion/README.md).
- **Chiếu** `P'_k = P_k − α g_k (nᵀP_k + d) n`, `0 < α ≤ 1` (25).
- **Hướng "lên" và nhãn `s_k`** (quyết định của nhóm, đề cương không nêu khi không có nhãn): ảnh đã xoay đứng nên "lên" trong camera là (0, −1, 0);
  `u₀` = trung bình hướng đó trong hệ thế giới qua các camera, tinh chỉnh bằng mặt phẳng ngang lớn nhất có pháp tuyến trong 20° quanh `u₀`.
  Sàn/trần là mặt phẳng có pháp tuyến song song `u` (sàn thấp hơn tâm camera, trần cao hơn); tường có pháp tuyến vuông góc `u`.
- **Ablation 2** (ĐC §20.1): `plane.force=true` kéo **mọi** điểm về mặt phẳng gần nhất, không cổng: mặt bàn cách sàn 75 cm bị dịch 0,5 × 75 = 37,5 cm.
- Các điều kiện "inlier ratio" và "depth continuity" trên sơ đồ dataflow **không có** trong đề cương; chưa triển khai.

## Tham số

| Khoá | Giá trị | Nguồn |
|---|---|---|
| `plane.tau_r` | 0.05 | ĐC §17.1 (m, ví dụ); khoá trên Validation |
| `plane.tau_n_deg` | 15 | ĐC §17.1 (độ, ví dụ); khoá trên Validation |
| `plane.tau_w` | 0.5 | ĐC §17.1 (ví dụ); khoá trên Validation |
| `plane.alpha` | 0.5 | ĐC §17.2 (ví dụ); khác `loss.alpha_r` |
| `plane.up_refine_deg` | 20 | quyết định của nhóm (tinh chỉnh hướng lên) |
| `plane.force` | false | `true` = Ablation 2 |
| `plane.max_planes` | 8 | TẠM cho M1 [Suy luận]: số mặt phẳng RANSAC tuần tự tối đa |
| `plane.min_inlier_fraction` | 0.02 | TẠM cho M1 [Suy luận]: mặt phẳng phải có ≥ tỉ lệ này số điểm |
| `plane.normal_knn` | 30 | TẠM cho M1 [Suy luận]: số láng giềng của PCA pháp tuyến cục bộ (`θ_k`, và Poisson ở export) |

## Cách chạy riêng

```bash
# skip (cần stage fuse đã chạy)
python -m pipeline.run --scene arkitscenes/42444738 --from-stage gate --to-stage gate
```

## Test vector và tiêu chí đạt

- `tests/test_m1d_stages.py`: phòng tổng hợp (sàn y=0, trần y=2,5, tường) nhận đúng 3 mặt phẳng floor/ceiling/wall với độ cao 0 và 2,5 m; `camera_up` = −y camera; `refine_up` kéo hướng lên nghiêng 5,7° về
  dưới 1,5°; stage `gate` kéo điểm sàn qua cổng còn khoảng một nửa độ lệch (α = 0,5), điểm không qua cổng giữ nguyên, `w_k ≤ τ_w` thì không điểm nào qua cổng.
- `tests/test_plane_gate.py`, bảng §17.2 với `α=0,5`, `τ_r=5 cm`, `τ_n=15°`, `τ_w=0,5` (P1…P7):
  `g = 1,1,0,0,0,1,0`; dịch 0,6 / 1,0 / 0,4 cm; P1 từ (0,012; 1,5; 1,2) thành (0,006; 1,5; 1,2).
  P3 loại vì `r > 5 cm`, P4 vì không phải cấu trúc, P5 vì `w < 0,5`, P7 (mặt bàn) vì không thuộc cấu trúc.
- Ép phẳng (Ablation 2) làm mặt bàn P7 dịch 37,5 cm; từng điều kiện trong bốn điều kiện đều bắt buộc.
- Tiêu chí đạt (M3–M4): point-to-plane giảm (mục tiêu 15–20%, chưa phải kết quả) mà F-score vật thể không giảm đáng kể (ĐC §21).

## Lỗi thường gặp

- Hiểu gate là "làm phẳng mọi thứ": thực tế cổng bốn điều kiện, đồ vật phi phẳng giữ nguyên.
- Dùng khoảng cách có dấu trong cổng: cổng dùng `r_k` (trị tuyệt đối); bước chiếu mới dùng `nᵀP + d` có dấu.
- Nhầm `plane.alpha` (25) với `loss.alpha_r` (29): hai hệ số khác nhau.
- Hướng "lên" sai (không xoay ảnh theo `sky_direction` trước): nhãn sàn/trần/tường đảo lộn.

## Người phụ trách

@username3 (theo `.github/CODEOWNERS`).
