# pipeline/eval/

Trạng thái (M3, nhánh `feature/m3-eval`): có `metrics.py` (hàm chỉ số, test theo số đề cương) **và stage `eval`** (`stage.py`, `lengths.py`, `b1.py`, `geometry.py`,
`variants.py`): chấm B0, B1, B3, proposed, abl_quality (Ablation 1) trên một scene, ghi `evaluation/metrics.csv`. **Chưa có:** Ablation 2, P2Plane, PlaneRecall
(theo PDF chuyển sang Replica, M5), bảng chéo scene (`outputs/eval_results/`), tên `endpoints_<variant>.json` do người dùng/luồng chấm tay tạo. Số liệu thật trên scene dev: `docs/notes_eval.md`.

## Vai trò

Chấm điểm đầu ra của pipeline (ĐC §20). Ngoài dataflow. Báo đủ chỉ số, không che failure; mỗi nguồn dữ liệu một bảng, không trộn.

Cấu hình so sánh (ĐC Hình 26): **B0** COLMAP, **B1** VGGT, **B3** + fusion, **Proposed** + plane gate, **Ablation 1** (bỏ `q_*`),
**Ablation 2** (ép plane không cổng). B2 (+ UniDepthV2) là mục tiêu mở rộng, không làm ở mốc đầu.

## Biến thể

| `--variant` | Cấu hình | Point cloud | Cách có |
|---|---|---|---|
| `B0` | COLMAP mét | `baselines/colmap/metric/fused_metric.ply` | stage `align` |
| `B1` | VGGT thuần mét | `baselines/vggt/metric/points_metric.ply` | `eval` tự dựng (`b1.py`): nối chunk bằng Umeyama trên điểm của cùng pixel ở ảnh gối, scale từ mốc tam giác hoá trong hệ VGGT [Suy luận] |
| `B3` | + fusion, không gate | `proposed/fusion/fused_points.ply` | stage `fuse` |
| `proposed` | + plane gate | `proposed/plane_refinement/refined_points.ply` | stage `gate` |
| `abl_quality` | Ablation 1: bỏ `q_*` (fuse với `fusion.use_quality=false`, rồi gate) | `proposed/variants/abl_quality/plane_refinement/refined_points.ply` | `--variant abl_quality --from-stage fuse --to-stage gate` [Suy luận] |

Ablation 2 (ép plane không cổng, `abl_gate`) không có ở đây: theo PDF chấm trên Replica (M5).

## Input/Output

| | Đường dẫn | Nội dung |
|---|---|---|
| vào | đầu ra các biến thể (`baselines/…/metric/`, `proposed/…`) | point cloud ở mét |
| vào | `ground_truth/measurements.csv` | `id, type, ground_truth_m, used_as_anchor, endpoints/notes` |
| vào | `ground_truth/faro/faro_scene_frame.ply` (hệ scene) | GT hình học (Chamfer/F-score) |
| vào | `raw/source.json` → `lowres_wide.traj`, `metadata/keyframes.csv` | tâm camera GT, chỉ để định vị (phép cứng scale = 1) |
| vào (tuỳ chọn) | `evaluation/logs/endpoints_<variant>.json` | đầu mút chọn tay (xem dưới) |
| ra | `evaluation/metrics.csv` | một dòng mỗi biến thể: chiều dài (nhãn `length_mode`), tập chung, ATE, Chamfer/F |
| ra | `evaluation/logs/{lengths_<v>_<mode>.csv, align_<v>.json, eval_result.json}` | từng đoạn, sai số căn, khoảng snap |
| ra | `baselines/vggt/metric/{points_metric.ply, cameras_metric.json, b1_result.json}` | B1 (VGGT thuần, mét) |
| ra | `outputs/eval_results/` | bảng tổng hợp chéo scene (Replica: trung bình theo không gian) |

## Công thức

