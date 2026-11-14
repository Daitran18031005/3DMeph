# Sai số đo chiều dài (mục tiêu: median < 5 cm sau MỘT lần neo scale) — đo bán tự động, chỉ đọc

Mã: `scripts/length_error.py` (không đổi tham số nào, không đổi kết quả cũ, không dùng GT để suy scale, không đụng held-out). Số liệu thô: `kabsch/` và `icp/` (`per_segment.csv`, `per_scene.csv`, `endpoints_missing.csv`, `sensitivity.csv`, thư mục `maps/`).
Phạm vi: 5 Validation (không 47204552) và dev 42444738; biến thể B0 (COLMAP), B1 (VGGT thuần), B3 (fusion không cổng), proposed (fusion + cổng, bản mặc định mới 15/11). Một mốc scale cho mọi biến thể: B0, B3, proposed dùng `s_m` từ mốc đã click; B1 dùng scale cùng mốc đó nhưng tính trên chuỗi VGGT (`pipeline/eval/b1.py`).

## 0. Kiểm trước: `eval` đã đo sai số chiều dài chưa?
**Rồi, nhưng rất ít đoạn hợp lệ.** `eval` có chế độ `auto` (đang chạy trong `metrics.csv`, cột `length_mode`): đầu mút Faro của các đoạn test (`measurements.csv`, bỏ `used_as_anchor = 1`) được đưa sang hệ từng biến thể bằng Kabsch cắt tỉa trên tâm camera
(scale = 1), snap vào điểm gần nhất trong **2 cm** (`eval.snap_radius_m`), rồi đo khoảng cách. Bán kính 2 cm chặt nên chỉ vài đoạn hợp lệ ở mỗi scene (ví dụ 42897599: 2/5). Chế độ `manual` (chấm tay) chỉ có cho scene dev và đã lỗi thời sau khi dựng lại mô hình d3.
Vì vậy tôi viết `scripts/length_error.py` làm phép đo **bán tự động với bán kính 5 cm** theo yêu cầu: dùng lại đúng hàm `ln.measure_auto` và phép căn `eval`. Đây là **bản thay thế xấp xỉ, KHÔNG thay thế chấm tay**: điểm snap có thể lệch vài cm so với đầu mút người chấm sẽ chọn, nên số này chỉ là xấp xỉ.
Thêm một chế độ phụ `icp` (Kabsch rồi ICP cứng, scale = 1, cùng thủ tục ICP của chỉ số hình học) để tách "đầu mút không có điểm" khỏi "phép căn lệch vài cm": ICP chỉ dịch và xoay, không đổi scale, nên không đụng tới sai số scale.

**Cách đọc:** "hợp lệ" = cả hai đầu mút Faro có điểm của biến thể trong 5 cm. median/MAE/MAPE/% dưới 5 cm tính trên các đoạn hợp lệ (sai số = |độ dài đo − độ dài Faro|). Số đoạn test: 42897599 = 5, 42898849 = 6, 42897566 = 6, 45662981 = 5, 42445022 = 12, 42444738 (dev) = 12 (tổng 46).


## 1. Kết quả đo — phép căn: Kabsch (đúng phép căn của `eval`)

| Scene | Biến thể | Số đoạn test | Hợp lệ (cả 2 đầu mút ≤ 5 cm) | median (cm) | MAE (cm) | MAPE (%) | % dưới 5 cm | Đầu mút có điểm ≤ 5 cm | Khoảng cách điểm gần nhất, trung vị (cm) |
|---|---|---|---|---|---|---|---|---|---|
| 42897599 | B0 | 5 | 4/5 (80%) | 1.10 | 1.05 | 1.69 | 100 | 90% | 1.98 |
| 42897599 | B1 | – | không có đám điểm (B1 không nối được chunk) | – | – | – | – | – | – |
| 42897599 | B3 | 5 | 4/5 (80%) | 1.08 | 1.16 | 1.61 | 100 | 90% | 2.02 |
| 42897599 | proposed | 5 | 4/5 (80%) | 1.08 | 1.16 | 1.61 | 100 | 90% | 2.02 |
| 42898849 | B0 | 6 | 2/6 (33%) | 2.13 | 2.13 | 1.92 | 100 | 67% | 2.37 |
| 42898849 | B1 | – | không có đám điểm (B1 không nối được chunk) | – | – | – | – | – | – |
| 42898849 | B3 | 6 | 3/6 (50%) | 1.66 | 2.34 | 2.47 | 67 | 75% | 2.91 |
| 42898849 | proposed | 6 | 3/6 (50%) | 1.66 | 2.34 | 2.47 | 67 | 75% | 2.91 |
| 42897566 | B0 | 6 | 2/6 (33%) | 2.02 | 2.02 | 2.42 | 100 | 67% | 2.34 |
| 42897566 | B1 | 6 | 2/6 (33%) | 1.61 | 1.61 | 3.67 | 100 | 42% | 5.81 |
| 42897566 | B3 | 6 | 3/6 (50%) | 1.02 | 0.92 | 1.87 | 100 | 75% | 1.76 |
| 42897566 | proposed | 6 | 3/6 (50%) | 1.14 | 0.96 | 1.99 | 100 | 75% | 1.76 |
| 45662981 | B0 | 5 | 3/5 (60%) | 1.20 | 1.90 | 2.34 | 100 | 80% | 2.75 |
| 45662981 | B1 | 5 | 0/5 (0%) | – | – | – | – | 10% | 10.18 |
| 45662981 | B3 | 5 | 1/5 (20%) | 0.26 | 0.26 | 0.45 | 100 | 60% | 2.89 |
| 45662981 | proposed | 5 | 1/5 (20%) | 0.26 | 0.26 | 0.45 | 100 | 60% | 2.89 |
| 42445022 | B0 | 12 | 10/12 (83%) | 1.18 | 1.16 | 2.12 | 100 | 92% | 1.84 |
| 42445022 | B1 | 12 | 2/12 (17%) | 0.46 | 0.46 | 0.87 | 100 | 33% | 9.78 |
| 42445022 | B3 | 12 | 7/12 (58%) | 1.18 | 1.04 | 2.17 | 100 | 79% | 2.37 |
| 42445022 | proposed | 12 | 7/12 (58%) | 1.18 | 1.04 | 2.17 | 100 | 79% | 2.37 |
| 42444738 | B0 | 12 | 4/12 (33%) | 0.30 | 0.46 | 0.35 | 100 | 42% | 8.23 |
| 42444738 | B1 | 12 | 0/12 (0%) | – | – | – | – | 12% | 11.88 |
| 42444738 | B3 | 12 | 4/12 (33%) | 1.35 | 1.43 | 1.51 | 100 | 38% | 7.51 |
| 42444738 | proposed | 12 | 4/12 (33%) | 1.35 | 1.43 | 1.51 | 100 | 38% | 7.51 |
| **Gộp 6 scene** | **B0** | 46 | **25/46 (54%)** | **1.13** | 1.27 | 1.80 | 100 | 71% | 2.45 |
| **Gộp 6 scene** | **B1** | 35 | **4/35 (11%)** | **1.09** | 1.03 | 2.27 | 100 | 24% | 9.78 |
| **Gộp 6 scene** | **B3** | 46 | **22/46 (48%)** | **1.17** | 1.26 | 1.87 | 95 | 66% | 2.65 |
| **Gộp 6 scene** | **proposed** | 46 | **22/46 (48%)** | **1.17** | 1.27 | 1.89 | 95 | 66% | 2.65 |

