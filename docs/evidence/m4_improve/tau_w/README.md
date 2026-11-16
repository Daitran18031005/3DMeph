# Chọn lại τ_w theo leave-one-scene-out — KHÔNG ĐẠT quy tắc đặt trước, giữ τ_w = 0,5

Quy tắc: `PLAN.md` (ghi trước khi chạy). Quét (16/11): `scripts/gate_variants.py --name tw0XX --set plane.tau_w=0.X --out-root data/sweeps/m4_tauw`, 6 scene, chỉ chạy lại `gate`.
Áp quy tắc: `python docs/evidence/m4_improve/tau_w/loso.py data/sweeps/m4_tauw/gate_variants.csv`. Dữ liệu: `gate_variants.csv` (bản sao của `data/sweeps/m4_tauw/`).

## Trên cả 6 scene (so với τ_w = 0,5)

| τ_w | Điểm qua cổng | Δ độ chính xác điểm qua (≤ 5 cm) | Scene có điểm bị kéo tốt hơn | ΔF | ΔChamfer | Đạt |
|---|---|---|---|---|---|---|
| 0,4 | ×2,29 | +0,028 | 5 (mốc 5) | −0,0001 | +0,0% | có |
| 0,3 | ×4,26 | +0,032 | 5 | −0,0001 | +0,0% | có |
| 0,2 | ×6,73 | +0,037 | 6 | −0,0001 | +0,0% | có |

Chọn trên 6 scene: 0,2. F và Chamfer gần như không đổi (cổng chỉ dịch điểm ≤ 2,5 cm, F đo ở δ = 5 cm).

## Leave-one-scene-out (quyết định)

| Bỏ scene | Chọn trên 5 scene còn lại | Trên scene bỏ ra: Δ độ chính xác, ΔF | Kiểm |
|---|---|---|---|
| 42897599 | 0,2 | +0,192, +0,0006 | giữ |
| 42898849 | 0,2 | +0,033, −0,0003 | giữ |
| 42897566 | 0,2 | −0,009, −0,0013 | giữ |
| 45662981 | 0,2 | **−0,037**, −0,0012 | hỏng |
| 42445022 | 0,2 | **−0,024**, +0,0000 | hỏng |
| 42444738 (dev) | không giá trị nào đạt | — | — |

Chọn cùng giá trị 5/6 lần (đạt ≥ 5), nhưng qua kiểm trên scene bỏ ra chỉ **3/6** (cần ≥ 5) → **giữ τ_w = 0,5**, không đổi `configs/default.yaml`.

## Đọc kết quả
- Mở cổng có lợi rõ ở scene nhiễu (42897599: độ chính xác điểm qua 0,70 → 0,89) nhưng hại nhẹ ở scene sạch (45662981 0,996 → 0,959; 42445022 0,914 → 0,890): ngưỡng tốt phụ thuộc scene, nên một ngưỡng chung không qua được leave-one-scene-out.
- Bỏ dev thì không giá trị nào đạt vì điều kiện "số scene có điểm bị kéo tốt hơn không ít hơn mốc" (dev là scene duy nhất mốc 0,5 làm xấu đi, 2,07 → 2,23 cm).
- Không thử 0,4 riêng cho leave-one-scene-out (quy tắc chọn giá trị nhỏ nhất đạt; thử thêm sau khi xem số là chỉnh theo kết quả).
- Kết quả phát triển, đáp án Faro; lợi ích thật (P2Plane, plane recall) cần Replica (M5).
