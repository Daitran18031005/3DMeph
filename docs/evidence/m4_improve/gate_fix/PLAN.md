# Kế hoạch sửa cổng plane gate (M4 đợt 3d) — GHI TRƯỚC KHI CHẠY, không đổi sau khi thấy số

Mốc git trước khi sửa mã: `3100e8b` (`proposed/` hiện có giữ nguyên làm mốc so sánh). Bằng chứng đầu vào: `../gate_diagnosis/README.md` mục A–H (mục H do người dùng điều tra).

## 1. Đối chiếu đề xuất của tôi với yêu cầu của người dùng

| Việc | Đề xuất trước của tôi | Yêu cầu của người dùng + bằng chứng H | Quyết định |
|---|---|---|---|
| Nhãn sàn | sàn = mặt ngang thấp nhất, mặt ngang khác nhãn riêng | Giống (A) | Trùng, làm một lần |
| Tường | bảo đảm tìm được tường | Giống: nếu RANSAC chỉ ra mặt ngang thì thêm lượt tìm mặt đứng | Trùng. Cách thêm lượt: chọn điểm có pháp tuyến cục bộ lệch hướng "lên" ≥ 60°, RANSAC trên tập đó (thiết kế của tôi, [Suy luận]) |
| Nhãn "mặt cao là bàn/ghế" | tôi suy đoán bàn/ghế (đã ghi "chưa kiểm chứng") | Mục H: mặt cao 0,4–0,94 m trải 4,7–6,8 m, 31–65% nằm trên sàn, **không giống bàn ghế** | **Khác: rút lại suy đoán của tôi**, dùng bằng chứng H (đây là mặt RANSAC dày 5 cm cắt qua điểm lẫn lộn). Không gắn nhãn "bàn", chỉ gọi `horizontal_other` |
| Sàn bị tách đôi | không nhắc | Mục H: dev có mặt "sàn" cao hơn sàn thấp nhất 0,08 m (81 nghìn điểm) là phần sàn cong | **Thêm so với yêu cầu:** khoá `plane.floor_band_m`: mặt ngang cách mặt thấp nhất ≤ band cũng là sàn. Thử cả band = 0 (đúng nguyên văn yêu cầu) và band = 0,10 m (đặt trước, không chỉnh) |
| Pháp tuyến | k lớn hoặc dùng pháp tuyến mặt phẳng | k = 100 và 300, một yếu tố mỗi lần | Trùng (dùng k lớn). Không làm phương án "pháp tuyến mặt phẳng" |
| Khoá k | dùng chung `plane.normal_knn` | Yêu cầu: đặt `plane.normal_knn` lớn hơn | **Khác nhỏ:** `plane.normal_knn` còn được `export` dùng cho Poisson, đổi nó sẽ âm thầm đổi mesh. Thêm khoá riêng `plane.gate_normal_knn` (mặc định `null` = dùng `normal_knn`, hành vi cũ) và chỉ đổi khoá này |
| Ngưỡng τ_r, τ_n, τ_w, α | chọn lại theo leave-one-scene-out | **Không đổi đợt này** (E) | Theo yêu cầu: làm đợt sau |
| Dev xấu đi | "cần điều tra" | Mục H đã giải thích: sàn chính vốn sát Faro (0,89 cm) bị kéo về mặt RANSAC lệch ~0,7 cm | Chấp nhận giải thích; không cố "sửa" dev |

## 2. Các biến thể (một yếu tố mỗi lần, so với `gate_base` = cấu hình cũ chạy lại bằng đúng script này)

Fusion không đổi (dùng `proposed/fusion` hiện có); chỉ `gate` chạy lại, kết quả ghi vào `proposed/variants/<tên>/plane_refinement/` (không đụng `proposed/`).