- Chiều dài: `MAE`, `MAPE`, `Median`, `%<5 cm` (32)–(33); `M` là số phép đo test (**không gồm mốc scale**).
- Hình học: `Acc`, `Comp`, `Chamfer = (Acc+Comp)/2`, `Prec_δ`, `Rec_δ`, `F_δ` với `δ = 5 cm` (34)–(35).
- Mặt phẳng và camera: `P2Plane`, `PlaneRecall` (36); `ATE` sau căn Sim(3) (37).
- Mức cải thiện `Δ% = (m_trước − m_sau)/m_trước × 100%` (31).
- Trung bình theo không gian `m̄ = (1/|G|) Σ_g (1/|g|) Σ_{s∈g} m_s` (7): Replica 18 scene = 13 không gian (6 `frl_apartment` là một).
- **Protocol đo chiều dài** (quyết định của nhóm, ĐC §8.3):
  1. *Ưu tiên (thủ công):* chọn hai đầu mút **trực tiếp trên point cloud mô hình**, đúng vị trí vật lý đã đánh dấu trên GT; lưu vào
     `evaluation/logs/endpoints_<variant>.json`; đo theo (30).
  2. *Chạy hàng loạt (tự động):* đặt đầu mút GT vào hệ mô hình bằng phép **cứng, scale cố định = 1**, rồi snap vào điểm gần nhất
     của point cloud trong **2 cm**. Bắt buộc ghi sai số căn (rms tâm camera, khoảng snap trung bình, số đầu mút không snap được) vào
     `evaluation/logs/` và gắn nhãn `auto` trong bảng.
  3. Mọi biến thể dùng **cùng** cặp điểm vật lý. `metrics.csv` có cột riêng cho **tập chung** (đoạn hợp lệ ở mọi biến thể đang chấm): so sánh B0/B3/… dựa vào cột `*_common`, không dựa vào cột toàn bộ.
- **Giới hạn của chế độ `auto` (đọc trước khi dùng số):** phép căn cứng scale = 1 giữ nguyên khoảng cách giữa hai đầu mút GT, và snap chỉ dời mỗi đầu mút ≤ `eval.snap_radius_m`;
  nên lỗi chiều dài `auto` ≤ 2 × bán kính snap (4 cm) **bất kể mô hình đúng hay sai scale**. Số `auto` chủ yếu cho biết đầu mút có rơi vào vùng được dựng hay không
  (`n_unsnapped_endpoints`, `nn_median_cm`) và độ lệch căn (`ate_rigid_cm`); sai scale lộ ra ở `ate_rigid_cm` và Chamfer/F-score. Phép đo chiều dài thực của mô hình là chế độ `manual`.
- **Chế độ `manual`:** `eval.mode=manual` dùng `evaluation/logs/endpoints_<variant>.json` nếu có, thiếu thì rơi về `auto` và ghi nhãn từng dòng (`length_mode`). Định dạng:
  ```json
  {"scene": "arkitscenes/42444738", "variant": "B0", "unit": "m", "frame": "variant_cloud",
   "endpoints": {"S01": {"a": [x, y, z], "b": [x, y, z]}}}
  ```
  `frame: variant_cloud` = toạ độ trong **đúng file point cloud của biến thể** (bảng Biến thể), không phải hệ đã xoay của `model.glb`; khoá = `id` ở `measurements.csv`; đoạn thiếu = chưa chấm.
- **Chamfer/F-score** (34)(35): mô hình đưa vào hệ scene bằng phép cứng scale = 1 từ tâm camera (cột `*_kabsch`), rồi ICP cứng scale = 1 (cột không hậu tố); Faro và mô hình cắt theo hộp quỹ đạo GT ± lề và voxel hoá.
- `ate_rigid_cm` = rms tâm camera sau phép cứng scale = 1 (cũng là sai số căn của `auto`); `ate_sim3_cm` = ATE sau Sim(3) (37).

## Tham số

