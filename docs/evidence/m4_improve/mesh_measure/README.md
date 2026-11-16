# Đo chiều dài trên mesh Poisson hiện có — KHÔNG ĐẠT quy tắc đặt trước (giữ đo trên điểm)

Quy tắc: `PLAN.md` (ghi trước khi chạy). Lệnh (16/11):
`python scripts/length_error.py --target mesh --align {kabsch,icp} --max-maps 0 --out docs/evidence/m4_improve/mesh_measure`.
Mesh = `proposed/export/model.glb` (Poisson depth 9, `density_quantile` 0,05), cùng thời điểm với `refined_points.ply` ở cả 6 scene; mẫu đều 0,5 cm. Mốc: proposed trên điểm ở `../length_error_doimoc/`.

| Phép căn | Hợp lệ trên điểm | Hợp lệ trên mesh | Cả hai | Chỉ mesh | Mất khi sang mesh | Median (cả hai) điểm → mesh | Khoảng cách đầu mút trung vị điểm → mesh |
|---|---|---|---|---|---|---|---|
| Kabsch | 35/62 | **32/62** | 30 | 2 (cả 2 < 5 cm) | 5 | 1,44 → 1,04 cm | 2,65 → 3,20 cm |
| ICP | 39/62 | **33/62** | 33 | 0 | 6 | 0,80 → 1,33 cm | 2,08 → 2,47 cm |

- Quy tắc 1 (tăng ≥ 5 đoạn): **không đạt** (−3 và −6). Quy tắc 2 đạt ở Kabsch, không đạt ở ICP (+0,53 cm). Quy tắc 3 đạt (2/2) nhưng chỉ 2 đoạn.
- Đầu mút trên mesh nằm **xa** Faro hơn trên điểm: Poisson làm trơn và bỏ đỉnh mật độ thấp (5% thấp nhất), nên mép/góc (chỗ đặt đầu mút) bị cắt hoặc bo tròn; lỗ lớn không được lấp vì chính bước bỏ mật độ thấp xoá phần nội suy.
- Mất: Kabsch 42897599 S03, 42898849 S02/S07, 42897566 S08, 45662981 S07; ICP 42897599 S09, 42898849 S06/S07, 42897566 S01, 45662981 S03, 42444738 S09.
- Kết luận: mesh Poisson hiện tại không tăng độ phủ. Không chỉnh tham số Poisson theo số này. Lượt sau (TSDF hoặc mesh khác) cần quy tắc riêng đặt trước.
