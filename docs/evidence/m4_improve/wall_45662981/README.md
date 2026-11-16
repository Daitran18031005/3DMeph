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
- Còn mở (chưa kiểm chứng): MVS dựng tường dày/lệch ra ngoài ở hai tường xa camera (bias depth ở góc nhìn xiên) là giải thích phù hợp nhất với "B0 lệch, đoạn dài không lệch", nhưng chưa có phép đo riêng.