Sai số có dấu tương đối (trung vị, đo − Faro chia Faro) gộp: B0 +0.19%, B3 -0.44%, proposed -0.44%.

### Đầu mút KHÔNG có điểm proposed trong 5 cm (33/104 đầu mút, trong đó 31 thuộc đoạn test)
| Scene | Số đầu mút thiếu | Nguyên nhân khả dĩ (số đo ở `endpoints_missing.csv`; heuristic, chưa kiểm chứng) |
|---|---|---|
| 42897599 | 1 | 1× có hoạ tiết và depth nhưng không có điểm hợp nhất: đầu mút ở mép/vật mảnh, hoặc điểm MVS bị lọc ở bước stereo_fusion |
| 42898849 | 3 | 3× depth bị lọc nhất quán hình học (có depth photometric nhưng không nhất quán giữa các ảnh) |
| 42897566 | 3 | 1× depth bị lọc nhất quán hình học (có depth photometric nhưng không nhất quán giữa các ảnh); 1× ít view nhìn thấy (3); 1× có hoạ tiết và depth nhưng không có điểm hợp nhất: đầu mút ở mép/vật mảnh, hoặc điểm MVS bị lọc ở bước stereo_fusion |
| 45662981 | 5 | 4× có hoạ tiết và depth nhưng không có điểm hợp nhất: đầu mút ở mép/vật mảnh, hoặc điểm MVS bị lọc ở bước stereo_fusion; 1× depth bị lọc nhất quán hình học (có depth photometric nhưng không nhất quán giữa các ảnh) |
| 42445022 | 5 | 2× có hoạ tiết và depth nhưng không có điểm hợp nhất: đầu mút ở mép/vật mảnh, hoặc điểm MVS bị lọc ở bước stereo_fusion; 2× depth bị lọc nhất quán hình học (có depth photometric nhưng không nhất quán giữa các ảnh); 1× bề mặt trơn, ít hoạ tiết (gradient thấp) |
| 42444738 | 16 | 7× depth bị lọc nhất quán hình học (có depth photometric nhưng không nhất quán giữa các ảnh); 6× có hoạ tiết và depth nhưng không có điểm hợp nhất: đầu mút ở mép/vật mảnh, hoặc điểm MVS bị lọc ở bước stereo_fusion; 2× không có ảnh nhìn rõ (ít view / ở rìa ảnh); 1× ít view nhìn thấy (3) |

Tổng cả 6 scene: 14× có hoạ tiết và depth nhưng không có điểm hợp nhất: đầu mút ở mép/vật mảnh, hoặc điểm MVS bị lọc ở bước stereo_fusion; 14× depth bị lọc nhất quán hình học (có depth photometric nhưng không nhất quán giữa các ảnh); 2× ít view nhìn thấy (3); 2× không có ảnh nhìn rõ (ít view / ở rìa ảnh); 1× bề mặt trơn, ít hoạ tiết (gradient thấp). Số ảnh keyframe thấy đầu mút (hình học, chưa xét che khuất): trung vị 7.0, nhỏ nhất 1. Điểm MVS gần nhất cách trung vị 8.4 cm và có trung vị 2 view trong `fused.ply.vis`. Bản đồ nhìn từ trên: `kabsch/maps/<scene>_topdown.png`; ảnh chiếu lên keyframe tốt nhất: `kabsch/maps/<scene>_<đoạn><a|b>.png`.

### Độ nhạy theo mốc scale (bước 2; quy tắc đặt trước trong docstring của script; median cm, đã trừ đoạn mốc thay thế, gồm cả đoạn mốc gốc làm đoạn test)
| Scene | Biến thể | Mốc gốc | Mốc thay thế (hệ số f = L_Faro / L_B0 của đoạn đó) |
|---|---|---|---|
| 42897599 | B0 | 1.10 | mốc S03: 1.06 (f = 1.009, n = 4); mốc S04: 1.17 (f = 1.001, n = 4) |
| 42897599 | B3 | 1.08 | mốc S03: 0.75 (f = 1.009, n = 4); mốc S04: 0.81 (f = 1.001, n = 4) |
| 42897599 | proposed | 1.08 | mốc S03: 0.75 (f = 1.009, n = 4); mốc S04: 0.81 (f = 1.001, n = 4) |
| 42898849 | B0 | 2.13 | mốc S04: 2.70 (f = 1.026, n = 2); mốc S06: 4.00 (f = 0.987, n = 2) |
| 42898849 | B3 | 1.66 | mốc S04: 2.57 (f = 1.026, n = 4); mốc S06: 3.19 (f = 0.987, n = 3) |
| 42898849 | proposed | 1.66 | mốc S04: 2.57 (f = 1.026, n = 4); mốc S06: 3.19 (f = 0.987, n = 3) |
| 42897566 | B0 | 2.02 | mốc S02: 5.01 (f = 1.029, n = 2) |
| 42897566 | B3 | 1.02 | mốc S02: 2.09 (f = 1.029, n = 3) |
| 42897566 | proposed | 1.14 | mốc S02: 2.22 (f = 1.029, n = 3) |
| 45662981 | B0 | 1.20 | mốc S03: 2.34 (f = 1.003, n = 3); mốc S04: 6.07 (f = 1.050, n = 3) |
| 45662981 | B3 | 0.26 | mốc S03: 0.10 (f = 1.003, n = 1); mốc S04: 2.68 (f = 1.050, n = 1) |
| 45662981 | proposed | 0.26 | mốc S03: 0.10 (f = 1.003, n = 1); mốc S04: 2.68 (f = 1.050, n = 1) |
| 42445022 | B0 | 1.18 | mốc S03: 2.22 (f = 1.010, n = 10); mốc S04: 0.75 (f = 0.990, n = 10); mốc S05: 0.73 (f = 0.989, n = 10) |
| 42445022 | B3 | 1.18 | mốc S03: 1.23 (f = 1.010, n = 7); mốc S04: 1.42 (f = 0.990, n = 7); mốc S05: 1.52 (f = 0.989, n = 8) |
| 42445022 | proposed | 1.18 | mốc S03: 1.23 (f = 1.010, n = 7); mốc S04: 1.42 (f = 0.990, n = 7); mốc S05: 1.52 (f = 0.989, n = 8) |
| 42444738 | B0 | 0.30 | mốc S01: 0.48 (f = 0.995, n = 3); mốc S02: 0.49 (f = 1.001, n = 3); mốc S04: 0.51 (f = 1.002, n = 3) |
| 42444738 | B3 | 1.35 | mốc S01: 1.18 (f = 0.995, n = 3); mốc S02: 2.02 (f = 1.001, n = 3); mốc S04: 0.60 (f = 1.002, n = 3) |
| 42444738 | proposed | 1.35 | mốc S01: 1.18 (f = 0.995, n = 3); mốc S02: 2.02 (f = 1.001, n = 3); mốc S04: 0.60 (f = 1.002, n = 3) |

