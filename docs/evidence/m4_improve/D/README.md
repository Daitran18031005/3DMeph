# Hướng D — làm dày MVS bằng nới tham số `stereo_fusion` (ĐẠT chỉ số mục tiêu và điều kiện chung; có chú ý quan trọng bên dưới)

Mã: `scripts/stereo_fusion_variant.py` (chạy lại `stereo_fusion` trên depth map MVS có sẵn, ghi `mvs/fused_<tag>.ply` + `.vis`, không đụng `fused.ply`, không chạy lại PatchMatch/GPU, ~10 s/scene),
khoá `fusion.mvs_cloud` (mặc định `fused.ply`) để `fuse` đọc PLY đó. Đánh giá bằng `scripts/eval_variants.py --name proposed_d3 --set fusion.mvs_cloud=fused_d3.ply`.

## Nguyên nhân MVS thưa (đo): depth map hình học chỉ giữ ít pixel
Pixel có depth > 0 (10 ảnh/scene): 42897599 photometric 0,983, **geometric 0,143**; 42897566 0,999 / 0,522; 42898849 0,999 / 0,274. Bộ lọc nhất quán hình học của PatchMatch (và các ngưỡng `stereo_fusion`) mới là nút thắt, không phải số keyframe.

## Thang thử trên 42897599 (ba nấc đặt trước; cả ba đều ghi ở đây)
Tham số mặc định COLMAP: `min_num_pixels 5, max_reproj_error 2, max_depth_error 0.01, max_normal_error 10, check_num_images 50`.

| Nấc | Tham số | Điểm MVS | F | acc | comp | P | R | Chamfer |
|---|---|---|---|---|---|---|---|---|
| proposed (baseline) | mặc định | 30.216 | 0,100 | 4,46 | 74,6 | 0,726 | 0,054 | 39,5 |
| d1 | min_num_pixels 3, max_reproj_error 4, max_depth_error 0.02, check_num_images 100 | 80.594 (×2,67) | 0,161 | 5,52 | 58,1 | 0,628 | 0,093 | 31,8 |
| d2 | `--input-type photometric` | 28.252 (×0,94) | 0,122 | 4,86 | 53,4 | 0,703 | 0,067 | 29,1 |
| **d3** | min_num_pixels 2, max_reproj_error 8, max_depth_error 0.05, max_normal_error 30, check_num_images 100 | **308.660 (×10,2)** | **0,248** | 7,37 | 46,8 | 0,512 | **0,164** | 27,1 |

Chỉ số mục tiêu (đặt trước): điểm MVS ≥ 3× và recall tăng ≥ 0,05 trên 42897599 → **d1 chưa đạt (×2,67; +0,039), d2 chưa đạt, d3 đạt (×10,2; +0,110)**. d3 là nấc thứ ba, thử sau khi thấy d1/d2 chưa đủ; không tinh chỉnh thêm.

## d3 trên cả 6 scene (`summary.csv`; baseline: `../baseline_truoc_doi/`)

| Trung bình 6 scene | F | Chamfer (cm) | acc | recall |
|---|---|---|---|---|
| B0 (mặc định) | 0,3828 | 24,46 | 4,60 | 0,254 |
| proposed (baseline) | 0,3719 | 23,17 | 4,42 | 0,260 |
| **proposed_d3** | **0,4907** | **16,62** | 6,26 | **0,426** |
| B0 trên MVS d3 (`B0_d3_reference.csv`) | 0,4926 | 18,86 | 9,42 | 0,398 |

Điều kiện chung: ΔF +0,1187 (≥ +0,010 ✓); Chamfer −28,3% (✓); đối chứng ΔF 42445022 +0,085, 45662981 +0,134, 42444738 +0,122 (✓) → ĐẠT.

## Chú ý quan trọng khi diễn giải
1. **Phần lớn mức tăng đến từ việc nới `stereo_fusion` của COLMAP, không đến từ fusion/gate.** B0 chạy trên chính MVS d3 (không VGGT, không gate) đạt F 0,4926, ngang proposed_d3 (0,4907). Fusion + gate chỉ còn lợi về hình học: Chamfer 16,62 so với 18,86 cm, acc 6,26 so với 9,42 cm (rõ nhất ở 42898849: acc 9,05 so với 27,33 cm), nghĩa là VGGT kéo điểm nhiễu của MVS dày về bề mặt.
2. Đổi lại precision giảm (0,73 → 0,51 ở 42897599; acc trung bình của proposed_d3 xấu hơn B0 mặc định: 6,26 so với 4,60 cm). Mô hình dày hơn nhưng nhiễu hơn (ảnh `../baseline_truoc_doi/<scene>/proposed_d3_*.png`: có vệt điểm bay dọc tia nhìn).
3. B0 baseline của đề tài (mặc định COLMAP) vì thế KHÔNG còn là cơ sở công bằng nếu lấy MVS d3 làm chuẩn: cần quyết định dùng `stereo_fusion` mặc định hay d3 cho cả B0 và proposed. Việc này chưa được thực hiện; số B0 chính thức vẫn là bản mặc định.
4. Mọi scene đã được nhìn khi chọn d3 (đợt phát triển); bằng chứng cuối cùng thuộc về lần chạy held-out một lần.
