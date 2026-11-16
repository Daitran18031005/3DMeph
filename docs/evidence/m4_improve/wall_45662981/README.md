# 45662981: lệch tường–tường — có sẵn ở MVS gốc (B0), không do fusion/cổng

Lệnh (16/11, chỉ đọc): `python docs/evidence/m4_improve/wall_45662981/wall_check.py`. Cùng phép căn ICP của proposed cho mọi biến thể; vùng = điểm trong dải 15 cm quanh tường 2 và 4 của proposed (đặt trước).

| Đám điểm | Tường 2 ↔ tường 4 | Lệch so với Faro |
|---|---|---|
| Faro | 5,818 m | — |
| B0 (MVS gốc) | 5,918 m | **+10,0 cm (+1,72%)** |
| B3 / proposed | 5,924 m | +10,5 cm (+1,81%) |
| B1 (VGGT) | không đủ điểm ở tường 2 | — |

- **B0 đã lệch gần bằng proposed**, nên fusion/cổng chỉ thêm ~0,5 cm. Nguyên nhân nằm trước fusion: MVS, mốc scale hoặc chính phép đo mặt phẳng.
- **Không phải scale chung**: các đoạn dài 3,4–4,6 m cùng scene sai ≤ 3,3 cm (`../length_error_buoc1/README.md` mục B); lệch scale 1,7% sẽ cho +6…+8 cm ở các đoạn đó.
- **Phép đo nhạy vùng chọn**: với vùng của `length_error_v2.py` Faro cho 5,849 m và lệch +7,8 cm; với vùng ở đây 5,818 m và +10,0 cm. Sai khác ~3 cm chỉ do cách chọn điểm, nên con số nên đọc là "+8…+10 cm, ± vài cm".
- Dấu của offset từng tường in ra phụ thuộc chiều pháp tuyến SVD (tuỳ ý), không dùng để kết luận tường nào lệch ra ngoài.
## Điều tra tiếp (16/11, `wall_diag.py`; ba phép kiểm phụ chạy từ scratchpad, số ghi dưới đây)

| Kiểm | Kết quả | Kết luận |
|---|---|---|
| Hướng lệch (pháp tuyến ra ngoài phòng) | tường 2 +3,9 cm, tường 4 +6,8 cm (B0) | cả hai mặt tường đều lùi ra ngoài |
| Theo khoảng cách camera / góc tới | không tăng theo khoảng cách hay góc xiên (gần camera còn lớn hơn) | không phải bias depth do nhìn xa/xiên |
| MVS lọc chặt cũ (`fused_metric_strict.ply`) | tường 2 +3,1, tường 4 +9,2 cm | không do nới lọc MVS d3 |
| Đoạn dài cùng phương 2↔4 | S08 4,43 m (chân tường cửa kính → sofa): B0 +2,4 / −0,9 cm, proposed −0,8 / −0,3 cm (Kabsch / ICP) | khoảng cách giữa VẬT trong phòng theo phương này đúng; không phải scale |
| Phân bố điểm quanh tường 4 | Faro có nhiều điểm phía SAU mặt tường (+5…+55 cm) | tường 4 có kính/khoảng hở (laser xuyên qua) |
| Cùng phép đo trên mọi tường/sàn của 6 scene (B0) | tường lệch cả hai chiều −4,2…+4,4 cm; sàn −1,5…+2,4 cm | mặt tường MVS lệch ±4 cm là mức nhiễu chung; 45662981 tình cờ có ba tường cùng lệch ra ngoài (w1 +2,6, w2 +3,9, w4 +6,8) |

**Kết luận:** không phải lỗi của pipeline có thể sửa (không do fusion, cổng, nới lọc MVS hay scale). Lệch nằm ở **mặt tường do MVS dựng** (tường giấy dán trơn, cửa mở, kính/rèm) cộng độ nhạy của phép khớp mặt phẳng. Không đổi mã hay tham số: chỉnh riêng cho một scene là chỉnh theo kết quả.
**Cách dùng số:** khoảng cách tường–tường của mô hình có sai số cỡ ±4 cm mỗi tường (tới ~8–10 cm cho một cặp xấu); đo kích thước phòng nên đặt đầu mút ở vật/cạnh rõ (như S08), không dựa vào khớp mặt tường.

- Còn mở (chưa kiểm chứng): MVS dựng tường dày/lệch ra ngoài ở hai tường xa camera (bias depth ở góc nhìn xiên) là giải thích phù hợp nhất với "B0 lệch, đoạn dài không lệch", nhưng chưa có phép đo riêng.