Thay đổi median lớn nhất so với mốc gốc: +4.87 cm (45662981, B0, mốc S04); số trường hợp median mốc thay thế > 5 cm: 2/39.

## 1. Kết quả đo — phép căn: Kabsch + ICP cứng (scale = 1)

| Scene | Biến thể | Số đoạn test | Hợp lệ (cả 2 đầu mút ≤ 5 cm) | median (cm) | MAE (cm) | MAPE (%) | % dưới 5 cm | Đầu mút có điểm ≤ 5 cm | Khoảng cách điểm gần nhất, trung vị (cm) |
|---|---|---|---|---|---|---|---|---|---|
| 42897599 | B0 | 5 | 4/5 (80%) | 0.65 | 0.69 | 1.08 | 100 | 80% | 1.15 |
| 42897599 | B1 | – | không có đám điểm (B1 không nối được chunk) | – | – | – | – | – | – |
| 42897599 | B3 | 5 | 3/5 (60%) | 1.31 | 1.38 | 1.83 | 100 | 80% | 2.39 |
| 42897599 | proposed | 5 | 3/5 (60%) | 1.31 | 1.38 | 1.83 | 100 | 80% | 2.39 |
| 42898849 | B0 | 6 | 4/6 (67%) | 0.55 | 0.51 | 0.60 | 100 | 83% | 1.06 |
| 42898849 | B1 | – | không có đám điểm (B1 không nối được chunk) | – | – | – | – | – | – |
| 42898849 | B3 | 6 | 2/6 (33%) | 1.54 | 1.54 | 2.59 | 100 | 58% | 4.23 |
| 42898849 | proposed | 6 | 2/6 (33%) | 1.54 | 1.54 | 2.59 | 100 | 58% | 4.23 |
| 42897566 | B0 | 6 | 5/6 (83%) | 0.70 | 1.41 | 3.66 | 100 | 92% | 0.79 |
| 42897566 | B1 | 6 | 3/6 (50%) | 0.57 | 0.71 | 1.33 | 100 | 75% | 1.64 |
| 42897566 | B3 | 6 | 4/6 (67%) | 0.65 | 1.12 | 2.59 | 100 | 83% | 2.68 |
| 42897566 | proposed | 6 | 4/6 (67%) | 0.65 | 1.12 | 2.59 | 100 | 83% | 2.68 |
| 45662981 | B0 | 5 | 4/5 (80%) | 2.11 | 2.18 | 2.88 | 100 | 90% | 4.01 |
| 45662981 | B1 | 5 | 0/5 (0%) | – | – | – | – | 30% | 9.22 |
| 45662981 | B3 | 5 | 2/5 (40%) | 3.86 | 3.86 | 4.63 | 100 | 70% | 3.37 |
| 45662981 | proposed | 5 | 2/5 (40%) | 3.86 | 3.86 | 4.63 | 100 | 70% | 3.33 |
| 42445022 | B0 | 12 | 10/12 (83%) | 0.94 | 1.18 | 2.12 | 100 | 92% | 1.41 |
| 42445022 | B1 | 12 | 5/12 (42%) | 2.04 | 1.79 | 4.71 | 100 | 58% | 4.26 |
| 42445022 | B3 | 12 | 10/12 (83%) | 0.91 | 0.91 | 1.68 | 100 | 92% | 0.80 |
| 42445022 | proposed | 12 | 10/12 (83%) | 0.83 | 0.84 | 1.57 | 100 | 92% | 0.81 |
| 42444738 | B0 | 12 | 5/12 (42%) | 0.90 | 1.35 | 1.02 | 100 | 54% | 4.30 |
| 42444738 | B1 | 12 | 2/12 (17%) | 1.03 | 1.03 | 0.58 | 100 | 38% | 8.06 |
| 42444738 | B3 | 12 | 5/12 (42%) | 0.99 | 1.52 | 1.22 | 100 | 46% | 7.79 |
| 42444738 | proposed | 12 | 5/12 (42%) | 0.79 | 1.48 | 1.17 | 100 | 46% | 7.80 |
| **Gộp 6 scene** | **B0** | 46 | **32/46 (70%)** | **0.70** | 1.22 | 1.96 | 100 | 79% | 1.51 |
| **Gộp 6 scene** | **B1** | 35 | **10/35 (29%)** | **1.13** | 1.31 | 2.87 | 100 | 50% | 5.07 |
| **Gộp 6 scene** | **B3** | 46 | **26/46 (57%)** | **1.10** | 1.39 | 2.05 | 100 | 71% | 2.49 |
| **Gộp 6 scene** | **proposed** | 46 | **26/46 (57%)** | **1.04** | 1.35 | 1.99 | 100 | 71% | 2.50 |

Sai số có dấu tương đối (trung vị, đo − Faro chia Faro) gộp: B0 -0.13%, B3 -0.72%, proposed -0.72%.

