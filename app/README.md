# app/

**Ngoài phạm vi mốc đầu** (M6). Mốc đầu là CLI; thay thao tác chạm hai điểm trong Unity bằng
`python -m pipeline.export.measure` (xem [export](../pipeline/export/README.md)).

- `backend_fastapi/`: API nhận video, tạo job, trả tiến độ và kết quả; chạy trên RTX 4060 8 GB.
- `unity_app/`: dự án Unity thường rất nặng (binary, `Library/`) nên quản lý bằng repo Git riêng (kèm `.gitignore` chuẩn của Unity). Thư mục này chỉ
  nên chứa ghi chú tích hợp và API contract với backend.

**API contract theo đề cương (ĐC §19, Hình 23–24):** `POST /jobs` (video + metadata + mốc scale) trả `job_id`; `GET /jobs/{id}` trả trạng thái và tiến độ
(`queued → keyframe → colmap+vggt → fusion → plane → export → done`, hoặc `failed` kèm mã lỗi: quá ít keyframe, SfM không hội tụ);
`GET /jobs/{id}/result` trả `model.glb` + `measurements.json`. Unity chỉ thu video, chọn mốc scale, upload, xem GLB và đo hai điểm; **không** chạy VGGT/COLMAP
trên máy. Sơ đồ `3dmeph-architecture.html` ghi `POST /reconstruct` và Redis, khác đề cương; mặc định theo đề cương (không dùng Redis ở mốc đầu).
