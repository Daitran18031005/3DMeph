# Chẩn đoán cổng plane gate (M4 đợt 3c) — chỉ đọc kết quả có sẵn, KHÔNG đổi ngưỡng

Mã: `scripts/diagnose_gate.py` (chạy `python scripts/diagnose_gate.py`); số liệu thô `<scene>.json`. Đầu vào: `proposed/fusion`, `proposed/plane_refinement` (MVS d3, gate với τ_r 5 cm, τ_n 15°, τ_w 0,5, α 0,5).
Đáp án: Faro, căn y như `eval` (Kabsch cắt tỉa theo camera, rồi ICP cứng scale = 1 trên cloud chưa qua cổng; cùng một phép căn cho trước/sau để cô lập tác động của cổng), trong vùng chấm `visible_gt`.
"Chính xác" ở đây = tỉ lệ điểm cách Faro ≤ 5 cm (cùng δ với F-score). Đây là chẩn đoán phát triển trên 5 Validation + dev, không phải bằng chứng cuối.

## A. Thang của `w_k` (độ tin cậy) và vì sao ngưỡng 0,5 gần như không bao giờ đạt

| Scene | `w_k` trung vị | `w_k` phân vị 95% | c_model | f(e_reproj) | f(σ_depth) | q_blur | q_texture |
|---|---|---|---|---|---|---|---|
| 42897599 | 0,228 | 0,488 | 0,42 | 0,639 | 0,975 | 1,00 | 1,00 |
| 42898849 | 0,151 | 0,449 | 0,45 | 0,622 | 0,918 | 1,00 | 1,00 |
| 42897566 | 0,227 | 0,601 | 0,77 | 0,613 | 0,960 | 1,00 | 1,00 |
| 45662981 | 0,152 | 0,481 | 0,64 | 0,614 | 0,945 | 0,82 | 0,75 |
| 42445022 | 0,170 | 0,518 | 0,76 | 0,560 | 0,955 | 0,73 | 1,00 |
| 42444738 | 0,187 | 0,477 | 0,75 | 0,610 | 0,918 | 0,80 | 0,91 |

(cột 4–8 là trung vị của từng hệ số trong 6 hệ số của (19), trên các cặp (điểm, ảnh).)
- `w` là tích sáu số ≤ 1 nên luôn nhỏ. **Phân vị 95% của `w_k` chỉ 0,45–0,60: ngưỡng 0,5 nằm trên ~95% điểm** (chỉ 42897566 có ~5% điểm vượt).
- **Hệ số thấp nhất ở mọi scene là f(e_reproj) ≈ 0,56–0,64**: sai số chiếu lại trung vị ≈ 1 px, mà thang đổi là e^(−e/2 px). Một điểm hoàn hảo trong dữ liệu thật vẫn chỉ đạt f ≈ 0,6. Ví dụ trong đề cương dùng e = 0,06 px (f = 0,97), không giống dữ liệu thật.
- **c_model (độ tin của VGGT)** thấp ở 42897599 (0,42) và 42898849 (0,45; hơn một nửa số cặp dưới 0,5). 7–10% cặp thiếu σ_depth (coi `w = 0`).
- Kết luận: thang `w_k` thật nằm ở khoảng 0–0,6, trong khi ví dụ đề cương nghĩ tới 0,7–0,95. Ngưỡng 0,5 không có căn cứ dữ liệu.

## B. `w_k` có báo trước độ chính xác không? Có ở 5/6 scene (không ở dev)

| Scene | Chính xác chung | Thập phân vị `w_k` thấp nhất | cao nhất | Spearman(w_k, sai số) |
|---|---|---|---|---|
| 42897599 | 0,663 | 0,523 | 0,732 | −0,119 |
| 42898849 | 0,575 | 0,257 | 0,732 | −0,331 |
| 42897566 | 0,839 | 0,694 | 0,960 | −0,220 |
| 45662981 | 0,736 | 0,549 | 0,895 | −0,259 |
| 42445022 | 0,855 | 0,760 | 0,967 | −0,203 |
| 42444738 (dev) | 0,667 | 0,633 | 0,620 | +0,022 |