### Đầu mút KHÔNG có điểm proposed trong 5 cm (30/104 đầu mút, trong đó 27 thuộc đoạn test)
| Scene | Số đầu mút thiếu | Nguyên nhân khả dĩ (số đo ở `endpoints_missing.csv`; heuristic, chưa kiểm chứng) |
|---|---|---|
| 42897599 | 2 | 1× depth bị lọc nhất quán hình học (có depth photometric nhưng không nhất quán giữa các ảnh); 1× có hoạ tiết và depth nhưng không có điểm hợp nhất: đầu mút ở mép/vật mảnh, hoặc điểm MVS bị lọc ở bước stereo_fusion |
| 42898849 | 5 | 3× có hoạ tiết và depth nhưng không có điểm hợp nhất: đầu mút ở mép/vật mảnh, hoặc điểm MVS bị lọc ở bước stereo_fusion; 2× depth bị lọc nhất quán hình học (có depth photometric nhưng không nhất quán giữa các ảnh) |
| 42897566 | 2 | 1× depth bị lọc nhất quán hình học (có depth photometric nhưng không nhất quán giữa các ảnh); 1× ít view nhìn thấy (3) |
| 45662981 | 5 | 4× có hoạ tiết và depth nhưng không có điểm hợp nhất: đầu mút ở mép/vật mảnh, hoặc điểm MVS bị lọc ở bước stereo_fusion; 1× depth bị lọc nhất quán hình học (có depth photometric nhưng không nhất quán giữa các ảnh) |
| 42445022 | 2 | 1× bề mặt trơn, ít hoạ tiết (gradient thấp); 1× depth bị lọc nhất quán hình học (có depth photometric nhưng không nhất quán giữa các ảnh) |
| 42444738 | 14 | 8× depth bị lọc nhất quán hình học (có depth photometric nhưng không nhất quán giữa các ảnh); 3× có hoạ tiết và depth nhưng không có điểm hợp nhất: đầu mút ở mép/vật mảnh, hoặc điểm MVS bị lọc ở bước stereo_fusion; 2× không có ảnh nhìn rõ (ít view / ở rìa ảnh); 1× ít view nhìn thấy (2) |

Tổng cả 6 scene: 14× depth bị lọc nhất quán hình học (có depth photometric nhưng không nhất quán giữa các ảnh); 11× có hoạ tiết và depth nhưng không có điểm hợp nhất: đầu mút ở mép/vật mảnh, hoặc điểm MVS bị lọc ở bước stereo_fusion; 2× không có ảnh nhìn rõ (ít view / ở rìa ảnh); 1× ít view nhìn thấy (3); 1× bề mặt trơn, ít hoạ tiết (gradient thấp); 1× ít view nhìn thấy (2). Số ảnh keyframe thấy đầu mút (hình học, chưa xét che khuất): trung vị 7.5, nhỏ nhất 0. Điểm MVS gần nhất cách trung vị 7.1 cm và có trung vị 2 view trong `fused.ply.vis`. Bản đồ nhìn từ trên: `icp/maps/<scene>_topdown.png`; ảnh chiếu lên keyframe tốt nhất: `icp/maps/<scene>_<đoạn><a|b>.png`.

### Độ nhạy theo mốc scale (bước 2; quy tắc đặt trước trong docstring của script; median cm, đã trừ đoạn mốc thay thế, gồm cả đoạn mốc gốc làm đoạn test)
| Scene | Biến thể | Mốc gốc | Mốc thay thế (hệ số f = L_Faro / L_B0 của đoạn đó) |
|---|---|---|---|
| 42897599 | B0 | 0.65 | mốc S03: 0.80 (f = 1.003, n = 4); mốc S04: 2.39 (f = 0.983, n = 4) |
| 42897599 | B3 | 1.31 | mốc S03: 0.84 (f = 1.003, n = 3); mốc S04: 3.34 (f = 0.983, n = 3) |
| 42897599 | proposed | 1.31 | mốc S03: 0.84 (f = 1.003, n = 3); mốc S04: 3.34 (f = 0.983, n = 3) |
| 42898849 | B0 | 0.55 | mốc S04: 0.78 (f = 0.993, n = 4); mốc S05: 0.98 (f = 1.006, n = 4); mốc S06: 0.77 (f = 1.001, n = 4) |
| 42898849 | B3 | 1.54 | mốc S04: 1.39 (f = 0.993, n = 3); mốc S05: 0.91 (f = 1.006, n = 3); mốc S06: 0.62 (f = 1.001, n = 2) |
| 42898849 | proposed | 1.54 | mốc S04: 1.39 (f = 0.993, n = 3); mốc S05: 0.91 (f = 1.006, n = 3); mốc S06: 0.62 (f = 1.001, n = 2) |
| 42897566 | B0 | 0.70 | mốc S02: 0.85 (f = 1.004, n = 5) |
| 42897566 | B3 | 0.65 | mốc S02: 1.26 (f = 1.004, n = 4) |
| 42897566 | proposed | 0.65 | mốc S02: 1.26 (f = 1.004, n = 4) |
| 45662981 | B0 | 2.11 | mốc S02: 3.76 (f = 1.003, n = 3); mốc S03: 3.64 (f = 1.001, n = 3); mốc S04: 10.37 (f = 0.952, n = 3) |
| 45662981 | B3 | 3.86 | mốc S02: 3.43 (f = 1.003, n = 2); mốc S03: 4.54 (f = 1.001, n = 1); mốc S04: 10.15 (f = 0.952, n = 2) |
| 45662981 | proposed | 3.86 | mốc S02: 3.43 (f = 1.003, n = 2); mốc S03: 4.54 (f = 1.001, n = 1); mốc S04: 10.15 (f = 0.952, n = 2) |
| 42445022 | B0 | 0.94 | mốc S03: 0.93 (f = 0.996, n = 10); mốc S04: 0.95 (f = 0.997, n = 10); mốc S05: 1.92 (f = 1.013, n = 10) |
| 42445022 | B3 | 0.91 | mốc S03: 0.66 (f = 0.996, n = 10); mốc S04: 0.62 (f = 0.997, n = 10); mốc S05: 1.36 (f = 1.013, n = 11) |
| 42445022 | proposed | 0.83 | mốc S03: 0.62 (f = 0.996, n = 10); mốc S04: 0.58 (f = 0.997, n = 10); mốc S05: 1.34 (f = 1.013, n = 11) |
| 42444738 | B0 | 0.90 | mốc S03: 1.28 (f = 1.009, n = 5); mốc S04: 1.04 (f = 1.012, n = 5); mốc S08: 0.93 (f = 1.018, n = 5) |
| 42444738 | B3 | 0.99 | mốc S03: 1.15 (f = 1.009, n = 5); mốc S04: 0.91 (f = 1.012, n = 4); mốc S08: 1.37 (f = 1.018, n = 4) |
| 42444738 | proposed | 0.79 | mốc S03: 1.15 (f = 1.009, n = 5); mốc S04: 0.91 (f = 1.012, n = 4); mốc S08: 1.37 (f = 1.018, n = 4) |

Thay đổi median lớn nhất so với mốc gốc: +8.26 cm (45662981, B0, mốc S04); số trường hợp median mốc thay thế > 5 cm: 3/45.

