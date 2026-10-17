# pipeline/eval/

Trạng thái (M0a): có `metrics.py` với đủ hàm chỉ số (chiều dài, hình học, mặt phẳng, ATE, Δ%, trung bình theo không gian) và test theo số
của đề cương. Chưa có stage chạy trên đầu ra thật, protocol đo chiều dài, bảng B0…Proposed (M3).

## Vai trò

Chấm điểm đầu ra của pipeline (ĐC §20). Ngoài dataflow. Báo đủ chỉ số, không che failure; mỗi nguồn dữ liệu một bảng, không trộn.

Cấu hình so sánh (ĐC Hình 26): **B0** COLMAP, **B1** VGGT, **B3** + fusion, **Proposed** + plane gate, **Ablation 1** (bỏ `q_*`),
**Ablation 2** (ép plane không cổng). B2 (+ UniDepthV2) là mục tiêu mở rộng, không làm ở mốc đầu.

## Input/Output

| | Đường dẫn | Nội dung |
|---|---|---|
| vào | đầu ra các biến thể (`baselines/…/metric/`, `proposed/…`) | point cloud ở mét |
| vào | `ground_truth/measurements.csv` | `id, type, ground_truth_m, used_as_anchor, endpoints/notes` |
| vào | Faro (hoặc `highres_depth` dự phòng) | GT hình học |
| ra | `evaluation/metrics.csv`, `evaluation/logs/`, `evaluation/figures/` | bảng chỉ số theo cấu hình |
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
  3. Mọi biến thể dùng **cùng** cặp điểm vật lý.

## Tham số

| Khoá | Giá trị | Nguồn |
|---|---|---|
| `eval.snap_radius_m` | 0.02 | quyết định của nhóm (2 cm) |
| `eval.mode` | manual | `manual` (chọn trên point cloud) hoặc `auto` (căn cứng, scale cố định) |

## Cách chạy riêng

```bash
# skip (chưa có CLI, dự kiến M3)
python -m pipeline.eval --scene arkitscenes/42444738 --variant proposed
```

## Test vector và tiêu chí đạt

- `tests/test_eval_metrics.py`, phòng R02 (sai số 6, 3, 3, 3, 7, 2 cm trên 3,30; 2,85; 2,40; 0,90; 1,20; 1,40 m): `MAE = 4,0 cm`,
  `Median = 3 cm`, `MAPE ≈ 2,5%` (tính chính xác 2,45%), `%<5 cm = 67%` (4/6).
- Trung bình theo không gian: Chamfer 2,0 (6 `frl_apartment`) và 4,0 (12 scene khác) cho 3,85 cm, trung bình phẳng 3,33 cm.
- Chamfer 2,5 (Acc 2,0, Comp 3,0); F = 0,847 (Prec 0,90, Rec 0,80); P2Plane 1,33 → 0,67 cm; ATE = 2,74 cm (sai 2, 3, 1, 4 cm);
  Δ% = 28% (6,1 → 4,4 cm); PlaneRecall 18/20 = 0,9.
- Tiêu chí đạt (M3): `metrics.csv` đủ sáu cấu hình trên scene dev; báo cả MAE lẫn median (khác nhau khi vài phép đo lệch lớn).

## Lỗi thường gặp

- Đưa đoạn mốc vào chỉ số test: sai số của mốc luôn bằng 0 vì đã dùng để đổi mét (ĐC §8.1).
- Báo trung bình phẳng cho Replica: một căn hộ dễ bị đếm 6 lần, số lạc quan giả; báo theo không gian.
- Chỉnh ngưỡng trên Replica hoặc held-out: ngưỡng khoá trên 6 scene Validation, test chạy một lần.
- So số paper khác giao thức (ScanNet++, RGB-D, pose biết) với số của đề tài (ĐC §22.4).
- Plane metrics trên Replica cần `preseg`/`semantic` mà dữ liệu hiện tại chưa có.

## Người phụ trách

@username3 (theo `.github/CODEOWNERS`).
