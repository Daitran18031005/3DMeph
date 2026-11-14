# Kế hoạch đo v2 sai số chiều dài (không lạc quan do chọn lọc) — GHI TRƯỚC KHI CHẠY

Mục tiêu: báo sai số chiều dài với ĐỦ MẪU SỐ, để không bị lạc quan do chỉ tính đoạn đo được. Chỉ đo và báo; không sửa pipeline; không dùng Faro để suy scale (Faro chỉ làm đáp án và công cụ kiểm); không đụng held-out; không commit.
Mã mới: `scripts/length_error_v2.py`. Dữ liệu đầu vào cho bước 1: `kabsch/per_segment.csv`, `icp/per_segment.csv` của lần đo trước (giữ nguyên, không ghi đè). 6 scene (5 Validation, không 47204552, và dev 42444738), 46 đoạn test (đã bỏ đoạn mốc).

## Bước 1. Mẫu số đầy đủ
Với mỗi phép căn (Kabsch của `eval` là chính, Kabsch + ICP cứng là phụ), mỗi biến thể (B0, B1, B3, proposed) và bán kính snap r ∈ {2, 3, 5} cm:
- **Hợp lệ(r)**: cả hai đầu mút có điểm gần nhất ≤ r. Điểm snap là điểm gần nhất nên độ dài đo không đổi theo r; chỉ tập hợp lệ thu hẹp (suy ra được từ `nn_a_cm`, `nn_b_cm`, không cần chạy lại).
- **Đạt**: hợp lệ và sai số |đo − Faro| < 5 cm.
- Báo (a) số hợp lệ / 46 và median, MAE, MAPE, % dưới 5 cm trên đoạn hợp lệ (như cũ); (b) **tỉ lệ đạt trên cả 46 đoạn** (đoạn không hợp lệ = chưa đạt) và median khi coi đoạn không hợp lệ có sai số vô hạn (nếu hợp lệ < 50% thì median là "không xác định"); (c) cùng các số đó tách theo **độ dài Faro** (< 1 m; 1–2 m (gồm cả 1 và 2); > 2 m) và theo scene; (d) **tập chung**: chỉ các đoạn mà B0, B3, proposed CÙNG hợp lệ (ở bán kính đang xét), nêu số đoạn, median/MAE của từng biến thể trên tập đó và chênh lệch cặp (proposed − B0, proposed − B3, theo từng đoạn).
- B1 báo riêng (không vào tập chung vì hầu như không có đoạn hợp lệ).

## Bước 2. Kiểm scale độc lập với đầu mút (chỉ để kiểm)
- Với mỗi biến thể có đám điểm, mỗi scene: bắt đầu từ phép căn cứng Kabsch + ICP cứng (scale 1), rồi chạy ICP điểm–điểm CÓ cho scale thay đổi (`with_scaling = True`, cùng đám điểm đã voxel hoá theo `eval.voxel_m`, cùng bán kính ghép `eval.icp_max_dist_m`, tối đa 50 vòng, vùng Faro là vùng chấm của `eval`) → hệ số `k`: nhân đám điểm với `k` để khớp Faro. `k` > 1 nghĩa là mô hình đang nhỏ hơn Faro.
- **Tự kiểm phương pháp**: với mỗi scene, nhân đám điểm B0 với 1,03 rồi chạy đúng thủ tục trên; kỳ vọng k ≈ 1/1,03 = 0,971. Độ lệch giữa k thu được và 0,971 là độ chệch của phương pháp (ICP scale trên đám điểm phủ một phần Faro dễ chệch). Quy tắc: nếu |k_tự_kiểm − 0,971| > 0,01 thì kết quả ICP scale của scene đó ghi là "không đáng tin" (không dùng để kết luận).
- So với `s_m / s` theo quỹ đạo: ICP scale cho k_icp; nếu quỹ đạo ARKit đúng thì k_kỳ_vọng = s / s_m = 1 / (s_m/s). **Mâu thuẫn** nếu |k_icp − 1/(s_m/s)| > 0,02. Nếu cả k_icp và 1/(s_m/s) cùng lệch 1 hơn 0,01 nhưng ngược chiều thì cũng ghi mâu thuẫn. Báo thẳng, không giải thích bằng suy đoán nếu không có số.

## Bước 3. Kích thước phòng bằng khoảng cách giữa mặt phẳng song song (thử)
- Mặt phẳng lấy từ `proposed/plane_refinement/planes.json` (bản mặc định hiện tại, không sửa cổng). Cặp hợp lệ: (floor, ceiling) nếu có cả hai; (wall, wall) hai mặt có |cos giữa hai pháp tuyến| ≥ 0,985 (lệch ≤ ~10°) và cách nhau ≥ 1,0 m.
- Khoảng cách mô hình: trung bình hai chiều của khoảng cách từ tâm inlier mặt này tới mặt kia. Inlier = điểm có `plane_id` của mặt đó và `r_m < τ_r` trong `gate_log.csv`.
- Khoảng cách Faro: mặt phẳng Faro khớp (bình phương tối thiểu, bỏ dần ngoại lai) trên các điểm Faro cách mặt phẳng mô hình ≤ 8 cm (sau phép căn Kabsch + ICP) và cách một inlier của nó ≤ 0,5 m ("cùng vùng"); khoảng cách tính cùng cách. Sai số = mô hình − Faro.
- Scene nào không có đủ cặp thì ghi "không có cặp", KHÔNG sửa cổng/tham số để ép có.

## Bước 4. Kết luận
Báo sai số chiều dài trên đoạn dài (> 2 m): số đoạn, % đo được (hợp lệ ở 5 cm), median, MAE, và nêu rõ nếu mẫu quá nhỏ (< 10 đoạn) thì KHÔNG kết luận được. Nêu chỗ chưa kết luận được. Ghi thêm mục mới vào `README.md` (giữ nguyên số cũ) và `WORKING_LOG.md`.