### Tỉ lệ s_m / s theo quỹ đạo (bước 2)
`s_m` là scale từ mốc (chiều dài Faro chia chiều dài mô hình); `s` là scale Umeyama bền giữa tâm camera COLMAP và quỹ đạo ARKit (chỉ để KIỂM TRA, không dùng để suy scale).
| Scene | 42897599 | 42898849 | 42897566 | 45662981 | 42445022 | 42444738 (dev) |
|---|---|---|---|---|---|---|
| s_m / s | 0.977 | 0.989 | 1.004 | 1.019 | 1.023 | 1.022 |
| Lệch (%) | -2.3 | -1.1 | +0.4 | +1.9 | +2.3 | +2.2 |
| Với đoạn 3 m: lệch tương ứng (cm) | 7.0 | 3.2 | 1.3 | 5.7 | 6.9 | 6.7 |

## 3. Median có vượt 5 cm không? Phân tích nguyên nhân (chỉ báo, chưa sửa)
**Trên các đoạn đo được, median KHÔNG vượt 5 cm** (nên bước 3 "nếu median > 5 cm" không được kích hoạt): B0 1,13 cm (Kabsch) và 0,70 cm (ICP), proposed 1,17 và 1,04 cm; không scene nào có median > 4 cm (lớn nhất: B3/proposed 3,86 cm ở 45662981 với ICP, chỉ 2 đoạn). Nhưng kết luận "đạt mục tiêu" phải đi kèm các giới hạn sau, theo đúng thứ tự scale, đầu mút, nhiễu cục bộ:

1. **Scale.** Sai số có dấu tương đối (đo − Faro, chia Faro) gộp chỉ −0,7% đến +0,2% (B0 +0,19%/−0,13%, proposed −0,44%/−0,72% với Kabsch/ICP), nghĩa là scale từ mốc khớp chiều dài Faro trong vài phần nghìn đến dưới 1%. Tỉ lệ s_m/s theo quỹ đạo ARKit lệch tới 2,3% (dev, 42445022: với đoạn 3 m là ~7 cm) nhưng **không thấy lệch đó trong số đo theo Faro**; hơn nữa các mốc Faro khác cho hệ số f chỉ ±1–3% (đoạn ≥ 1 m) và ngược chiều với s_m/s ở dev (f > 1 trong khi s_m/s > 1): gợi ý quỹ đạo ARKit không phải thước chuẩn và scale mốc đủ tốt, nhưng f được tính từ chiều dài snap nên có nhiễu; chưa kết luận chắc.
2. **Đầu mút.** Đây là chỗ yếu nhất: chỉ **54% (B0) và 48% (proposed) đoạn đo được với phép căn Kabsch, 70% và 57% với ICP**; B1 chỉ 11%/29%. Khoảng cách điểm gần nhất trung vị của đầu mút Faro tới đám điểm 1,5–2,7 cm (B0, proposed), 5–10 cm (B1, vì quỹ đạo VGGT lệch xa Faro). Đầu mút thiếu điểm (30–33/104, 27–31 thuộc đoạn test) tập trung ở (a) đầu mút CAO: ở ICP, 16/30 đầu mút thiếu cao ≥ 1,6 m so với đầu mút thấp nhất của scene (trần, đỉnh cửa; dev có 11/14 đầu mút thiếu ở cao ≥ 1,6 m: đoạn S03, S05, S07, S10, S11, S13, trong đó S07, S11, S13 sát trần mà mô hình không có trần); (b) đầu mút ở mép/vật mảnh hoặc depth bị lọc nhất quán hình học. Số view nhìn thấy đầu mút thiếu không phải nút thắt (trung vị 7 ảnh), nhưng điểm MVS gần nhất chỉ có trung vị 2 view trong `fused.ply.vis`: tức điểm bị `stereo_fusion` loại hoặc ít ủng hộ.
3. **Nhiễu cục bộ.** MAE 1,2–1,4 cm trên đoạn hợp lệ, MAPE ~2%: nhiễu cục bộ nhỏ so với 5 cm khi đã có điểm; sai số lớn hơn xuất hiện ở đoạn ngắn và khi dùng mốc ngắn (xem độ nhạy: mốc thay thế 0,83 m ở 45662981 làm median B0 tăng 4,9–8,3 cm).

## Điều phải nói thẳng
- **Độ phủ thấp, không phải sai số, là rủi ro chính:** một nửa số đoạn test không có điểm quanh đầu mút. Số đo trên đoạn hợp lệ lạc quan vì chọn lọc (đoạn có bề mặt dựng được). Nếu coi đoạn không đo được là "chưa đạt", tỉ lệ đoạn đo được và sai số < 5 cm chỉ 48% (proposed, Kabsch) và 57% (ICP) trên 46 đoạn.
- **Đây là xấp xỉ bán tự động** (snap vào điểm gần nhất trong 5 cm): sai số lệch đầu mút do người chấm thật có thể lớn hơn; chấm tay vẫn là phép đo chuẩn.
- **B3 và proposed gần như trùng nhau** (cổng chỉ dịch ≤ 2,5 cm); proposed kém B0 về độ phủ đầu mút (66–71% so với 71–79% đầu mút có điểm) vì đám điểm sau fusion không dày bằng MVS d3 (B0).
- Phép căn Kabsch của `eval` đưa vài đầu mút ra ngoài 5 cm chỉ vì lệch phép căn (dev: khoảng cách trung vị 7,5–8,2 cm với Kabsch, 4,3 và 7,8 cm với ICP); bản ICP tách phần này ra.
- Mốc thay thế chọn theo quy tắc đặt trước (đoạn hợp lệ ở B0, độ dài 1–2,5 m, ba đoạn đầu theo id; nới 0,7–3 m nếu thiếu) nên có scene chỉ 1–2 mốc thay thế, và một số mốc thay thế ngắn (< 1 m).
- Chưa kiểm: các đầu mút Faro đã được người dùng chọn đúng vị trí vật lý chưa (đây là GT); nguyên nhân đầu mút thiếu là suy đoán từ số đo, chưa xem ảnh từng đầu mút ngoài vài ảnh mẫu.

## Khác với kế hoạch
Thêm chế độ phụ ICP ngoài yêu cầu (chỉ để tách nguyên nhân); mọi kết quả cũ giữ nguyên; không commit, không push, không tải dữ liệu, không đụng held-out.


---

# Phần 2 (v2, 15/11): đo KHÔNG lạc quan do chọn lọc — đủ mẫu số

Quy tắc đặt trước: `PLAN_v2.md`. Mã: `scripts/length_error_v2.py`; số liệu thô: `v2/coverage.csv`, `v2/common_set.csv`, `v2/scale_icp.csv`, `v2/plane_pairs.csv`. Các số của phần 1 ở trên giữ nguyên.
Định nghĩa: **hợp lệ(r)** = cả hai đầu mút Faro có điểm của biến thể trong r cm (điểm snap là điểm gần nhất nên độ dài đo không đổi theo r, chỉ tập hợp lệ thu hẹp); **đạt** = hợp lệ và sai số < 5 cm; mẫu số = 46 đoạn test (B1: 35, vì không có đám điểm ở 42897599, 42898849).

