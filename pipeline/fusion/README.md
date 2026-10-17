# pipeline/fusion/

Trạng thái (M0a): có `fusion.py` (trọng số, chuẩn hóa, ghép, `w_k`) và test theo ví dụ đề cương. Chưa có stage lấy mẫu tín hiệu
từ dữ liệu thật và ghi `fused_points.ply` (M1).

## Vai trò

Node **Confidence Fusion** của dataflow. Mỗi view cho một "phiếu bầu" vị trí của điểm; view nét, hình học khớp được phiếu
nặng, view mờ hoặc nhìn qua gương gần như không có phiếu (ĐC §16). Kết quả là một điểm đã ghép `P̂_k` và trọng số `w_k`
chuyển cho [plane_gate](../plane_gate/README.md).

Chỉ số: **i = view, k = điểm/correspondence**. Điểm `k` là điểm của `stereo_fusion` (MVS dày); `V_k` đọc từ
`fused.ply.vis`. `P_{i,k}` là vị trí VGGT dự đoán ở view i: chiếu `k` vào view i bằng camera COLMAP rồi lấy mẫu song tuyến
bản đồ điểm VGGT (đã sang mét). COLMAP chỉ cho tín hiệu; nhánh VGGT mới là "người bỏ phiếu".

## Input/Output

| | Đường dẫn (trong thư mục scene) | Nội dung | Đơn vị |
|---|---|---|---|
| vào | `baselines/colmap/mvs/fused.ply`, `fused.ply.vis` | điểm `k` và tập view `V_k` | đv COLMAP |
| vào | `proposed/alignment/` | Sim(3) từng chunk, `scale.json` | |
| vào | `baselines/vggt/chunk_XX/vggt_out.npz` | `c_model`, điểm VGGT | |
| vào | `baselines/colmap/sfm/e_reproj_map/`, `baselines/colmap/mvs/sigma_depth/` | `e_reproj` (px), `σ_depth` (đổi sang **mét** bằng `s_m`) | |
| vào | `metadata/keyframes.csv` | `q_blur_i`, `q_exposure_i` (theo view) | |
| ra | `proposed/fusion/fused_points.ply`: `x, y, z, w_k, n_views` | điểm đã ghép | m |
| ra | `proposed/fusion/fusion_log.npz`: `view, point, c_model, f_e, f_sigma, q_blur, q_texture, q_exposure, w, w_tilde` | log **theo (i, k)** ("bảng trước/sau, log trọng số", ĐC §25) | |

## Công thức

- Trọng số **thô**: `w_{i,k} = c_model · e^{−e_reproj/τ_e} · e^{−σ_depth/τ_σ} · q_blur · q_texture · q_exposure` (19).
  Theo (i,k): `c_model, e_reproj, σ_depth, q_texture`; theo view i: `q_blur, q_exposure`. Phép nhân: một tín hiệu rất thấp hạ cả view.
- Đổi sai số thành điểm tin cậy `f(x) = e^{−x/τ}` (21): `f(0)=1`, `f(τ)=0,37`, `f(2τ)=0,14`.
- `q_texture = min(1, ‖∇I‖_{N(k)} / G_ref)` với cửa sổ 15×15 (20).
- Trọng số **đã chuẩn hóa** `w̃_{i,k} = w_{i,k} / Σ_{j∈V_k} w_{j,k}` và `P̂_k = Σ_i w̃_{i,k} P_{i,k}` (22).
- **`w_k = Σ_i w̃_{i,k} · w_{i,k}`**: trọng số tin cậy của điểm đã ghép chuyển sang cổng (24). Đề cương chỉ nói "từ fusion";
  đây là quyết định của nhóm (ví dụ A/B/C: 0,79; trung bình cộng thô 0,52 sát ngưỡng 0,5; max 0,895).
- Không xoá view có `w ≈ 0` ("thuật toán không xóa ảnh C, nó hạ phiếu xuống dưới 1%", ĐC §16.4). Điểm có tổng `w` bằng 0: chia đều
  cho view nhìn thấy để tránh NaN (suy luận, nên ghi log).
- Ngoài vùng nội suy `e_reproj`: gán `e_cap_px` (suy luận). View nằm trong hai chunk (ảnh gối): chọn chunk mà view xa biên hơn (suy luận).

## Tham số

| Khoá | Giá trị | Nguồn |
|---|---|---|
| `fusion.tau_e` | 2.0 | ĐC §16.1: px, "minh họa"; khoá trên Validation |
| `fusion.tau_sigma` | 0.20 | ĐC §16.1: m, "minh họa"; khoá trên Validation |
| `fusion.e_cap_px` | 4.0 | Suy luận (ngưỡng RANSAC 1–4 px, ĐC §14.1) |
| `fusion.use_quality` | true | `false` là Ablation 1: bỏ `q_blur, q_texture, q_exposure` |

## Cách chạy riêng

```bash
# skip (chưa có CLI, dự kiến M1)
python -m pipeline.fusion --scene arkitscenes/42444738 --variant proposed
```

## Test vector và tiêu chí đạt

- `tests/test_fusion.py`, ví dụ ba ảnh A/B/C của §16.4 (độ sâu 2,00/2,08/3,40 m): `w = 0,895/0,659/0,012`;
  `w̃ = 0,571/0,421/0,008`; `P̂ = 2,04 m` (thật 2,05 m); trung bình đơn giản 2,49 m; ảnh C còn dưới 1% phiếu.
- `f(e)` với `τ=2 px` cho 0,97/0,92/0,30; `w_k = 0,789` với A/B/C; một view thì `w_k = w`.
- Tiêu chí đạt (M1–M3): tổng `w̃` mỗi điểm bằng 1; B3 (fusion không gate) tốt hơn B0 và B1 trên scene dev.

## Lỗi thường gặp

- Gọi trọng số thô là `w̃`, hoặc dùng `λ` thay `τ` (ghi chú cũ làm vậy): theo PDF thô là `w`, chuẩn hóa là `w̃`, thang là `τ`.
- Quên đổi `σ_depth` từ đv COLMAP sang mét trước khi chia cho `τ_σ = 0,20 m`.
- Nói "bốn loại confidence": đúng là **sáu tín hiệu, ba nhóm** (model uncertainty, geometric evidence, image quality; ĐC §23).
- Dùng `V_ref`, `G_ref` chưa đo: hàm `q_blur`, `q_texture` báo lỗi khi tham số là `null` thay vì đoán.

## Người phụ trách

@username3 (theo `.github/CODEOWNERS`).
