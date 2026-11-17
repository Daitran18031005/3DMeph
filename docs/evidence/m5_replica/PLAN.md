# M5 Replica — quy tắc kết luận ĐẶT TRƯỚC khi chạy 17 scene còn lại (17/11/2026)

Ghi sau pilot room_0 (đã thấy số của room_0), trước khi chạy các scene khác. Không đổi sau khi thấy số.

**Dữ liệu:** 18 scene Replica (13 không gian). Render Open3D màu đỉnh, 600 khung, quỹ đạo chữ nhật sát tường nhìn vào giữa phòng (`scripts/render_replica.py`);
mốc scale tự động trên mesh GT chiếu bằng pose GT, tam giác hoá COLMAP theo (4). Chỉ số mặt phẳng chỉ có ở 16 scene có `preseg` (thiếu apartment_0, apartment_1).
Cấu hình pipeline giữ nguyên `configs/default.yaml` (không chỉnh tham số nào trên Replica).

**Chỉ số (36):** P2Plane (cm, trung bình theo mặt GT có ≥ 200 điểm gán), PlaneRecall; kèm Acc/Comp/Chamfer/F (δ = 5 cm). Ngưỡng `eval.plane.*` đặt trước.
Trung bình: theo scene rồi theo **13 không gian** (scene cùng không gian gộp trước) [ĐC §11].

**Kết luận về plane gate (mục tiêu ĐC §21):**
- "Đạt": P2Plane(proposed) giảm ≥ 15% so với B3 (trung bình theo không gian) **và** ΔF(proposed − B3) ≥ −0,01.
- "Không đạt": ngược lại; báo số thật.
- Ablation 2 (`abl_gate`, ép phẳng không cổng) báo kèm để so: nếu ép phẳng làm F giảm > 0,01 so với proposed thì cổng có tác dụng "bảo vệ hình học".
- Scene SfM đăng ký < 90% hoặc pipeline lỗi: vẫn báo, nhưng tách khỏi trung bình chính (bảng phụ).

**Pilot room_0 (đã biết trước khi ghi quy tắc):** P2Plane B3 2,18 cm, proposed 2,20 cm, abl_gate 3,14 cm; F 0,771 / 0,770 / 0,597.
