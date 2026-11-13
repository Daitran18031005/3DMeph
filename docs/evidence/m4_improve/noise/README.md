# Giảm nhiễu sau MVS d3 — KHÔNG ĐẠT quy tắc đặt trước (cả f1 và f2 giữ TẮT)

Mốc: sau bước 1–2 (`../baseline_d3/`). Mã: `pipeline/fusion/noise.py` (`min_views_mask`, `statistical_outlier_mask`, `noise_keep_mask`), khoá `fusion.filter_min_views`, `fusion.filter_sor_std_ratio`, `fusion.filter_sor_k`
(đều mặc định `null`/20 = tắt, README fusion khớp). Quét: `python scripts/sweep_noise.py --out-root data/sweeps/m4_noise` (6 scene × 11 cấu hình, một yếu tố một lần, `proposed/` có băm kiểm không đổi);
dữ liệu thô `sweep_noise.csv`, trung bình theo cấu hình `summary_by_config.csv`, hình `pr_by_config.png` (precision–recall theo cấu hình: hai scene mục tiêu và trung bình 6 scene).
Đường tích hợp trong `fuse` cho kết quả TRÙNG bảng quét (42897599: biến thể `proposed_d3_f1` min_views 3 → P 0,623 R 0,120 F 0,201; `proposed_d3_f2` std_ratio 2,0 → P 0,592 R 0,145 F 0,233, giống từng chữ số).

## Quy tắc chọn (đặt trước, không đổi)
Trong mỗi bộ lọc chọn cấu hình NHẸ NHẤT thoả cả ba: (1) precision trung bình của 42897599 và 42898849 tăng ≥ 0,05; (2) recall trung bình 6 scene giảm không quá 0,02;
(3) F trung bình không giảm quá 0,005, Chamfer trung bình không tệ hơn 5%, scene đối chứng (42445022, 45662981, 42444738) không mất F quá 0,010. Cộng leave-one-scene-out.

## Kết quả (trung bình 6 scene so với không lọc: F 0,4939, Chamfer 16,65 cm, precision 0,612, recall 0,427)

| Cấu hình | Điểm giữ | ΔP (2 scene mục tiêu) | Δrecall | ΔF | Chamfer | Đạt |
|---|---|---|---|---|---|---|
| f1 min_views 2 | 99,9% | +0,000 | −0,000 | −0,0000 | +0,0% | không (precision không tăng) |
| f1 min_views 3 | 37,4% | **+0,055** | −0,066 | −0,035 | +13,0% | không |
| f1 min_views 4 | 14,9% | +0,114 | −0,126 | −0,084 | +35,8% | không |
| f1 min_views 6 | 3,8% | +0,205 | −0,227 | −0,189 | +116,6% | không |
| f2 std 1,0 (k=20) | 90,9% | +0,063 | −0,087 | −0,047 | +26,9% | không |
| f2 std 1,5 | 94,7% | +0,042 | −0,065 | −0,032 | +23,0% | không |
| f2 std 2,0 | 96,6% | +0,028 | −0,050 | −0,025 | +21,0% | không |
| f2 std 3,0 | 98,4% | +0,015 | −0,031 | −0,016 | +18,3% | không |
| f2 std 2,0, k=10 | 96,6% | +0,027 | −0,048 | −0,023 | +18,0% | không |
| f2 std 2,0, k=40 | 96,6% | +0,029 | −0,051 | −0,026 | +27,3% | không |

Chọn trên cả 6 scene: f1 KHÔNG ĐẠT, f2 KHÔNG ĐẠT. Leave-one-scene-out (chọn trên 5 scene còn lại): **không cấu hình nào đạt ở cả 6 lần bỏ**, nên không có cấu hình để đo trên scene bỏ ra. Giữ cả hai bộ lọc tắt; không nới ngưỡng.

## Vì sao không đạt (từ bảng)
- **min_views = 2 không lọc gì** (giữ 99,9%): d3 đã đòi ≥ 2 pixel. **min_views = 3 xoá 62,6% điểm**: precision hai scene mục tiêu tăng +0,055 (vừa đủ điều kiện 1) nhưng recall mất 0,066 và Chamfer +13%, F −0,035; đối chứng mất F 0,021–0,038. Từ 4 trở lên mất quá nhiều.
- **Ngoại lai thống kê xoá ít điểm (1,6–9,1%) nhưng vẫn mất recall nhiều hơn precision thu được** (std 1,0: P +0,063, recall −0,087): các điểm có khoảng cách láng giềng lớn không chỉ là nhiễu mà còn là vùng bề mặt thưa mà Faro thật có, nên xoá chúng làm recall và comp tệ hơn (Chamfer +18% đến +27%).
- Không có điểm cân bằng: tăng precision luôn đi kèm mất recall lớn hơn. Nhiễu còn lại của d3 nằm lẫn trong vùng có thật, không tách được bằng số view hay mật độ cục bộ.
Đây là kết quả phát triển (5 Validation đã được nhìn khi quét ngưỡng), không phải bằng chứng cuối.
