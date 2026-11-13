# Baseline "trước khi đổi" — M4 đợt 2 (cải thiện proposed)

Chụp ngày 12/11/2026, **trước khi sửa mã**. Git rev: `ac0d110f7e46c3ca6250b60a74e200ca6c7263f6` (`rev.txt`); cấu hình: `default.yaml` cùng thư mục
(ngưỡng fusion/gate đã khoá giữ mặc định, 12/11). Vùng đánh giá `eval.region.mode = visible_gt`. Bản gốc trong `data/scenes/.../{proposed,evaluation}` **không bị đụng**.

Nội dung mỗi `<scene>/`: `metrics.csv`, `align_*.json`, `fusion_result.json`, `planes.json`, `gate_result.json` (tóm tắt của `gate_log.csv` 1,3 MB, không chép), `proposed_topdown.png`
và `proposed_view.png` (từ `proposed/export/model_points.ply`; `view_params.json` giữ khung hình chung để các biến thể sau vẽ cùng góc: `scripts/render_cloud_views.py`).
`baseline.csv` = variant × scene × acc, comp, precision, recall, F, Chamfer.

## Số đang có (B0 → proposed): acc cm, comp cm, precision, recall, F, Chamfer cm

| Scene | Điểm MVS | B0 acc | B0 comp | B0 P | B0 R | B0 F | B0 Ch | prop acc | prop comp | prop P | prop R | prop F | prop Ch |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 42897599 | 30.216 | 1,95 | 79,5 | 0,937 | 0,071 | 0,132 | 40,7 | 4,46 | 74,6 | 0,726 | 0,054 | 0,100 | 39,5 |
| 42897566 | 234.183 | 2,20 | 40,2 | 0,917 | 0,315 | 0,469 | 21,2 | 4,01 | 40,5 | 0,754 | 0,315 | 0,444 | 22,3 |
| 42898849 | 82.429 | 12,3 | 44,3 | 0,912 | 0,238 | 0,377 | 28,3 | 6,34 | 40,0 | 0,604 | 0,195 | 0,294 | 23,2 |
| 42445022 | 153.656 | 3,28 | 41,0 | 0,848 | 0,333 | 0,479 | 22,2 | 3,50 | 37,9 | 0,825 | 0,387 | 0,527 | 20,7 |
| 45662981 | 125.091 | 3,09 | 32,8 | 0,844 | 0,307 | 0,450 | 17,9 | 3,28 | 31,9 | 0,819 | 0,349 | 0,489 | 17,6 |
| 42444738 (dev, train) | 112.002 | 4,79 | 28,1 | 0,771 | 0,261 | 0,390 | 16,4 | 4,91 | 26,7 | 0,698 | 0,258 | 0,377 | 15,8 |
| **Trung bình 6 scene** | | | | | | **0,383** | **24,46** | | | | | **0,372** | **23,17** |

B1 (VGGT thuần): F 0,506 (42897566), 0,302 (42445022), 0,311 (45662981), 0,648 (42444738); không có ở 42897599, 42898849 (không nối được chunk).

## Điểm yếu đã đo = lý do phải thay đổi

1. **Recall rất thấp:** 0,05–0,39 ở proposed (0,054 ở 42897599; 0,315 ở 42897566). Precision 0,60–0,94 nên nút thắt là phủ.
2. **Fusion làm acc xấu đi so với B0** ở hai scene: 42897566 2,20 → 4,01 cm; 42897599 1,95 → 4,46 cm (giả thuyết, chưa kiểm chứng: vị trí VGGT lệch vài cm vì chỉ căn Sim(3) theo chunk).
3. **MVS của 42897599 chỉ 30.216 điểm** (σ_depth hợp lệ 13% pixel); điểm ra của `fuse` chỉ lấy từ điểm MVS nên không phủ hơn được.
4. **F-score trung bình proposed 0,372 (6 scene) / 0,371 (5 Validation) không thắng B0 (0,383 / 0,381)**; Chamfer proposed thấp hơn (23,17 so với 24,46) nhờ comp, không nhờ phủ.
5. **Ngưỡng fusion/gate không nhạy:** quét 6 tham số, F lệch ≤ 0,0006, đã khoá giữ mặc định (commit ac0d110). Vì vậy không chỉnh lại các ngưỡng này.
6. **Cổng mặt phẳng ít tác dụng:** chỉ 0,7–19% điểm qua cổng, dịch tối đa 2,5 cm trong khi F tính ở 5 cm.