## 1a–1b. Toàn bộ 46 đoạn: hợp lệ, đạt (đoạn không hợp lệ = chưa đạt), theo bán kính snap

**Phép căn: Kabsch (phép căn của `eval`; số chính)**

| Biến thể | r (cm) | Hợp lệ / N | **Đạt / N** (cả mẫu số) | median trên đoạn hợp lệ (cm) | MAE hợp lệ (cm) | MAPE hợp lệ (%) | median nếu đoạn không hợp lệ = lỗi vô hạn (cm) |
|---|---|---|---|---|---|---|---|
| B0 | 2 | 10/46 (22%) | **10/46 (22%)** | 1.09 | 0.91 | 1.45 | không xác định (hợp lệ < 50%) |
| B0 | 3 | 20/46 (43%) | **20/46 (43%)** | 1.09 | 1.02 | 1.61 | không xác định (hợp lệ < 50%) |
| B0 | 5 | 25/46 (54%) | **25/46 (54%)** | 1.13 | 1.27 | 1.80 | 3.05 |
| B1 | 2 | 1/35 (3%) | **1/35 (3%)** | 1.46 | 1.46 | 4.04 | không xác định (hợp lệ < 50%) |
| B1 | 3 | 2/35 (6%) | **2/35 (6%)** | 0.82 | 0.82 | 2.19 | không xác định (hợp lệ < 50%) |
| B1 | 5 | 4/35 (11%) | **4/35 (11%)** | 1.09 | 1.03 | 2.27 | không xác định (hợp lệ < 50%) |
| B3 | 2 | 10/46 (22%) | **10/46 (22%)** | 0.62 | 0.71 | 1.13 | không xác định (hợp lệ < 50%) |
| B3 | 3 | 19/46 (41%) | **19/46 (41%)** | 1.02 | 1.05 | 1.78 | không xác định (hợp lệ < 50%) |
| B3 | 5 | 22/46 (48%) | **21/46 (46%)** | 1.17 | 1.26 | 1.87 | không xác định (hợp lệ < 50%) |
| proposed | 2 | 10/46 (22%) | **10/46 (22%)** | 0.62 | 0.73 | 1.16 | không xác định (hợp lệ < 50%) |
| proposed | 3 | 19/46 (41%) | **19/46 (41%)** | 1.14 | 1.05 | 1.80 | không xác định (hợp lệ < 50%) |
| proposed | 5 | 22/46 (48%) | **21/46 (46%)** | 1.17 | 1.27 | 1.89 | không xác định (hợp lệ < 50%) |

**Phép căn: Kabsch + ICP cứng (phụ)**

| Biến thể | r (cm) | Hợp lệ / N | **Đạt / N** (cả mẫu số) | median trên đoạn hợp lệ (cm) | MAE hợp lệ (cm) | MAPE hợp lệ (%) | median nếu đoạn không hợp lệ = lỗi vô hạn (cm) |
|---|---|---|---|---|---|---|---|
| B0 | 2 | 23/46 (50%) | **23/46 (50%)** | 0.63 | 0.73 | 1.18 | không xác định (hợp lệ < 50%) |
| B0 | 3 | 26/46 (57%) | **26/46 (57%)** | 0.66 | 0.84 | 1.34 | 1.55 |
| B0 | 5 | 32/46 (70%) | **32/46 (70%)** | 0.70 | 1.22 | 1.96 | 1.29 |
| B1 | 2 | 3/35 (9%) | **3/35 (9%)** | 0.30 | 0.62 | 1.22 | không xác định (hợp lệ < 50%) |
| B1 | 3 | 3/35 (9%) | **3/35 (9%)** | 0.30 | 0.62 | 1.22 | không xác định (hợp lệ < 50%) |
| B1 | 5 | 10/35 (29%) | **10/35 (29%)** | 1.13 | 1.31 | 2.87 | không xác định (hợp lệ < 50%) |
| B3 | 2 | 13/46 (28%) | **13/46 (28%)** | 0.80 | 0.75 | 1.15 | không xác định (hợp lệ < 50%) |
| B3 | 3 | 19/46 (41%) | **19/46 (41%)** | 0.99 | 0.94 | 1.65 | không xác định (hợp lệ < 50%) |
| B3 | 5 | 26/46 (57%) | **26/46 (57%)** | 1.10 | 1.39 | 2.05 | 2.91 |
| proposed | 2 | 13/46 (28%) | **13/46 (28%)** | 0.79 | 0.74 | 1.13 | không xác định (hợp lệ < 50%) |
| proposed | 3 | 19/46 (41%) | **19/46 (41%)** | 0.80 | 0.89 | 1.58 | không xác định (hợp lệ < 50%) |
| proposed | 5 | 26/46 (57%) | **26/46 (57%)** | 1.04 | 1.35 | 1.99 | 2.91 |

Sai số trên đoạn hợp lệ gần như không đổi theo r (0,6–1,5 cm), còn số đoạn hợp lệ giảm mạnh khi r nhỏ: bán kính 2 cm (mặc định của `eval`) chỉ giữ 22% số đoạn (B0 và proposed, Kabsch); với ICP là 50% (B0) và 28% (proposed).

## 1c. Tách theo độ dài Faro và theo scene (r = 5 cm)

**Theo độ dài — Kabsch (phép căn của `eval`; số chính)** (hợp lệ / N · đạt · median cm · MAE cm)

| Biến thể | < 1 m | 1–2 m | > 2 m |
|---|---|---|---|
| B0 | 15/23 · 15 · 1.09 · 1.13 | 8/16 · 8 · 1.20 · 1.53 | 2/7 · 2 · 1.25 · 1.25 |
| B3 | 14/23 · 13 · 1.08 · 1.30 | 7/16 · 7 · 1.29 · 1.14 | 1/7 · 1 · 1.53 · 1.53 |
| proposed | 14/23 · 13 · 1.15 · 1.31 | 7/16 · 7 · 1.29 · 1.14 | 1/7 · 1 · 1.53 · 1.53 |

**Theo scene — Kabsch (phép căn của `eval`; số chính)** (hợp lệ / N · đạt · median cm)

| Scene | B0 | B3 | proposed |
|---|---|---|---|
| 42897599 | 4/5 · 4 · 1.10 | 4/5 · 4 · 1.08 | 4/5 · 4 · 1.08 |
| 42898849 | 2/6 · 2 · 2.13 | 3/6 · 2 · 1.66 | 3/6 · 2 · 1.66 |
| 42897566 | 2/6 · 2 · 2.02 | 3/6 · 3 · 1.02 | 3/6 · 3 · 1.14 |
| 45662981 | 3/5 · 3 · 1.20 | 1/5 · 1 · 0.26 | 1/5 · 1 · 0.26 |
| 42445022 | 10/12 · 10 · 1.18 | 7/12 · 7 · 1.18 | 7/12 · 7 · 1.18 |
| 42444738 | 4/12 · 4 · 0.30 | 4/12 · 4 · 1.35 | 4/12 · 4 · 1.35 |