| Khoá | Giá trị | Nguồn |
|---|---|---|
| `eval.snap_radius_m` | 0.02 | quyết định của nhóm (2 cm) |
| `eval.mode` | manual | `manual` (chọn trên point cloud, thiếu file thì rơi về auto) hoặc `auto` (căn cứng, scale cố định) |
| `eval.delta_m` | 0.05 | δ của Prec/Rec/F-score [ĐC (35)] |
| `eval.b1.stride` | 4 | bước lấy mẫu pixel của point cloud B1 [Suy luận, TẠM] |
| `eval.b1.c_min` | 0.5 | ngưỡng `c_model` khi nối chunk và dựng B1 [Suy luận, TẠM] |
| `eval.crop_margin_m` | 1.0 | lề quanh hộp quỹ đạo GT khi cắt Faro/mô hình cho Chamfer/F [Suy luận, TẠM] |
| `eval.voxel_m` | 0.02 | voxel trước khi tính Chamfer/F [Suy luận, TẠM] |
| `eval.icp_max_dist_m` | 0.10 | khoảng ghép tối đa của ICP cứng scale = 1 [Suy luận, TẠM] |

## Cách chạy riêng

```bash
# skip (cần dữ liệu thật của scene dev)
python -m pipeline.run --scene arkitscenes/42444738 --config configs/default.yaml --from-stage eval --to-stage eval
```

Ablation 1 (không ghi đè `proposed/`):

```bash
# skip (cần dữ liệu thật của scene dev)
python -m pipeline.run --scene arkitscenes/42444738 --config configs/default.yaml --from-stage fuse --to-stage gate --variant abl_quality
```

Thêm `--variant B0|B1|B3|proposed|abl_quality` ở stage `eval` để chỉ chấm một biến thể (thiếu đầu ra là lỗi); không ghi thì chấm mọi biến thể có đầu ra và bỏ qua phần thiếu (ghi vào `eval_result.json`).

## Test vector và tiêu chí đạt

- `tests/test_eval_metrics.py`, phòng R02 (sai số 6, 3, 3, 3, 7, 2 cm trên 3,30; 2,85; 2,40; 0,90; 1,20; 1,40 m): `MAE = 4,0 cm`,
  `Median = 3 cm`, `MAPE ≈ 2,5%` (tính chính xác 2,45%), `%<5 cm = 67%` (4/6).
- Trung bình theo không gian: Chamfer 2,0 (6 `frl_apartment`) và 4,0 (12 scene khác) cho 3,85 cm, trung bình phẳng 3,33 cm.
- Chamfer 2,5 (Acc 2,0, Comp 3,0); F = 0,847 (Prec 0,90, Rec 0,80); P2Plane 1,33 → 0,67 cm; ATE = 2,74 cm (sai 2, 3, 1, 4 cm);
  Δ% = 28% (6,1 → 4,4 cm); PlaneRecall 18/20 = 0,9.
- Test stage: `tests/test_eval_lengths.py`, `test_eval_b1.py` (3 chunk tổng hợp, Sim(3) và scale biết trước), `test_eval_stage.py` (tường phẳng tổng hợp).
- Tiêu chí đạt (M3): `metrics.csv` đủ cấu hình trên scene dev; báo cả MAE lẫn median (khác nhau khi vài phép đo lệch lớn). Luồng này chỉ có 5 cấu hình (không Ablation 2, xem Biến thể).

## Lỗi thường gặp

- Đưa đoạn mốc vào chỉ số test: sai số của mốc luôn bằng 0 vì đã dùng để đổi mét (ĐC §8.1).
- Báo trung bình phẳng cho Replica: một căn hộ dễ bị đếm 6 lần, số lạc quan giả; báo theo không gian.
- Chỉnh ngưỡng trên Replica hoặc held-out: ngưỡng khoá trên 6 scene Validation, test chạy một lần.
- So số paper khác giao thức (ScanNet++, RGB-D, pose biết) với số của đề tài (ĐC §22.4).
- Plane metrics trên Replica cần `preseg`/`semantic` mà dữ liệu hiện tại chưa có.

## Người phụ trách

@username3 (theo `.github/CODEOWNERS`).
