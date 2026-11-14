# Sửa cổng plane gate (M4 đợt 3d): kết quả

Kế hoạch và quy tắc nhận ĐẶT TRƯỚC khi chạy: `PLAN.md` (cùng thư mục). Mốc git trước khi sửa: `3100e8b`. `proposed/` hiện có KHÔNG bị ghi đè (băm kiểm trước/sau cho từng scene); các biến thể ghi vào
`data/scenes/arkitscenes/<scene>/proposed/variants/gate_*/plane_refinement/`. Số liệu thô: `gate_variants.csv`. Mã: `pipeline/plane_gate/stage.py` (`restrict_horizontal`, `find_planes`), `scripts/gate_variants.py`.
Chỉ số đọc thế nào: "qua cổng" = tỉ lệ điểm được kéo về mặt phẳng; "chính xác của điểm qua" = tỉ lệ điểm qua cổng cách Faro ≤ 5 cm; "sai số điểm bị kéo trước → sau" = khoảng cách trung vị tới Faro trước và sau khi kéo (căn Kabsch + ICP một lần, dùng chung cho mọi biến thể); F-score và Chamfer tính trên toàn cloud sau cổng đúng đường `eval`.

## Đã sửa gì và vì sao
| Biến thể | Thay đổi | Lý do (bằng chứng ở `../gate_diagnosis/README.md`) |
|---|---|---|
| `gate_base` | không đổi (kiểm script tái lập đúng số `proposed`) | mốc so sánh |
| `gate_A` | sàn = mặt ngang THẤP NHẤT, trần = mặt ngang CAO NHẤT, mặt ngang khác nhãn `horizontal_other` (không thuộc S_struct); thiếu tường thì chạy thêm tối đa 4 lượt RANSAC mặt đứng | mục A, E, H: 4–8 "sàn" mỗi scene ở nhiều độ cao; 42898849 có 8 sàn và 0 tường |
| `gate_Ab` | như `gate_A` nhưng mặt ngang cách mặt thấp nhất ≤ 0,10 m vẫn là sàn | mục H: sàn dev bị tách, mặt cao hơn 0,08 m có 81 nghìn điểm (thêm so với yêu cầu, xem "Khác với yêu cầu") |
| `gate_B100`, `gate_B300` | pháp tuyến tính từ 100 và 300 láng giềng (cũ: 30), nhãn cũ | mục D: θ trung vị 24–39° ở k = 30 nhưng 10–25° ở k = 300 |
| `gate_AB` | `gate_A` + `gate_B300` | chỉ chạy vì A và B300 cùng đạt; chạy đúng một lần |

## Kết quả
(tính tự động từ `gate_variants.csv`)

### Trung bình 6 scene

| Biến thể | Điểm qua cổng | Đạt điều kiện θ | Chính xác của điểm qua (≤ 5 cm) | Số scene sai số điểm bị kéo giảm | Tỉ lệ điểm được cải thiện | F-score | Chamfer (cm) |
|---|---|---|---|---|---|---|---|
| gate_base | 1.69% | 21.5% | 0.887 | 5/6 | 0.637 | 0.4939 | 16.65 |
| gate_A | 1.33% | 22.5% | 0.892 | 5/6 | 0.680 | 0.4938 | 16.65 |
| gate_Ab | 1.35% | 22.5% | 0.886 | 5/6 | 0.684 | 0.4937 | 16.65 |
| gate_B100 | 2.15% | 29.3% | 0.877 | 5/6 | 0.626 | 0.4938 | 16.65 |
| gate_B300 | 2.45% | 34.4% | 0.871 | 5/6 | 0.627 | 0.4938 | 16.65 |
| gate_AB | 1.90% | 35.9% | 0.874 | 5/6 | 0.671 | 0.4937 | 16.65 |

### Từng scene (sàn / tường / trần / ngang khác = số mặt phẳng theo nhãn; "far" = số mặt nhãn sàn cách mặt thấp nhất quá band)