**Theo độ dài — Kabsch + ICP cứng (phụ)** (hợp lệ / N · đạt · median cm · MAE cm)

| Biến thể | < 1 m | 1–2 m | > 2 m |
|---|---|---|---|
| B0 | 19/23 · 19 · 0.70 · 1.36 | 10/16 · 10 · 0.86 · 1.16 | 3/7 · 3 · 0.68 · 0.57 |
| B3 | 17/23 · 17 · 1.06 · 1.33 | 7/16 · 7 · 1.02 · 1.25 | 2/7 · 2 · 2.43 · 2.43 |
| proposed | 17/23 · 17 · 0.86 · 1.27 | 7/16 · 7 · 1.02 · 1.25 | 2/7 · 2 · 2.43 · 2.43 |

**Theo scene — Kabsch + ICP cứng (phụ)** (hợp lệ / N · đạt · median cm)

| Scene | B0 | B3 | proposed |
|---|---|---|---|
| 42897599 | 4/5 · 4 · 0.65 | 3/5 · 3 · 1.31 | 3/5 · 3 · 1.31 |
| 42898849 | 4/6 · 4 · 0.55 | 2/6 · 2 · 1.54 | 2/6 · 2 · 1.54 |
| 42897566 | 5/6 · 5 · 0.70 | 4/6 · 4 · 0.65 | 4/6 · 4 · 0.65 |
| 45662981 | 4/5 · 4 · 2.11 | 2/5 · 2 · 3.86 | 2/5 · 2 · 3.86 |
| 42445022 | 10/12 · 10 · 0.94 | 10/12 · 10 · 0.91 | 10/12 · 10 · 0.83 |
| 42444738 | 5/12 · 5 · 0.90 | 5/12 · 5 · 0.99 | 5/12 · 5 · 0.79 |

Bảng đầy đủ (scene × nhóm độ dài, mọi bán kính, B1) ở `v2/coverage.csv`.

## 1d. So B0, B3, proposed chỉ trên tập đoạn mà CẢ BA cùng hợp lệ
| Phép căn | r (cm) | Số đoạn chung / 46 (< 1 m, 1–2 m, > 2 m) | median B0 / B3 / proposed (cm) | MAE B0 / B3 / proposed (cm) | chênh cặp trung vị: proposed − B0 (cm), lớn nhất theo trị tuyệt đối | proposed − B3 |
|---|---|---|---|---|---|---|
| kabsch | 2 | 5 (4, 1, 0) | 1.09 / 0.26 / 0.26 | 1.02 / 0.56 / 0.56 | -0.94, 1.51 | 0.00 |
| kabsch | 3 | 16 (11, 5, 0) | 1.09 / 0.99 / 0.99 | 0.99 / 1.05 / 1.05 | 0.10, 2.41 | 0.00 |
| kabsch | 5 | 18 (11, 6, 1) | 1.10 / 1.17 / 1.17 | 1.05 / 1.09 / 1.09 | 0.06, 2.41 | 0.00 |
| icp | 2 | 10 (6, 4, 0) | 0.56 / 0.89 / 0.79 | 0.88 / 0.81 / 0.79 | 0.01, 1.96 | 0.00 |
| icp | 3 | 16 (11, 5, 0) | 0.61 / 1.01 / 0.83 | 0.94 / 1.01 / 0.95 | 0.17, 2.63 | 0.00 |
| icp | 5 | 24 (16, 6, 2) | 0.66 / 1.10 / 1.04 | 1.05 / 1.44 / 1.40 | 0.27, 2.80 | 0.00 |

Trên đúng cùng tập đoạn, B0, B3 và proposed không khác nhau đáng kể về sai số (chênh cặp trung vị ≤ 0,3 cm với r ≥ 3 cm, lớn nhất 2,8 cm trên một đoạn; riêng Kabsch r = 2 cm chỉ 5 đoạn chung, chênh −0,94 cm); B3 và proposed giống hệt nhau (chênh 0). Tập chung chỉ 5–24 đoạn trên 46 nên đây là so sánh trên phần dễ đo.

## 2. Kiểm scale độc lập với đầu mút: ICP CÓ scale vào Faro (chỉ để kiểm, không dùng suy scale)
`k` = hệ số nhân đám điểm để khớp Faro (k > 1: mô hình nhỏ hơn Faro). `1/(s_m/s)` = k kỳ vọng nếu quỹ đạo ARKit đúng scale. **Tự kiểm phương pháp:** nhân B0 với 1,03 rồi chạy lại, kỳ vọng k = 0,971; scene có độ chệch > 0,01 ghi "không đáng tin".

| Scene | Tự kiểm: k thu được (kỳ vọng 0,971), chệch | Đáng tin? | s_m/s | 1/(s_m/s) | k ICP: B0 | B1 | B3 | proposed | Mâu thuẫn với quỹ đạo (|k − 1/(s_m/s)| > 0,02 hoặc ngược chiều) |
|---|---|---|---|---|---|---|---|---|---|
| 42897599 | 0.981, +0.011 | KHÔNG | 0.977 | 1.024 | 1.010 | – | 1.016 | 1.016 | không |
| 42898849 | 0.971, -0.000 | có | 0.989 | 1.011 | 1.000 | – | 0.995 | 0.996 | không |
| 42897566 | 0.979, +0.008 | có | 1.004 | 0.996 | 1.008 | 0.995 | 1.032 | 1.031 | B3, proposed |
| 45662981 | 0.953, -0.018 | KHÔNG | 1.019 | 0.981 | 0.982 | 1.059 | 0.985 | 0.985 | B1 |
| 42445022 | 0.937, -0.034 | KHÔNG | 1.023 | 0.978 | 0.965 | 0.904 | 0.984 | 0.985 | B1 |
| 42444738 | 0.970, -0.001 | có | 1.022 | 0.978 | 0.998 | 0.980 | 0.998 | 0.998 | proposed |

