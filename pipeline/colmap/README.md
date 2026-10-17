# pipeline/colmap/

Trạng thái (M0a): chưa có mã stage; đã kiểm chứng pycolmap 3.10 đọc được model do COLMAP CLI 4.2 ghi và công thức
`e_reproj` theo quan sát khớp COLMAP (`tests/test_colmap_compat.py`). Stage SfM, MVS, tín hiệu: M1.

## Vai trò

Các node **COLMAP SfM**, **COLMAP MVS**, **SfM Output** của dataflow. Là baseline B0 và là nguồn của hai tín hiệu hình
học `e_reproj` (thưa, theo điểm feature) và `σ_depth` (dày, theo pixel) cho fusion (ĐC §14).
**Hoàn toàn tách biệt với VGGT** (`demo_colmap.py` của VGGT chỉ là lớp tương thích dữ liệu, không phải phương pháp này).

## Input/Output

| | Đường dẫn (trong thư mục scene) | Nội dung | Đơn vị |
|---|---|---|---|
| vào | `frames/keyframes/`, `metadata/camera.json` | keyframe và intrinsics | px |
| ra | `baselines/colmap/sfm/sparse/0/{cameras,images,points3D}.bin` | camera, pose, điểm 3D thưa | đv COLMAP |
| ra | `baselines/colmap/sfm/observations.npz`: `image_id, point3d_id, xy, e_reproj` | sai số chiếu lại **theo từng quan sát (i, điểm)** | px |
| ra | `baselines/colmap/mvs/` (depth photometric và geometric, `fused.ply`, `fused.ply.vis`) | MVS dày và visibility | đv COLMAP |
| ra | `baselines/colmap/sfm/e_reproj_map/<view>.npy` | `e_reproj` nội suy từ thưa sang dày | px |
| ra | `baselines/colmap/mvs/sigma_depth/<view>.npy` | `σ_depth = abs(d_photo − d_geom)` | **đv COLMAP** (nhân `s_m` thành mét trước khi vào (19)) |
| ra | `baselines/colmap/metric/` | baseline B0: `fused.ply × s_m` | m |

## Công thức

- RANSAC loại match sai (9); phép chiếu `λx = K[R|t]X` (10); Bundle Adjustment (11); PatchMatch MVS và nhất quán hình học (12).
- `e_reproj = ‖π(R X + t) − x‖` tính **theo từng quan sát**; COLMAP không xuất sẵn bản đồ (ĐC §14.4). Ví dụ: dự đoán (812,0; 440,0)
  so với quan sát (809,9; 441,2) cho 2,42 px.
- `σ_depth` dùng chênh lệch depth photometric và geometric làm proxy (ĐC §14.4). `e_reproj` thưa nên phải **tự nội suy**
  sang dày (IDW hoặc Delaunay có bán kính cắt; phương pháp là suy luận của nhóm).
- Lệnh COLMAP (CLI, subprocess): `feature_extractor` → `sequential_matcher` → `mapper`; rồi `image_undistorter` →
  `patch_match_stereo` (`geom_consistency=true`) → `stereo_fusion` (ĐC Hình 15).

## Tham số

| Khoá | Giá trị | Nguồn |
|---|---|---|
| `colmap.camera_model` | PINHOLE | intrinsics lấy từ `camera.json` |
| `colmap.matcher_overlap` | null | chưa có căn cứ (dùng mặc định của COLMAP) |
| `colmap.geom_consistency` | true | tạo cả depth photometric và geometric (cần cho `σ_depth`) |
| `colmap.max_image_size` | null | null = giữ nguyên kích thước ảnh |

Đường dẫn `colmap.exe`: `paths.colmap_exe` (biến `COLMAP_EXE`), mặc định `../colmap/bin/colmap.exe` so với repo.
`patch_match_stereo` cần CUDA.

## Cách chạy riêng

```bash
# skip (chưa có CLI, dự kiến M1; cần colmap.exe và GPU)
python -m pipeline.colmap --scene arkitscenes/42444738 --stage sfm
```

## Test vector và tiêu chí đạt

- `tests/test_colmap_compat.py` (bỏ qua nếu thiếu `data/processed/images/sparse`): trên 2.377 điểm / 121 ảnh, trung vị
  |Δ| giữa `e_reproj` theo quan sát (trung bình mỗi điểm) và `point3D.error` của COLMAP là 0,0008 px, tương quan 0,99996.
- `tests/test_geometry.py`: phép chiếu K=500, 320, 240, X=(0,40; −0,20; 2,00) cho (420; 190) px; sai số 2,42 px.
- Tiêu chí đạt (M1–M2): ≥ 90% keyframe đăng ký được (suy luận, chưa có căn cứ trong đề cương); mã lỗi `E_SFM_FAILED` khi
  SfM không hội tụ (ĐC Hình 24).

## Lỗi thường gặp

- `import cv2` hoặc `open3d` trước `pycolmap` gây "DLL load failed": luôn `import pipeline` (có `import torch` trước).
- Ảnh 256×192 quá nhỏ: lần chạy cũ ở `data/processed` chỉ ra 2.377 điểm 3D từ 121 ảnh; dùng `vga_wide` 640×480 cho kết quả.
- Quên đổi `σ_depth` sang mét trước khi dùng `τ_σ = 0,20 m`.
- COLMAP 4.2 (CLI) và pycolmap 3.10 (đọc): đọc xuôi đã kiểm chứng; chưa thử pycolmap ghi rồi CLI đọc, nên mọi bước
  ghi đều dùng CLI.

## Người phụ trách

@username1 (theo `.github/CODEOWNERS`).