| Scene | Biến thể | sàn/tường/trần/ngang khác | far | Qua cổng | Đạt θ | Chính xác điểm qua | Sai số điểm bị kéo trước → sau (cm) | Tỉ lệ cải thiện | F | Chamfer |
|---|---|---|---|---|---|---|---|---|---|---|
| 42897599 | gate_base | 4/3/0/0 | 3 | 1.19% | 24.7% | 0.749 | 2.99 → 2.57 | 0.73 | 0.271 | 27.25 |
| 42897599 | gate_A | 1/3/0/3 | 0 | 1.15% | 24.4% | 0.743 | 3.02 → 2.59 | 0.73 | 0.271 | 27.25 |
| 42897599 | gate_Ab | 1/3/0/3 | 0 | 1.15% | 24.4% | 0.743 | 3.02 → 2.59 | 0.73 | 0.271 | 27.25 |
| 42897599 | gate_B100 | 4/3/0/0 | 3 | 1.47% | 30.1% | 0.708 | 3.44 → 3.03 | 0.68 | 0.271 | 27.25 |
| 42897599 | gate_B300 | 4/3/0/0 | 3 | 1.78% | 36.2% | 0.704 | 3.57 → 3.35 | 0.68 | 0.271 | 27.25 |
| 42897599 | gate_AB | 1/3/0/3 | 0 | 1.72% | 35.5% | 0.701 | 3.57 → 3.40 | 0.68 | 0.271 | 27.25 |
| 42898849 | gate_base | 8/0/0/0 | 7 | 0.17% | 17.5% | 0.897 | 1.65 → 1.01 | 0.63 | 0.436 | 14.79 |
| 42898849 | gate_A | 1/1/0/7 | 0 | 0.13% | 19.0% | 0.953 | 1.73 → 0.97 | 0.67 | 0.436 | 14.79 |
| 42898849 | gate_Ab | 1/1/0/7 | 0 | 0.13% | 19.0% | 0.953 | 1.73 → 0.97 | 0.67 | 0.436 | 14.79 |
| 42898849 | gate_B100 | 8/0/0/0 | 7 | 0.18% | 22.0% | 0.893 | 1.74 → 1.05 | 0.65 | 0.436 | 14.79 |
| 42898849 | gate_B300 | 8/0/0/0 | 7 | 0.18% | 22.9% | 0.893 | 1.76 → 1.05 | 0.67 | 0.436 | 14.79 |
| 42898849 | gate_AB | 1/1/0/7 | 0 | 0.16% | 25.9% | 0.938 | 1.69 → 1.01 | 0.67 | 0.436 | 14.79 |
| 42897566 | gate_base | 5/2/0/0 | 4 | 5.41% | 22.7% | 0.991 | 1.28 → 1.19 | 0.70 | 0.523 | 16.76 |
| 42897566 | gate_A | 1/1/0/5 | 0 | 4.34% | 23.9% | 0.994 | 1.30 → 1.13 | 0.77 | 0.523 | 16.76 |
| 42897566 | gate_Ab | 1/2/0/4 | 0 | 4.43% | 23.8% | 0.993 | 1.29 → 1.14 | 0.75 | 0.523 | 16.76 |
| 42897566 | gate_B100 | 5/2/0/0 | 4 | 7.37% | 32.4% | 0.990 | 1.27 → 1.17 | 0.68 | 0.523 | 16.76 |
| 42897566 | gate_B300 | 5/2/0/0 | 4 | 8.60% | 39.7% | 0.987 | 1.28 → 1.20 | 0.67 | 0.523 | 16.77 |
| 42897566 | gate_AB | 1/2/0/4 | 0 | 6.70% | 41.3% | 0.991 | 1.25 → 1.11 | 0.73 | 0.523 | 16.77 |
| 45662981 | gate_base | 5/3/0/0 | 4 | 1.76% | 27.4% | 0.983 | 1.40 → 1.25 | 0.73 | 0.612 | 14.43 |
| 45662981 | gate_A | 1/3/0/4 | 0 | 1.36% | 27.7% | 0.998 | 1.12 → 1.05 | 0.76 | 0.612 | 14.43 |
| 45662981 | gate_Ab | 1/3/0/4 | 0 | 1.36% | 27.7% | 0.998 | 1.12 → 1.05 | 0.76 | 0.612 | 14.43 |
| 45662981 | gate_B100 | 5/3/0/0 | 4 | 1.85% | 37.8% | 0.985 | 1.41 → 1.25 | 0.72 | 0.612 | 14.43 |
| 45662981 | gate_B300 | 5/3/0/0 | 4 | 1.89% | 44.3% | 0.989 | 1.44 → 1.26 | 0.73 | 0.612 | 14.43 |
| 45662981 | gate_AB | 1/3/0/4 | 0 | 1.48% | 45.8% | 0.996 | 1.16 → 1.07 | 0.75 | 0.612 | 14.43 |
| 42445022 | gate_base | 5/2/0/0 | 4 | 0.91% | 18.0% | 0.967 | 1.12 → 0.77 | 0.74 | 0.614 | 16.48 |
| 42445022 | gate_A | 1/2/0/4 | 0 | 0.52% | 21.5% | 0.942 | 1.04 → 0.67 | 0.94 | 0.614 | 16.49 |
| 42445022 | gate_Ab | 1/2/0/4 | 0 | 0.52% | 21.5% | 0.942 | 1.04 → 0.67 | 0.94 | 0.614 | 16.49 |
| 42445022 | gate_B100 | 5/2/0/0 | 4 | 1.17% | 25.2% | 0.958 | 1.16 → 0.83 | 0.69 | 0.614 | 16.49 |
| 42445022 | gate_B300 | 5/2/0/0 | 4 | 1.36% | 29.2% | 0.955 | 1.16 → 0.87 | 0.67 | 0.614 | 16.49 |
| 42445022 | gate_AB | 1/2/0/4 | 0 | 0.70% | 34.1% | 0.914 | 1.06 → 0.70 | 0.93 | 0.614 | 16.49 |
| 42444738 | gate_base | 5/3/0/0 | 4 | 0.66% | 18.4% | 0.736 | 1.71 → 2.02 | 0.29 | 0.507 | 10.18 |
| 42444738 | gate_A | 1/3/0/4 | 0 | 0.49% | 18.6% | 0.721 | 1.43 → 1.73 | 0.22 | 0.507 | 10.18 |
| 42444738 | gate_Ab | 2/3/0/3 | 0 | 0.54% | 18.5% | 0.686 | 1.61 → 1.79 | 0.25 | 0.507 | 10.18 |
| 42444738 | gate_B100 | 5/3/0/0 | 4 | 0.85% | 28.4% | 0.727 | 2.11 → 2.34 | 0.32 | 0.507 | 10.18 |
| 42444738 | gate_B300 | 5/3/0/0 | 4 | 0.88% | 33.9% | 0.697 | 2.24 → 2.52 | 0.35 | 0.507 | 10.18 |
| 42444738 | gate_AB | 1/3/0/4 | 0 | 0.64% | 32.9% | 0.705 | 2.07 → 2.23 | 0.27 | 0.507 | 10.18 |

