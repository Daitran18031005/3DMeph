# data/

- raw/arkitscenes/  : dữ liệu thô ARKitScenes (Training/Validation), 30-40 scene Faro subset.
  Khuyến nghị: nếu lưu chính trên Google Drive, đặt đây là symlink hoặc chỉ giữ bản
  giải nén tạm thời khi cần chạy pipeline, xoá sau khi dùng xong.
- raw/replica/       : 18 scene Replica (held-out test set, KHÔNG dùng để train).
- self_collected/    : 6-8 phòng tự quay bằng smartphone (cross-domain test set), thêm sau.
- processed/         : cache output sau khi adapters.py chuẩn hoá (rgb/depth/pose/mesh
  theo interface chung), nếu cần tránh xử lý lại từ raw mỗi lần.
- selected_scenes.csv : danh sách video_id ARKitScenes đã lọc từ upsampling_train_val_splits.csv
