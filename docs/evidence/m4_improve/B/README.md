# Hướng B — kẹp độ dịch của điểm fuse quanh điểm MVS (KHÔNG ĐẠT điều kiện chung)

Mã: `clamp_shift` (`pipeline/fusion/fusion.py`), khoá `fusion.max_shift_m` (mặc định `null` = hành vi cũ; README fusion). Chạy: `python scripts/eval_variants.py --name proposed_b02 --scenes ... --set fusion.max_shift_m=0.02`
(biến thể `proposed_b02` = 0,02 m, `proposed_b05` = 0,05 m, `proposed_b00` = 0 m = giữ đúng vị trí MVS). Ghi vào `proposed/variants/<tên>/`, `evaluation/variants/<tên>/metrics.csv`; `proposed/` gốc không đổi (băm kiểm).
Tái lập: chạy không `--set` (`--name check`) trên 42897599 ra đúng số baseline (F 0,100, acc 4,46, Chamfer 39,5).
Bảng đủ 6 scene × (B0, proposed, 3 biến thể): `summary.csv`; baseline: `../baseline_truoc_doi/`.

## Chỉ số mục tiêu (đặt trước): acc giảm ≥ 1,0 cm so với proposed và cách B0 ≤ 1,0 cm, trên 42897566 và 42897599 → ĐẠT

| acc (cm) | B0 | proposed | b02 | b05 | b00 |
|---|---|---|---|---|---|
| 42897599 | 1,95 | 4,46 | 2,21 | 2,82 | 1,95 |
| 42897566 | 2,20 | 4,01 | 2,28 | 2,57 | 2,20 |

## Điều kiện chung (đặt trước): ΔF trung bình ≥ +0,010; Chamfer trung bình không tệ hơn 5%; đối chứng không mất F quá 0,010 → KHÔNG ĐẠT (cả ba biến thể)

| Trung bình 6 scene | F | Chamfer (cm) | ΔF vs proposed | Chamfer tương đối | ΔF 42445022 / 45662981 / 42444738 |
|---|---|---|---|---|---|
| B0 | 0,3828 | 24,46 | | | |
| proposed (baseline) | 0,3719 | 23,17 | | | |
| b02 | 0,3866 | 24,40 | +0,0147 | +5,3% (vượt 5%) | −0,033 / −0,031 / +0,013 |
| b05 | 0,3864 | 24,47 | +0,0144 | +5,6% | −0,023 / −0,018 / +0,011 |
| b00 | 0,3828 | 24,46 | +0,0108 | +5,5% | −0,049 / −0,039 / +0,014 |

Kết luận: acc về gần B0 nhưng F không tăng thật. `b00` trùng B0 từng chữ số (F, Chamfer): kẹp về 0 chỉ trả lại B0. Ở 42445022 và 45662981 phần F mà fusion VGGT từng thắng B0 (+0,048 và +0,039) bị mất khi kẹp,
vì chính độ dịch về phía VGGT làm tăng recall ở hai scene đó (0,333 → 0,387; 0,307 → 0,349) trong khi làm giảm precision ở 42897566, 42897599, 42898849. Giữ baseline.