### Áp quy tắc đặt trước (so với gate_base)

| Biến thể | A1 tường và sàn đúng | A2 Δchính xác điểm qua (≥ −0,02) | A3 scene cải thiện / Δtỉ lệ cải thiện (≥ −0,02) | A4 ΔF (≥ −0,005), ΔChamfer (≤ +2%), ΔF xấu nhất (≥ −0,010) | B1 θ gấp (≥ 1,5) | Kết luận |
|---|---|---|---|---|---|---|
| gate_A | có | +0.005 | 5 so với 5 / +0.043 | -0.0001, +0.0%, -0.000 | ×1.05 | nhãn: NHẬN |
| gate_Ab | có | -0.001 | 5 so với 5 / +0.046 | -0.0002, +0.0%, -0.000 | ×1.05 | nhãn: NHẬN (không chọn: gate_A cũng đạt) |
| gate_B100 | KHÔNG | -0.010 | 5 so với 5 / -0.012 | -0.0001, +0.0%, -0.000 | ×1.37 | pháp tuyến: không (θ chỉ ×1.37) |
| gate_B300 | KHÔNG | -0.016 | 5 so với 5 / -0.010 | -0.0001, +0.0%, -0.000 | ×1.60 | pháp tuyến: NHẬN |
| gate_AB | có | -0.013 | 5 so với 5 / +0.034 | -0.0002, +0.0%, -0.001 | ×1.67 | tổ hợp: NHẬN |

(A1 chỉ áp cho biến thể nhãn: các biến thể B giữ nhãn cũ nên A1 "KHÔNG" là bình thường; B1 chỉ áp cho biến thể pháp tuyến.)

## Kết luận theo quy tắc đặt trước
- **Nhãn: `gate_A` NHẬN** (A1–A4 đều đạt; `gate_Ab` cũng đạt nhưng theo quy tắc chọn `gate_A` vì đơn giản hơn). Cả 6 scene có đúng một "sàn" và ≥ 1 tường (42898849: từ 8 sàn/0 tường thành 1 sàn/1 tường nhờ lượt tìm tường thêm).
- **Pháp tuyến: `gate_B300` NHẬN, `gate_B100` KHÔNG** (k = 100 chỉ tăng tỉ lệ đạt θ ×1,37, dưới ngưỡng ×1,5; k = 300 tăng ×1,60). Cái giá của k = 300: độ chính xác điểm qua giảm 0,016 (trong giới hạn 0,02).
- **Tổ hợp `gate_AB` NHẬN**: nhãn đúng ở 6/6 scene, đạt θ 35,9% (so với 21,5%), điểm qua cổng 1,90% (so với 1,69%), chính xác điểm qua 0,874 (so với 0,887), tỉ lệ cải thiện 0,671 (so với 0,637), số scene sai số giảm 5/6 như cũ.

