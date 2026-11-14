# Export trên MVS d3 (M4 đợt 3b) — chạy được; mesh Poisson xấu rõ rệt (chỉ ghi nhận)

Mốc git trước khi chạy: `7232c3b`. Lệnh: `python -m pipeline.run --scene arkitscenes/<id> --config configs/default.yaml --from-stage export --to-stage export` (stage `export` chỉ có cho proposed; **không có export cho B0**).
Trước khi ghi đè, bản export cũ (MVS lọc chặt) được sao lưu ở `data/scenes/arkitscenes/<id>/proposed/variants/strict_old/export/` (cùng bản sao `fusion`, `plane_refinement`, `alignment` từ lần `refuse_mvs.py`); export mới ghi vào chỗ chuẩn `proposed/export/`.

## Số đo (6 scene; Poisson depth 9, `export.density_quantile` 0,05)

| Scene | Điểm vào Poisson (cũ → mới) | Đỉnh (cũ → mới) | Mặt | `model.glb` | Thời gian (cũ → mới) | Mặt phẳng sàn (cũ → mới) | Cao sàn y_floor, m (cũ → mới) | Hộp bao (m) |
|---|---|---|---|---|---|---|---|---|
| 42444738 (dev) | 112.002 → 803.970 | 213.390 → 579.865 | 1.153.726 | 20,8 MB | 2,8 → 9,8 s | 4 → 5 | −1,339 → −1,349 | 5,56 × 2,69 × 7,17 |
| 42445022 | 153.656 → 839.599 | 210.301 → 404.033 | 803.966 | 14,5 MB | 3,7 → 7,6 s | 3 → 5 | **−0,650 → −1,377** | 5,69 × 2,37 × 3,90 |
| 42897566 | 234.183 → 854.469 | 431.566 → 845.662 | 1.685.354 | 30,4 MB | 8,8 → 11,5 s | 5 → 6 | −1,403 → −1,413 | 4,58 × 2,10 × 5,05 |
| 42897599 | 30.216 → 308.573 | 52.536 → 225.058 | 446.440 | 8,1 MB | 1,0 → 4,0 s | 3 → 4 | **−0,503 → −1,369** | 9,55 × 2,45 × 8,10 |
| 42898849 | 82.429 → 650.489 | 183.514 → 600.114 | 1.190.763 | 21,5 MB | 2,8 → 9,4 s | 7 → 8 | −1,495 → −1,496 | 8,79 × 3,02 × 12,69 |
| 45662981 | 125.091 → 998.375 | 235.433 → 596.737 | 1.185.033 | 21,4 MB | 3,4 → 9,7 s | 5 → 5 | −1,400 → −1,400 | 8,34 × 3,57 × 7,25 |

- Cả 6 `model.glb` mở được bằng `trimesh` (đủ đỉnh/mặt, không lỗi); **không scene nào kín (`is_watertight` = False)**. `python -m pipeline.export.measure --a ... --b ...` đo được một đoạn thử 0,500 m ở cả 6 scene (chỉ kiểm công thức (30)).
- **Phát hiện phụ:** ở 42445022 và 42897599 bản export cũ chọn nhầm "sàn" (cao −0,65 và −0,50 m; suy luận chưa kiểm chứng: một mặt phẳng ngang nằm cao như mặt bàn, vì MVS thưa); với d3 chọn mặt thấp hơn (−1,38 và −1,37 m, cùng mức −1,35…−1,50 m của 4 scene còn lại), nên hệ "model: sàn y = 0" của hai scene này dời ~0,7–0,9 m so với bản cũ.
- **Hệ quả cho chấm tay (chỉ scene dev có `endpoints_*.json`):** hệ model đổi nên các đầu mút đã chấm trên model cũ không còn đúng; `eval` dev sau export cho `n_valid` 3 → 1 ở B3/abl_quality (hình học acc, comp, F, Chamfer KHÔNG đổi). Số trước export: `dev_metrics_before_export.csv`; bản MVS lọc chặt: `evaluation/variants/strict_old/metrics.csv`. Muốn so chiều dài chấm tay trên d3 phải chấm lại trên `model_points.ply` mới.
- 5 scene Validation chấm chiều dài tự động (đầu mút Faro snap vào điểm) nên không phụ thuộc hệ model.

## Mesh trông thế nào (ảnh `<scene>/montage.png`: hàng trên 2 ảnh điểm 300k mẫu, hàng dưới mesh; trên-xuống và góc xiên; `scripts/render_mesh_views.py`, ray casting CPU)
- **Bố cục phòng nhận ra được** ở 42444738, 45662981, 42897566, 42898849, 42445022: sàn, tường, đồ lớn (tủ, ghế, giường/sofa). **42897599 không nhận ra phòng**: mesh vỡ thành cụm cục, mảng thưa lớn, đoạn dải dài chéo (vệt điểm bay) bị Poisson dựng thành mặt.
- **Bề mặt gồ ghề, sần ở mọi scene**: sàn phẳng ngoài đời hiện lồi lõm cỡ cm (đặc biệt 42897566, 45662981); tường mỏng và sần; đồ vật thành "cục" có bóng nổi và các mảnh vỏ nhỏ trôi nổi.
- **Lỗ lớn** ở vùng ít điểm (42898849, 42897599, 42444738 giữa phòng): MVS lọc vẫn thưa ở sàn ít hoạ tiết nên Poisson để trống.
- **Vệt điểm bay** còn thấy ở ảnh điểm (đường thẳng dài xuyên phòng ở 42897599, vài vệt ở 42898849, 42445022) và đã đi vào mesh thành dải mỏng.
- **Trần: 0 mặt phẳng ở cả 6 scene** (nguyên nhân chưa kiểm tra); "mặt phẳng sàn" 4–8 mỗi scene nghĩa là sàn bị tách thành nhiều mảnh phẳng hoặc nhận thêm bề mặt ngang khác, chưa kiểm tra.
- **Hướng đề xuất (chỉ ghi nhận, không đổi pipeline):** (1) TSDF tích hợp từ depth map MVS/VGGT (Open3D `ScalableTSDFVolume`) cho mặt mịn hơn và lỗ được lấp theo ray; (2) ép phẳng mặt lớn: thay điểm nằm trong dải sàn/tường (đã có plane gate) bằng mặt phẳng lý tưởng trước Poisson, hoặc dựng sàn/tường bằng đa giác; (3) tăng `export.density_quantile` hoặc hạ `poisson_depth` 8 để bớt cục, đổi lại mất chi tiết; (4) lọc vệt điểm bay trước Poisson (bộ lọc nhiễu đợt 3 không đạt theo F nhưng có thể dùng riêng cho mesh).
Chỉ số hình học (34)–(35) tính trên điểm, không tính trên mesh, nên mesh xấu không ảnh hưởng bảng F/Chamfer. Mọi kết luận ở đây dựa trên ảnh đã xem và là định tính.