Đọc kết quả:
- **Chỉ 3/6 scene đáng tin** (42898849, 42897566, dev 42444738); 42897599 chệch 0,011 (sát ngưỡng), 45662981 chệch −0,018 và 42445022 chệch −0,034: ICP có scale trên đám điểm phủ một phần Faro không thu hồi scale đủ tốt ở các scene này, nên **không dùng để kết luận** ở đó.
- Ở 3 scene đáng tin, **k của B0 là 1,000; 1,008; 0,998**: scale của B0 khớp Faro trong ±0,8%. Giá trị 1/(s_m/s) là 1,011; 0,996; 0,978. Hai con số **mâu thuẫn ở dev** (chênh +0,020: ICP nói B0 đúng scale, quỹ đạo nói mô hình lớn hơn thật 2,2%) và ở 42897566 với B3/proposed (k = 1,032 so với 0,996: chênh +0,036); theo quy tắc đặt trước chúng được gắn nhãn mâu thuẫn (ở dev chênh đúng +0,020 bằng ngưỡng nên chỉ proposed bị gắn nhãn do làm tròn; B1 ở 45662981 và 42445022 lệch rất lớn: k = 1,059 và 0,904, nhưng hai scene này không đáng tin).
- **B3/proposed ở 42897566 có scale 1,031–1,032 trong khi B0 1,008:** đám điểm sau fusion (toạ độ lấy từ VGGT căn Sim(3) theo chunk) nhỏ hơn Faro ~3%, B0 chỉ ~0,8%: tức fusion có thể mang sai scale riêng ở scene này (chưa điều tra; sai số chiều dài đoạn ở scene này vẫn nhỏ vì đoạn ngắn).
- **Quỹ đạo ARKit có vẻ không phải thước chuẩn (chưa chắc: chỉ 3 scene đáng tin):** ở các scene đáng tin B0 khớp Faro hơn là khớp quỹ đạo; ở scene không đáng tin (45662981, 42445022) B0 có k = 0,982 và 0,965 cùng chiều với 1/(s_m/s) = 0,981 và 0,978 (không đáng tin theo tự kiểm nên chỉ ghi lại).

## 3. Kích thước phòng bằng khoảng cách giữa mặt phẳng song song (thử)
Mặt phẳng từ `proposed/plane_refinement/planes.json` (bản mặc định sau sửa cổng 15/11); không sửa cổng để ép có cặp. Mặt Faro: khớp trên điểm Faro cách mặt phẳng mô hình ≤ 8 cm và cách một inlier ≤ 0,5 m.

| Scene | Sàn / trần / tường | Cặp tìm được | Khoảng cách mô hình (m) | Khoảng cách Faro (m) | Sai số (cm) | Góc giữa hai mặt: mô hình / Faro (°) |
|---|---|---|---|---|---|---|
| 42897599 | 1 / 0 / 3 | không có cặp (không có trần; tường không đủ hai mặt song song cách ≥ 1 m) | – | – | – | – |
| 42898849 | 1 / 0 / 1 | không có cặp (không có trần; tường không đủ hai mặt song song cách ≥ 1 m) | – | – | – | – |
| 42897566 | 1 / 0 / 2 | không có cặp (không có trần; tường không đủ hai mặt song song cách ≥ 1 m) | – | – | – | – |
| 45662981 | 1 / 0 / 3 | tường–tường (mặt 2 và 4) | 5.927 | 5.849 | **+7.8** (+1.34%) | 2.5 / 1.6 |
| 42445022 | 1 / 0 / 2 | không có cặp (không có trần; tường không đủ hai mặt song song cách ≥ 1 m) | – | – | – | – |
| 42444738 | 1 / 0 / 3 | không có cặp (không có trần; tường không đủ hai mặt song song cách ≥ 1 m) | – | – | – | – |

- **Không scene nào có trần** (cổng chưa từng tìm được mặt trần, kể cả dev), nên không có cặp sàn–trần nào. **Chỉ 1/6 scene (45662981) có cặp tường–tường**: 5,927 m so với Faro 5,849 m, sai **+7,8 cm (+1,3%)**, nghĩa là chiều dài lớn hơn 5 cm đã xuất hiện ở khoảng cách ~6 m.
- Cùng chiều với các chỉ báo scale ở scene này (B0 k = 0,982: mô hình lớn hơn Faro ~1,8%; s_m/s = 1,019), dù k ICP ở scene này không đáng tin. Đây là MỘT cặp, không thể khái quát.

## 4. Kết luận (không lạc quan do chọn lọc)
- **Đoạn dài > 2 m: chỉ 7 đoạn trên 46** (42897599 S03; 45662981 S02, S03; dev S07, S11, S12, S13). Đo được ở r = 5 cm: **B0 2/7 (Kabsch) hoặc 3/7 (ICP); proposed 1/7 hoặc 2/7**. Sai số trên các đoạn đo được: B0 0,57–1,93 cm (Kabsch, n = 2), 0,30–0,71 cm (ICP, n = 3); proposed 1,53 cm (n = 1), 1,76 và 3,11 cm (ICP, n = 2). **Cả 4 đoạn dài của dev (S07 5,29 m, S11 6,19 m, S13 3,30 m sát trần, S12 2,13 m ở hành lang cách điểm gần nhất 38–55 cm) đều KHÔNG đo được** (đầu mút cách điểm gần nhất 15–97 cm).
- **Vì mẫu ≤ 3 đoạn mỗi biến thể (< 10), KHÔNG kết luận được sai số chiều dài trên đoạn dài.** Số duy nhất ở quy mô phòng là cặp tường 5,9 m ở 45662981 với +7,8 cm (> 5 cm). Số "median ≈ 1 cm" ở phần 1 chỉ đúng cho đoạn ngắn và vừa (phần lớn < 2 m) đo được: tỉ lệ đạt trên cả 46 đoạn (Kabsch) chỉ 54% với B0 (25/46) và 46% với proposed (21/46); với ICP là 70% và 57%.
- **Chưa kết luận được:** sai số trên đoạn > 2 m (mẫu quá nhỏ và thiên lệch về phía đoạn dễ đo); sai số ở quy mô phòng (chỉ 1 cặp mặt phẳng); scale thật của từng scene (ICP có scale chỉ đáng tin ở 3/6 scene, hai nguồn kiểm scale mâu thuẫn ở dev và ở B3/proposed của 42897566); khác biệt B0 so với proposed ở đoạn dài (không có đoạn chung).
- **Điều khá chắc:** (1) với đoạn ngắn đo được, sai số ≈ 1 cm và không phụ thuộc biến thể; (2) độ phủ đầu mút (không phải scale) là giới hạn chính của phép đo; (3) nếu lệch scale ~1–2% (dấu hiệu ở 45662981, dev) là thật thì sai số chiều dài sẽ vượt 5 cm từ khoảng 2,5–5 m trở lên (2% × 3 m = 6 cm), nhưng chưa có đoạn dài đo được để chứng minh hoặc bác bỏ.
- Chưa sửa gì; không dùng Faro suy scale (ICP có scale và mặt phẳng Faro chỉ để kiểm). Không commit, không push, không đụng held-out.
