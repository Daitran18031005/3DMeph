# Đổi mốc scale (hướng 1) — kết quả áp dụng quy tắc

Quy tắc: `PLAN.md` (ghi trước). Mã xếp hạng: `rank_candidates.py` (chỉ đọc), số: `candidates.json`.

Scene đổi mốc (R1: mốc hiện tại < 1,8 m): **42897566** (S01, 1,17 m) và **42898849** (S07, 1,39 m). Bốn scene còn lại giữ nguyên (45662981 1,81 m; 42445022 1,84 m; 42897599 2,02 m; dev 2,41 m).

| Scene | Ứng viên (min view / min góc tia) | Xếp đầu theo R3 |
|---|---|---|
| 42897566 | S11 2,00 m (15 / 108°), S09 2,00 m (12 / 61°), S10 2,42 m (7 / 77°) | **S11** |
| 42898849 | S01 1,95 m (5 / 158°) — ứng viên duy nhất | **S01** (đạt R4 sát ngưỡng: đúng 5 view) |

Lưu ý (số ước lượng của `point_visibility`, góc tia thô):
- 42897566 S11 là "chân ghế" hai đầu: ghế là vật di chuyển được; Faro và video quay ở hai thời điểm khác nhau nên ghế có thể đã dịch. S10 (kệ dưới gương → chân tường) gồm vật cố định nhưng chỉ 7 view.
- 42898849 S01 là chiều cao cửa chính; đầu trên ở z = +0,55 m (gần trần, vùng mô hình thường thiếu điểm), chỉ 5 view.

Chưa áp dụng: `--finalize` bị chặn vì chưa có xác nhận của người dùng (R4b). Phiên chấm đã đổi vai trò (S01→test, S11→mốc; S07→test, S01→mốc) nhưng `measurements.csv`/`scale_anchor.json` vẫn là bản cũ. Bản sao: `ground_truth_truoc_doi_moc/` trong từng scene.

## Cập nhật 15/11 (sau trả lời của người dùng)
- **42897566: mốc mới = S10** (kệ dưới gương → chân tường đối diện, 2,4225 m; 7 view, góc tia ~77°). Người dùng chọn S10 và xác nhận không nằm trên vật di chuyển (R4b), bỏ qua S11 (chân ghế) và S09 theo quyết định của người dùng, không phải theo thứ tự R3. S01 (1,1745 m) thành đoạn test. `--finalize --overwrite --test-min 5` đã chạy: 1 mốc, 9 đoạn test, `scale_anchor.json` mới (chưa có phần click 2D; `proposed/alignment/scale.json` vẫn là của mốc cũ S01 đến khi click lại và chạy `align`).
- **42898849: chưa quyết** (S01, đúng 5 view, đầu trên gần trần): chờ người dùng xác nhận hoặc từ chối.

## Cập nhật 2 (15/11): đổi lại S11
Người dùng báo nhầm và chọn lại **S11** làm mốc của 42897566 (đúng thứ hạng R3 và xác nhận R4b của người dùng). S10 trở lại là đoạn test. `--finalize --overwrite` đã chạy lại: mốc S11 L_real 1,9970 m. Cảnh báo giữ nguyên: hai đầu là chân ghế (vật di chuyển được); người dùng chịu xác nhận. Bản trung gian (mốc S10) giữ ở `ground_truth/scale_anchor.mocS10_nhamlan.json`.

## Cập nhật 3 (15/11): 42898849
Người dùng xác nhận **S01** (chiều cao cửa chính, 1,949 m, 5 view) làm mốc; S07 (1,3934 m) thành đoạn test. `--finalize --overwrite --test-min 5` đã chạy. Chờ click 2D; `proposed/alignment/scale.json` vẫn của mốc cũ đến khi chạy lại `align`.
