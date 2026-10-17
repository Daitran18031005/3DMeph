# reports/

- `statistics/validation_report.csv`, `statistics/eda_stats.csv`: đầu ra của `scripts/validate_dataset.py` và `scripts/explore_dataset.py`
  (tên thư mục trước đây gõ nhầm là `stastitic`, đã đổi thành `statistics`). EDA đo trên `lowres_wide` 256×192.
- `figures/`: hình minh hoạ dùng lại cho chương Dataset và slide bảo vệ.

**Chính sách commit chưa chốt:** thư mục `reports/` đang nằm trong `.gitignore`, nhưng README này từng nói commit CSV. Hiện các CSV **không**
được commit; cần nhóm quyết định (ví dụ bỏ `reports/` khỏi `.gitignore` chỉ cho các CSV nhỏ).

Số liệu trong CSV được đối chiếu lại với đề cương: 9 scene có `blur_min < 10` (đề cương ghi 8); trung vị `blur_mean` của 40 scene là 581
(số cũ, không dùng làm cấu hình, xem `configs/README.md`).