## Phải nói thẳng những điều sau
1. **F-score và Chamfer gần như không đổi ở mọi biến thể** (F 0,4937–0,4939; Chamfer 16,65 cm): cổng chỉ dịch tối đa 2,5 cm còn F tính ở δ = 5 cm. Quy tắc nhận chỉ chứng minh "không làm hại", KHÔNG chứng minh cải thiện chất lượng mô hình. Lợi ích thật của cổng chỉ đo được bằng P2Plane và plane recall trên Replica (M5).
2. **Cải thiện về nhãn là có thật và kiểm tra được** (1 sàn, ≥ 1 tường mỗi scene). Các mặt "ngang khác" (3–7 mặt mỗi scene) không còn được kéo; theo mục H đó là mặt RANSAC dày 5 cm cắt qua điểm lẫn lộn, không phải bàn ghế.
3. **Dev vẫn xấu đi** (gate_AB: sai số điểm bị kéo 2,07 → 2,23 cm; chỉ 27% điểm được cải thiện), đúng như mục H giải thích (sàn chính vốn sát Faro bị kéo về mặt RANSAC lệch ~0,7 cm). Không sửa nguyên nhân này trong đợt này; các biến thể không cứu được dev.
4. **Số điểm qua cổng vẫn rất ít** (1,3–2,5%) vì τ_w = 0,5 chưa đổi (theo yêu cầu E). Đây là việc của đợt sau (chọn lại ngưỡng, leave-one-scene-out).
5. Lượt tìm tường thêm chỉ tìm được 1 tường ở 42898849 và 1–2 tường ở 42897566; chưa kiểm xem đó có phải tường thật hay chỉ là mặt đứng bất kỳ (chưa xem ảnh từng mặt).
6. Kết quả là phát triển trên 5 Validation + dev; 5 Validation đã được nhìn nhiều lần, không phải bằng chứng cuối.

## Khác với yêu cầu ban đầu (đã ghi trước trong PLAN.md §1)
- **Thêm `plane.floor_band_m`** (thử cả band 0 đúng nguyên văn và band 0,10): vì mục H cho thấy sàn dev bị tách đôi. Kết quả: không cần band, `gate_A` (band 0) đạt nên chọn band 0.
- **Khoá riêng `plane.gate_normal_knn`** thay vì đổi `plane.normal_knn`: `normal_knn` còn dùng cho Poisson ở `export`, đổi nó sẽ âm thầm đổi mesh.
- **Rút lại suy đoán "mặt cao là bàn/ghế"** của tôi ở báo cáo trước; dùng kết luận của mục H.

## Trạng thái mặc định (đã áp dụng 15/11 theo yêu cầu của người dùng)
`configs/default.yaml` nay là: `plane.floor_rule: lowest`, `floor_band_m: 0.0`, `min_walls: 1`, `gate_normal_knn: 300` (và `extra_wall_passes: 4`); τ_r, τ_n, τ_w, α không đổi. Cấu hình cũ chọn lại được bằng `floor_rule: any`, `min_walls: 0`, `gate_normal_knn: null`.
Đã chạy lại `gate` → `export`, `fuse → gate` cho `abl_quality` và `eval` cho 6 scene (không 47204552): kết quả `proposed` TRÙNG từng chữ số với `gate_AB` (F 0,4937 trung bình, Chamfer 16,65 cm); B0, B1, B3 không đổi.
Bản cũ giữ ở `proposed/variants/pre_gate_fix/{plane_refinement, export, abl_quality_plane_refinement}` và `evaluation/variants/pre_gate_fix/{metrics.csv, logs/}` của từng scene. Bảng trước/sau: `applied_before_after.csv`.
**Hệ quả cần biết:** `export` chạy lại nên hệ model (sàn y = 0) có thể đổi theo mặt sàn mới, do đó các đầu mút chấm tay của scene dev (`endpoints_*.json`, chấm trên model cũ) lại không còn khớp; hình học (acc, comp, F, Chamfer) không bị ảnh hưởng.