(Spearman âm = `w_k` cao ↔ sai số thấp; yếu nhưng đúng chiều ở 5/6.) Ở dev `w_k` không phân biệt được.

## C. Từng điều kiện của cổng: điểm qua so với điểm trượt (tỉ lệ ≤ 5 cm, qua/trượt)

| Scene | r < 5 cm | θ < 15° | w_k > 0,5 | Tỉ lệ điểm đạt r / θ / w |
|---|---|---|---|---|
| 42897599 | 0,76 / 0,43 | 0,83 / 0,61 | 0,72 / 0,66 | 0,71 / 0,25 / 0,04 |
| 42898849 | 0,69 / 0,45 | 0,72 / 0,54 | 0,76 / 0,57 | 0,53 / 0,18 / 0,02 |
| 42897566 | 0,88 / 0,69 | 0,93 / 0,81 | 0,95 / 0,82 | 0,80 / 0,23 / 0,15 |
| 45662981 | 0,81 / 0,56 | 0,85 / 0,69 | 0,88 / 0,73 | 0,69 / 0,27 / 0,04 |
| 42445022 | 0,89 / 0,77 | 0,93 / 0,84 | 0,98 / 0,85 | 0,72 / 0,18 / 0,06 |
| 42444738 | 0,71 / 0,57 | 0,72 / 0,66 | 0,67 / 0,67 | 0,67 / 0,18 / 0,04 |

Cả ba điều kiện đều chọn đúng chiều (điểm qua chính xác hơn điểm trượt) ở mọi scene (riêng w ở dev: hoà). **Ý tưởng của cổng có tín hiệu thật; chỉ có ngưỡng quá chặt so với thang dữ liệu.**

## D. Điều kiện góc θ: pháp tuyến quá nhiễu

Trong các điểm sát mặt phẳng cấu trúc (r < 5 cm), θ trung vị với k = 30 láng giềng (cấu hình hiện tại) là 24°–39°, chỉ 23–37% điểm có θ < 15°. Tính lại cho 15.000 điểm mẫu:

| Scene | θ trung vị, k = 30 | k = 100 | k = 300 |
|---|---|---|---|
| 42897599 | 29,1° | 21,9° | 16,9° |
| 42898849 | 39,4° | 33,3° | 32,5° |
| 42897566 | 32,6° | 22,9° | 16,4° |
| 45662981 | 24,2° | 14,2° | 9,8° |
| 42445022 | 39,0° | 30,4° | 25,1° |
| 42444738 | 34,5° | 23,1° | 17,9° |

θ giảm mạnh khi tăng k: **nhiễu của pháp tuyến cục bộ trên điểm d3 là nguyên nhân chính khiến chỉ ~25% điểm qua điều kiện θ**, không phải bề mặt cong. Riêng 42898849 vẫn ~32° ở k = 300 (liên quan lỗi nhãn/mặt phẳng ở mục E).

## E. Hướng "lên" và mặt phẳng

- **Hướng "lên" ước lượng chính xác**: lệch trọng lực thật (trục z của hệ scene ARKit) chỉ **0,55°–2,57°** (42897599 0,81°; 42898849 1,0°; 42897566 0,58°; 45662981 0,55°; 42445022 1,2°; 42444738 2,57°). Con số 19,6° ở `gate_result.json` của 42897566 là độ lệch giữa hướng tinh chỉnh và trung bình hướng camera, KHÔNG phải sai số: so với trọng lực thật nó chỉ lệch 0,58°. Hướng "lên" không phải nguồn lỗi.
- **Nhãn "sàn" quá rộng**: mã gán "sàn" cho mọi mặt phẳng ngang nằm dưới camera, nên mỗi scene có 4–8 "sàn" ở độ cao khác nhau, chỉ một là sàn thật:

| Scene | Số mặt phẳng sàn / tường / khác | Độ cao các "sàn" so với camera (m) |
|---|---|---|
| 42897599 | 4 / 3 / 1 | −1,37; −1,25; −0,53; −0,41 |
| 42898849 | **8 / 0 / 0** | −1,50; −1,17; −1,04; −0,78; −0,75; −0,75; −0,59; −0,50 |
| 42897566 | 6 / 1 / 1 | −1,41; −1,28; −1,12; −1,00; −0,92; −0,57 |
| 45662981 | 5 / 3 / 0 | −1,40; −0,90; −0,86; −0,82; −0,57 |
| 42445022 | 5 / 2 / 1 | −1,38; −0,82; −0,58; −0,55; −0,43 |
| 42444738 | 5 / 3 / 0 | −1,35; −1,27; −0,95; −0,68; −0,49 |

  Mặt phẳng cao hơn sàn thật 0,2–1 m có thể là mặt bàn, ghế, giường (suy luận, chưa đối chiếu từng mặt phẳng với cảnh) đang bị gắn nhãn "sàn". **42898849: cả 8 mặt phẳng đều là "sàn", không có tường**, vì RANSAC lấy tuần tự 8 mặt phẳng lớn nhất toàn là ngang. Với scene này cổng không chạm tường.
  Đây là lỗi thiết kế cần sửa trước M5 (P2Plane và plane recall cần nhãn đúng).

## F. Cổng có kéo điểm về phía Faro không? Có ở 5/6 scene (sai số tính trên các điểm đã qua cổng)

| Scene | Số điểm bị kéo | Sai số trung vị trước → sau (cm) | Tỉ lệ cải thiện / xấu đi |
|---|---|---|---|
| 42897599 | 3.683 | 2,99 → 2,57 | 73% / 27% |
| 42898849 | 1.131 | 1,65 → 1,01 | 63% / 37% |
| 42897566 | 46.568 | 1,29 → 1,17 | 72% / 28% |
| 45662981 | 17.582 | 1,40 → 1,25 | 73% / 27% |
| 42445022 | 7.603 | 1,12 → 0,77 | 75% / 25% |
| 42444738 (dev) | 5.316 | 1,71 → 2,02 | **29% / 71%** |

Cơ chế hoạt động đúng ở 5/6 scene (sai số giảm 0,1–0,6 cm). **Ở dev cổng làm xấu đi** (sai số tăng 0,3 cm): nguyên nhân chưa điều tra (nghi: `w_k` ở dev không phân biệt được và mặt phẳng/nhãn lệch). Mức cải thiện nhỏ (≤ 0,6 cm) nên khó thấy ở F-score (δ 5 cm).

## G. Nếu đổi ngưỡng (CHỈ ĐỂ XEM, không áp dụng): tỉ lệ qua cổng / độ chính xác của điểm qua (r < 5 cm, nhãn cấu trúc)

| Scene | Chính xác chung | τ_w 0,5 / τ_n 15° | τ_w 0,3 / 15° | τ_w 0,2 / 15° | τ_w 0,2 / 35° |
|---|---|---|---|---|---|
| 42897599 | 0,663 | 1,2% / 0,75 | 8,0% / 0,88 | 12,6% / 0,88 | 22,6% / 0,85 |
| 42898849 | 0,575 | 0,2% / 0,90 | 3,2% / 0,88 | 6,3% / 0,89 | 10,7% / 0,84 |
| 42897566 | 0,839 | 5,5% / 0,99 | 10,8% / 0,98 | 13,0% / 0,98 | 24,2% / 0,96 |
| 45662981 | 0,736 | 1,8% / 0,98 | 6,9% / 0,97 | 12,5% / 0,96 | 18,6% / 0,94 |
| 42445022 | 0,855 | 0,9% / 0,97 | 4,4% / 0,93 | 6,8% / 0,93 | 14,6% / 0,92 |
| 42444738 | 0,667 | 0,7% / 0,74 | 3,3% / 0,74 | 6,5% / 0,74 | 15,1% / 0,74 |

Hạ τ_w xuống 0,2–0,3 và nới θ làm tỉ lệ qua cổng tăng 3–10 lần mà điểm qua vẫn chính xác hơn mức chung ở cả 6 scene (ở dev chỉ hơn chút). Đây chỉ là gợi ý hướng; thang ngưỡng phải được chọn theo quy trình đặt trước (xem dưới), không chọn từ bảng này.

