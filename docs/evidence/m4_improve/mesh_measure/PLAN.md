# Đo chiều dài trên mesh (M4, bước 5 "sửa mesh", lượt 1) — quy tắc ĐẶT TRƯỚC khi chạy

Ngày ghi: 2026-11-16, trước khi có số. Người dùng duyệt hướng "làm bước 5 trước để tăng độ phủ" (16/11).

**Câu hỏi:** đo đầu mút trên mặt `proposed/export/model.glb` (Poisson hiện có, không đổi tham số) thay vì trên đám điểm `refined_points.ply` thì số đoạn đo được tăng bao nhiêu, và sai số có xấu đi không?
Cơ sở: (30) của đề cương đo ‖B − A‖ trên mô hình GLB.

**Cách đo:** `scripts/length_error.py --target mesh`. Mesh đổi ngược về hệ COLMAP × s_m bằng `measurements.json["frame"]`, lấy mẫu đều mặt ~0,5 cm (lấy mẫu là xấp xỉ, sai ≤ ~0,5 cm),
rồi dùng đúng phép căn (Kabsch, ICP), bán kính 5 cm, 62 đoạn, 6 scene như `../length_error_doimoc/`. Chỉ có mesh cho proposed (không có export cho B0).
Mốc so sánh: proposed trên điểm ở `../length_error_doimoc/{kabsch,icp}/per_segment.csv`.

**Nhận "đo trên mesh" nếu cả ba (cho từng phép căn, Kabsch là chính):**
1. Số đoạn test hợp lệ tăng ≥ 5 (trên 62).
2. Trên các đoạn hợp lệ ở CẢ hai cách đo: median sai số không tăng quá 0,3 cm.
3. Trên các đoạn CHỈ mesh mới đo được: ≥ 80% sai < 5 cm.

Không chỉnh bán kính, mật độ mẫu hay tham số Poisson sau khi xem số. Không đụng held-out. Báo riêng "trên điểm thật" và "trên mặt nội suy"; nhận không có nghĩa mesh đúng ở vùng không có điểm.
Không đạt → ghi nhận, sang lượt 2 (dựng mesh khác, ví dụ TSDF) với quy tắc riêng đặt trước.