| Tên | Thay đổi | Khoá |
|---|---|---|
| `gate_base` | không (kiểm script tái lập đúng số `proposed`) | — |
| `gate_A` | nhãn: sàn chỉ là mặt ngang thấp nhất (band 0), trần là mặt ngang cao nhất; mặt ngang khác `horizontal_other`; đảm bảo ≥ 1 tường | `plane.floor_rule=lowest`, `plane.floor_band_m=0`, `plane.min_walls=1`, `plane.extra_wall_passes=4` |
| `gate_Ab` | như `gate_A` nhưng band 0,10 m | `plane.floor_band_m=0.10` |
| `gate_B100` | pháp tuyến 100 láng giềng (nhãn cũ) | `plane.gate_normal_knn=100` |
| `gate_B300` | pháp tuyến 300 láng giềng (nhãn cũ) | `plane.gate_normal_knn=300` |
| `gate_AB` (chỉ khi cả A và B đạt) | tổ hợp của A (bản đạt, ưu tiên band 0) và B (k nhỏ nhất đạt) | cả hai |

Cả 6 scene: 42897599, 42898849, 42897566, 45662981, 42445022, 42444738 (dev). Không held-out, không Replica.

## 3. Chỉ số (mỗi biến thể × scene)
Số mặt phẳng theo nhãn; **tỉ lệ điểm qua cổng**; tỉ lệ điểm đạt riêng điều kiện θ; **độ chính xác của điểm qua** (tỉ lệ cách Faro ≤ 5 cm; căn Kabsch cắt tỉa + ICP tính MỘT lần trên cloud chưa qua cổng, dùng chung cho mọi biến thể);
**sai số trung vị của điểm bị kéo, trước → sau**, tỉ lệ cải thiện; **F-score, Chamfer, precision, recall** của cloud sau cổng (đúng đường `eval`).

## 4. Quy tắc nhận (ĐẶT TRƯỚC)
Mọi so sánh là trung bình 6 scene so với `gate_base`, trừ khi ghi khác.

**Nhãn (A và Ab) được nhận khi ĐỒNG THỜI:**
- A1. Cả 6 scene có ≥ 1 tường, và mọi mặt nhãn "floor" cách mặt thấp nhất ≤ band (không còn "sàn" ở độ cao khác).
- A2. Độ chính xác của điểm qua cổng (≤ 5 cm) không thấp hơn `gate_base` quá 0,02.
- A3. Số scene có sai số trung vị của điểm bị kéo giảm (sau < trước) không ít hơn `gate_base`; và tỉ lệ cải thiện trung bình không thấp hơn quá 0,02.
- A4. ΔF trung bình ≥ −0,005; Chamfer trung bình không tệ hơn quá +2% tương đối; không scene nào ΔF < −0,010.
Nếu `gate_A` và `gate_Ab` cùng đạt thì chọn `gate_A` (đơn giản hơn, đúng yêu cầu); nếu chỉ `gate_Ab` đạt thì chọn `gate_Ab`.

**Pháp tuyến (B100, B300) được nhận khi ĐỒNG THỜI** (xét từng k; nếu cả hai đạt thì chọn k nhỏ hơn):
- B1. Tỉ lệ điểm đạt điều kiện θ (θ < τ_n) trung bình ≥ 1,5 × `gate_base`.
- B2. Độ chính xác của điểm qua cổng không thấp hơn `gate_base` quá 0,02.
- B3. Số scene có sai số trung vị điểm bị kéo giảm không ít hơn `gate_base`.
- B4. Như A4 (ΔF, Chamfer, không scene nào ΔF < −0,010).

**Tổ hợp `gate_AB`:** chỉ chạy nếu A và B cùng đạt, chạy MỘT lần; nhận nếu A2–A4 và B2–B4 đều giữ (không tệ hơn `gate_base` theo cùng các ngưỡng).

**Không đạt:** giữ cấu hình cũ (không đổi `configs/default.yaml` mặc định), báo số thật. Nếu đạt: đề xuất đổi mặc định và nêu `proposed/` hiện có sẽ cũ cho tới khi chạy lại; không đổi τ_r, τ_n, τ_w, α.

Giới hạn đã biết: F-score ở δ = 5 cm không nhạy với cổng (độ dịch tối đa 2,5 cm), nên A4/B4 chỉ là "không hại"; bằng chứng về lợi ích của cổng chỉ chắc chắn khi có P2Plane và plane recall trên Replica (M5).
