# Quy tắc chọn lại mốc scale — GHI TRƯỚC KHI TÍNH

Lý do: sai số mốc tương đối = √2 × 1 cm / L_real (0,6–1,2%), mốc ngắn 1,2–1,4 m có thể ăn 5–6 cm trên đoạn 5 m (`../length_error_buoc1/README.md`, bước 3). Người dùng đã duyệt (15/11): đổi mốc theo hướng 1, khoảng **1,8 m ≤ L_real ≤ 2,5 m**.

## Quy tắc (cố định, không xét sai số mô hình)
- **R1.** Chỉ đổi mốc ở scene có mốc hiện tại L_real < 1,8 m. Mốc ≥ 1,8 m (ở 2,5 m trở xuống) giữ nguyên.
- **R2.** Ứng viên: đoạn hiện có của scene (đang là `test`) với 1,8 ≤ L_real ≤ 2,5 m.
- **R3.** Chọn ứng viên theo độ nhìn thấy của hai đầu mút bằng `point_visibility` (cùng hàm `annotate_segments --visibility`, trên `faro_display_rgb.ply`, keyframe của scene): điểm = min(số view đầu a, số view đầu b); lớn nhất thắng; chênh ≤ 1 view thì lấy min góc tia lớn hơn; hoà nữa thì đoạn dài hơn. KHÔNG dùng sai số của mô hình, `nn_cm` hay kết quả đo nào.
- **R4.** Điều kiện tối thiểu: min view ≥ 5 và min góc tia ≥ 15° (`VIS_MID`). Nếu ứng viên tốt nhất không đạt thì KHÔNG tự nới: báo người dùng quyết.
- **R5.** Mốc cũ chuyển thành đoạn test (độ dài Faro vẫn là đáp án); mốc mới bị loại khỏi test.
- **R6.** Mốc mới phải click 2D lại (`click_anchor_2d.py`, ≥ 2 view mỗi đầu mút). Báo tâm chiếu và góc tia; không có ngưỡng tự loại, người dùng đọc số.
- **R7.** Sau khi đổi: chạy lại align → … → eval cho scene đổi mốc, rồi `length_error.py`/`length_error_v2.py`. Không đổi mốc lần hai sau khi thấy kết quả. Báo kết quả mốc mới cạnh mốc cũ.
- Không dùng Faro để suy scale, không đụng held-out, không commit.

## Bổ sung R4b (ghi SAU khi thấy bảng xếp hạng, không đổi thứ tự xếp hạng)
Mốc phải được người dùng xác nhận "không nằm trên gương/kính/vật di chuyển được" (`annotate_segments` bắt buộc, `confirmed_not_on_glass_or_moving`). Tôi KHÔNG tự xác nhận thay. Nếu người dùng không xác nhận ứng viên xếp đầu thì xét ứng viên kế tiếp theo đúng thứ tự R3.
