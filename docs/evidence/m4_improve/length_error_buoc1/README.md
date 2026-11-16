# Đo lại sai số chiều dài sau khi thêm đoạn dài (bước 1 của kế hoạch 15/11)

Chỉ đọc, không đổi pipeline, không đụng held-out, không dùng Faro suy scale. Cùng mã `scripts/length_error.py` và `length_error_v2.py`, cùng quy tắc `../length_error/PLAN_v2.md`; kết quả cũ ở `../length_error/` giữ nguyên.

## Dữ liệu
- 6 scene (5 Validation, không 47204552, và dev 42444738), **62 đoạn test** (trước đây 46). Thêm: dev +4 (S14–S17), 42445022 +2, 42897566 +3, 42897599 +3, 42898849 +1, 45662981 +3.
- `finalize --overwrite` đã xoá phần click mốc 2D trong `scale_anchor.json` ở cả 6 scene. Đã khôi phục từ `ground_truth_truoc_buoc1/` (mốc `L_real`, `endpoints_scene_xyz` không đổi; bản sau finalize giữ ở `scale_anchor.after_finalize.json`).
- 42897599: đám điểm rất nhiễu (người dùng xác nhận không chấm được thêm). 3 đoạn dài S07–S09 của scene này đã có trong dữ liệu; báo cả hai cách (có / bỏ 42897599).

## Kết quả (bán kính snap 5 cm; đạt = hợp lệ và sai số < 5 cm)
Tổng 62 đoạn: B0 đạt 33/62 (53%) Kabsch, 45/62 (73%) ICP; proposed 31/62 (50%) và 39/62 (63%).

Đoạn dài > 2 m (19 đoạn; 15 nếu bỏ 42897599):
| Phép căn | Biến thể | Hợp lệ/19 | Median (cm) | Max (cm) | Hợp lệ/15 (bỏ 42897599) | Median |
|---|---|---|---|---|---|---|
| Kabsch (của `eval`) | B0 | 9 | 1,93 | 3,09 | 6 | 1,51 |
| Kabsch | proposed | 9 | 1,50 | 3,31 | 6 | 1,24 |
| Kabsch + ICP | B0 | 13 | 0,77 | 2,10 | 9 | 0,89 |
| Kabsch + ICP | proposed | 12 | 0,75 | 3,11 | 8 | 0,49 |

- Mọi đoạn đo được đều < 5 cm. Số đoạn dài đo được theo scene (Kabsch, B0/proposed): dev 0/0 trên 6 đoạn; 42445022 2/2 (2); 42897566 1/0 (1); 42898849 1/1 (1); 45662981 2/3 (5); 42897599 3/3 (4).
- **Đo được ≠ đạt mục tiêu**: chỉ khoảng 47% (Kabsch) đến 68% (ICP) đoạn dài đo được; dev (6 đoạn dài, gồm 4 mới) vẫn 0 đo được, đầu mút cách điểm gần nhất 3–97 cm.
- **Chọn lọc có chủ ý**: đoạn được đặt ở vùng mô hình dựng được, nên các số trên là "sai số ở vùng mô hình phủ được", không phải sai số toàn phòng.
- ICP có lợi cho độ phủ (45 so với 33 đoạn hợp lệ) vì khớp mô hình vào Faro; số Kabsch (đúng `eval`) là số chính.

## Scale (bước 2 v2, chỉ để kiểm)
ICP có scale `k` (B0 / proposed): 42898849 1,000 / 0,996; 42897566 1,008 / 1,031; 45662981 0,982 / 0,985; 42445022 0,965 / 0,985; 42444738 0,998 / 0,998; 42897599 1,010 / 1,016. Đáng tin theo tự kiểm (±0,01): 42898849, 42897566, dev. **Mâu thuẫn với quỹ đạo (> 0,02) vẫn ở 42897566 (B3/proposed k lệch +0,036 so với 1/(s_m/s)) và dev proposed (+0,020).** 45662981 B1 và 42445022 B1 cũng mâu thuẫn nhưng B1 ít điểm khớp.

## Kích thước phòng bằng mặt phẳng
Vẫn 0/6 scene có trần; chỉ 45662981 có cặp tường–tường: mô hình 5,927 m so với Faro 5,849 m (**+7,8 cm, +1,3%**, như trước).

## Kết luận (trung thực)
- Với 15–19 đoạn dài thì mẫu đủ để báo (> 10), nhưng chỉ 6–13 đoạn đo được và đều ở vùng phủ tốt: median 0,5–1,9 cm tuỳ phép căn. Chưa chứng minh sai số < 5 cm cho toàn phòng.
- Dev vẫn không đo được đoạn dài nào; 42897599 nhiễu nên số của scene này không nên tin quá.
- Dấu hiệu scale (42897566 sau fusion, 45662981 +7,8 cm) còn mở: bước 3 của kế hoạch.

---
# Bước 3 — điều tra scale (chỉ đọc; `scale_check/`)
Mã: `scale_check/scale_check.py`; số: `scale_check/{fusion_scale_check.csv,plane_offsets.csv}`. Không sửa pipeline, không dùng Faro suy scale (Faro chỉ làm đáp án).

