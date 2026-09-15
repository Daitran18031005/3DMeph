# scripts/

Các script chuẩn bị dữ liệu (chạy 1 lần hoặc theo batch):
- download_arkitscenes.py, download_replica.sh : tải dữ liệu thô
- validate_dataset.py   : kiểm tra toàn vẹn/format trước khi dùng
- explore_dataset.py    : EDA — blur/exposure/depth/mesh stats, feed tham số cho q^blur, q^exposure
- adapters.py           : ARKitScenesAdapter / ReplicaAdapter — interface chung
  (get_rgb_frames, get_depth_gt, get_poses, get_intrinsics, get_mesh_gt) cho downstream pipeline