## Kết luận và đề xuất (chờ bạn duyệt)
1. Ngưỡng τ_w = 0,5 vô căn cứ trên dữ liệu thật: nằm trên ~95% `w_k`. Nguyên nhân gốc là thang đổi sai số của đề cương (τ_e = 2 px khi sai số thật ~1 px).
2. Cả ba điều kiện r, θ, w chọn đúng chiều ⇒ giữ ý tưởng cổng; chỉnh thang ngưỡng và cách tính θ.
3. θ nhiễu do pháp tuyến k = 30 trên điểm d3: cần tính pháp tuyến ổn định hơn (k lớn, hoặc dùng pháp tuyến của mặt phẳng + khoảng cách).
4. Nhãn "sàn/tường" cần sửa: sàn = mặt phẳng ngang thấp nhất; mặt ngang khác (bàn, ghế) nhãn khác; bảo đảm tìm được tường.
5. Dev: cổng làm xấu: cần điều tra riêng.
6. Chọn lại ngưỡng bằng quy trình đặt trước theo chỉ số của chính cổng (chính xác của điểm qua, sai số trước/sau, leave-one-scene-out), vì F-score không nhạy; kiểm chứng cuối bằng P2Plane và plane recall trên Replica (M5).

## H. Điều tra tiếp (dev xấu đi; mặt phẳng "sàn" cao; phép căn Faro) — chỉ đọc, không đổi pipeline

Phân tích từng mặt phẳng trên dev 42444738 và 42445022 (mã tạm, chưa vào repo): inlier mỗi mặt phẳng (r < 5 cm), khoảng cách tới Faro, tỉ lệ ô 20 cm nằm trên sàn thấp nhất.

**Dev xấu đi vì đâu.** Gần hết điểm qua cổng nằm trên sàn chính (mặt 0: 2.827/5.316 điểm). Các điểm này vốn đã sát Faro (0,89 cm) nhưng bị kéo về mặt RANSAC (độ dày 5 cm) nên thành 1,58 cm. Mặt phẳng RANSAC lệch khoảng 0,7 cm so với sàn Faro, tức không đúng hơn chính các điểm. Cải thiện chỉ xảy ra khi điểm xa mặt phẳng thật (tường 3: 7,07 → 7,45 cm vẫn xấu). Ở 42445022 sàn chính chuẩn hơn nên cổng giúp (1,12 → 0,77 cm). Biên độ chỉ ~0,3–0,7 cm, dưới δ = 5 cm của F-score.
**Sàn bị tách đôi.** Dev có mặt "sàn" cao hơn sàn thấp nhất 0,08 m với 81 nghìn điểm, trải 5,9×5,4 m (cả căn phòng), chỉ 34% inlier cách Faro ≤ 3 cm, sai số trung vị 6,7 cm. Đó là phần còn lại của sàn bị cong/nghiêng, không phải đồ vật.
**"Mặt cao hơn là bàn, ghế" chưa được ủng hộ.** Các mặt "sàn" cao 0,4–0,94 m có 35–118 nghìn inlier, trải 4,7–6,8 m mỗi chiều (lớn như cả phòng) và chỉ 31–65% ô của chúng nằm trên sàn. Mặt bàn ghế không to như vậy; đây giống mặt RANSAC dày 5 cm cắt qua nhiều điểm lẫn lộn. Chưa xem ảnh từng mặt, nên kết luận này chưa chắc chắn.
**Phép căn Faro.** `eval` và chẩn đoán dùng Kabsch cắt tỉa rồi ICP cứng. Trên dev ICP dịch thêm 17,4 cm và xoay 3,28° (42445022: 6,1 cm, 1,94°); sai số trung vị toàn cloud 3,13 cm với ICP so với 5,60 cm chỉ Kabsch. Vì ICP khớp thẳng cloud vào Faro nên các số "chính xác" tuyệt đối lạc quan. Kết luận về cổng không đổi khi bỏ ICP: dev xấu đi (12,22 → 12,63 cm), 42445022 tốt lên (2,28 → 1,90 cm).
