# app/

- backend_fastapi/ : API nhận video, gọi pipeline, trả mesh/kết quả đo, chạy trên RTX 4060 8GB.
- unity_app/        : LƯU Ý — dự án Unity thường rất nặng (binary, Library/) và nên được
  quản lý bằng repo Git riêng (kèm .gitignore chuẩn của Unity). Thư mục này chỉ nên chứa
  ghi chú tích hợp/API contract với backend, không nhất thiết chứa toàn bộ project Unity.
