# Hướng A — lấp lỗ MVS bằng điểm VGGT (KHÔNG ĐẠT chỉ số mục tiêu; không chạy 6 scene)

Mã: `pipeline/fusion/fill.py` (`fill_points`) + `vggt_candidates` trong `pipeline/fusion/stage.py`; khoá `fusion.fill_enabled` (mặc định false), `fill_voxel_m`, `fill_min_views`, `fill_min_conf`, `fill_stride`.
Giá trị đặt TRƯỚC khi chạy: ô 0,10 m, ≥ 3 view khác nhau trong ô, c_model ≥ 0,5, lấy mỗi 4 pixel; chỉ nhận ô không nằm trong lân cận 1 ô (26 ô) của điểm MVS. Không chỉnh sau khi xem số.
Chạy: `python scripts/eval_variants.py --name proposed_a --scenes 42897599 42897566 --set fusion.fill_enabled=true` (MVS mặc định, không kết hợp hướng D).

## Chỉ số mục tiêu (đặt trước): recall tăng ≥ 0,05 trên 42897599 và 42897566, precision giảm không quá 0,10 → KHÔNG ĐẠT

| Scene | | điểm thêm | F | acc | comp | P | R | Chamfer |
|---|---|---|---|---|---|---|---|---|
| 42897599 | proposed | | 0,100 | 4,46 | 74,6 | 0,726 | 0,054 | 39,5 |
| | proposed_a | 504 | 0,115 | 4,55 | 66,1 | 0,722 | 0,062 (+0,008) | 35,3 |
| 42897566 | proposed | | 0,444 | 4,01 | 40,5 | 0,754 | 0,315 | 22,3 |
| | proposed_a | 540 | 0,469 | 4,03 | 30,5 | 0,752 | 0,341 (+0,026) | 17,3 |

Precision gần như không đổi; recall tăng +0,008 và +0,026, dưới +0,05.

## Vì sao ít điểm được thêm (số đo từ một lượt chẩn đoán 12/11, script chẩn đoán không lưu lại)
Ứng viên VGGT có nhiều: 42897599 có 530.655 điểm với c_model ≥ 0,5, trong đó 360.885 (68%) nằm ở ô xa điểm MVS; 42897566: 778.081 và 84.923 (11%). Nhưng chỉ ~500 ô qua điều kiện "≥ 3 view khác nhau trong cùng ô 10 cm".
Nghĩa là điểm VGGT của các view khác nhau hầu như không trùng ô 10 cm: VGGT không đủ nhất quán đa view ở mức vài cm (phù hợp số đo fusion: lệch VGGT so với COLMAP theo cặp trung vị 6,5 cm, p90 26,3 cm ở 42897599).
Không thử nới ô/số view/ngưỡng vì sẽ là chỉnh theo kết quả. Nếu muốn thử, nên đặt giá trị mới trước (ví dụ ô 0,2 m hoặc ≥ 2 view) và coi là đợt thử khác.