## A. 42897566: fusion có làm lệch scale ~3% không? **Không; "3%" là sai lệch của phương pháp**
- ICP có scale cho B3 vào Faro: k = 1,0318 (B0: 1,0083). Nhưng **tự kiểm B3** (nhân đám B3 với 1,03 rồi chạy lại, kỳ vọng 0,971) cho k = 1,0016, tức **chệch +0,031**, vượt ngưỡng 0,01 đã đặt (với B0 ở bước v2 chệch +0,008). Trừ chệch thì k(B3) ≈ 1,001: khớp B0.
- Chiều dài trực tiếp: độ dốc sai số có dấu theo chiều dài (hồi quy qua gốc, đoạn hợp lệ): B3 −0,23% (Kabsch, 5 đoạn) và −0,74% (ICP, 7 đoạn); B0 +0,78% và −0,30%. Không có dấu hiệu lệch 3%.
- Các scene khác: tự kiểm B3 chệch +0,015 (42897599), −0,015 (45662981), −0,015 (42445022), −0,002, −0,001 → "mâu thuẫn" ICP-scale của đám fusion ở 42897566 là **độ chệch của phương pháp**, không phải bằng chứng fusion đổi scale. Chuỗi k(B3→B0) (đám với đám) = 0,993–1,013 ở mọi scene, tức fusion không đổi scale đáng kể so với B0 (1,013 ở 42897566 cũng nằm trong khoảng chệch).
- Scale riêng từng chunk VGGT (s từ 2,8 đến 11,2 trong đơn vị COLMAP) khác nhau nhiều giữa chunk; đó là bình thường (VGGT không có scale tuyệt đối), phần được căn chunk-by-chunk. Không thấy bằng chứng căn chunk gây lệch scale chung.

## B. 45662981: tường–tường +7,8 cm — chưa quy được cho scale
- Đoạn dài cùng scene (mô hình − Faro, có dấu, Kabsch / ICP): S07 3,42 m: +3,31 / +0,25 cm (B3), S08 4,43 m: −0,79 / −0,31, S09 4,57 m: +1,79 / −0,75 (proposed ICP +2,50); độ dốc +0,30% (Kabsch), −0,2…0% (ICP). Nếu thang đo lệch +1,3% thì phải thấy +4,4…+5,9 cm ở ba đoạn này; không thấy.
- Từng mặt tường (offset mô hình so với mặt Faro cùng vùng, dọc pháp tuyến Faro): tường 2 +3,5 cm, tường 4 +4,1 cm (độ lệch chuẩn 2,5–3,0 cm trong mỗi mặt, p95 +8 cm); tường 1 +0,5 cm; sàn −0,75 cm. Hai tường đối diện cùng lệch ra ngoài ~4 cm làm ra +7,8 cm; **một lệch scale +1,3% cũng cho kiểu này (~3,8 cm mỗi bên), nhưng một lệch mặt tường thì cũng vậy**, nên với một cặp không phân biệt được. Các đoạn dài trực tiếp ủng hộ "không phải scale chung".
- Góc lệch pháp tuyến mô hình/Faro của mỗi tường 0,4–1,3°, p5–p95 của offset trong cùng một mặt rộng 8–10 cm: phép đo mặt phẳng nhạy với cách khớp và vùng; **số +7,8 cm nên coi là ± vài cm**, chưa phải sai số scale.
- Mốc 1,8148 m: tâm chiếu ≤ 4,65 px (một điểm lẻ; còn lại ≤ 2,5 px), góc tia 69–73°, 6–7 view mỗi đầu mút: chất lượng click ổn.

## C. Giới hạn do mốc (điều mới, quan trọng)
Sai số tương đối của mốc, giả định không chắc chắn đầu mút 1 cm (`endpoint_uncertainty_m`, đã ghi sẵn, không phải số đo mới) → √2 × 1 cm / L_real:
| Scene | L_real (m) | Sai số tương đối | Tương đương trên 3 m | Trên 5 m |
|---|---|---|---|---|
| 42444738 | 2,41 | 0,59% | 1,8 cm | 2,9 cm |
| 42445022 | 1,84 | 0,77% | 2,3 cm | 3,8 cm |
| 42897599 | 2,02 | 0,70% | 2,1 cm | 3,5 cm |
| 45662981 | 1,81 | 0,78% | 2,3 cm | 3,9 cm |
| 42898849 | 1,39 | 1,01% | 3,0 cm | 5,1 cm |
| 42897566 | 1,17 | 1,20% | 3,6 cm | 6,0 cm |
Vậy với mốc 1,2–1,4 m thì **chỉ riêng sai số mốc đã có thể ăn 3–6 cm trên đoạn 3–5 m**, độc lập với chất lượng mô hình. Đây là ước lượng theo giả định 1 cm; độ lệch giữa các scene (độ dốc −0,9…+0,8%) cùng cỡ.

## Kết luận bước 3
- Không có bằng chứng fusion làm lệch scale; "3%" ở 42897566 là chệch của ICP scale (tự kiểm +0,031). Chưa cần sửa fusion vì lý do scale.
- 45662981 +7,8 cm chưa quy được cho scale; các đoạn dài cùng scene cho sai số ≤ 3,3 cm.
- Rủi ro thật cho mục tiêu < 5 cm trên đoạn dài là **độ không chắc chắn của mốc** (nhất là mốc ngắn 1,2–1,4 m). Chưa kiểm: dùng nhiều mốc / mốc dài hơn; việc này đổi quy trình, cần bạn quyết.
