# Khảo sát khả thi Replica cho M5 (13/11/2026) — chỉ khảo sát, KHÔNG tải dữ liệu, KHÔNG cài gói vào môi trường nào

Vì sao cần Replica: chỉ số mặt phẳng (P2Plane, plane recall) và kiểm tra plane gate chỉ chấm được trên Replica (ĐC Hình 4, §11, §17, công thức (36)); ARKitScenes không có nhãn phẳng.
Môi trường máy: Windows 11, GPU RTX 4060 Laptop (driver 573.22), ổ D còn ~26 GB, ổ C còn ~19 GB, conda 26.1.1, Visual Studio 18 Community có MSVC 14.51 và CMake.

## 1. Đã có trên đĩa (`data/raw/replica`, 18 scene, 40 GB)
apartment_0–2, frl_apartment_0–5, hotel_0, office_0–4, room_0–2 (13 không gian). Mỗi scene chỉ có **`mesh.ply`** (18–192 MB; room_0: 954.492 đỉnh có màu đỉnh, 953.647 mặt **tứ giác**) và
**`textures/`** (5–32 file `*-color-ptex.hdr` + `parameters.json`; **không có `.w`**).

## 2. Còn thiếu (so với README của Replica-Dataset)
Cả 18 scene thiếu: `glass.sur` (kính/gương), `preseg.bin` + `preseg.json` (phân đoạn phẳng/không phẳng = **GT mặt phẳng**), `semantic.bin` + `semantic.json`,
và thư mục `habitat/` (`mesh_semantic.ply`, `mesh_preseg_semantic.ply`, `info_*.json`, `*.navmesh`, `replica_stage.stage_config.json`, `sorted_faces.bin`). Kiểm bằng `find`: không file nào có trên đĩa.

## 3. Phương án render — kết quả thử thật
| Phương án | Thử | Kết quả | Rủi ro / chi phí |
|---|---|---|---|
| **a. Habitat-Sim trên Windows** | `pip index versions habitat-sim`; `pip download habitat-sim --platform win_amd64`; `conda search -c aihabitat -c conda-forge habitat-sim --platform win-64`; `conda create -n habprobe_dryrun --dry-run -c aihabitat -c conda-forge python=3.9 habitat-sim` | **Bị chặn.** PyPI không có bản nào cho Windows; kênh `aihabitat` win-64 chỉ có gói rỗng `habitat-sim-mutex`, còn bản thật (0.3.3 py3.9) chỉ cho linux-64 và osx-arm64; bước dry-run báo không tìm thấy gói (không tạo môi trường nào) | Muốn có phải tự build từ nguồn trên Windows (không được hỗ trợ chính thức). Không thử build |
| **b. ReplicaSDK** (`Download/Replica/Replica-Dataset/ReplicaSDK`) | đọc `README.md`, `build.sh`, `CMakeLists.txt`, mã nguồn; kiểm công cụ | **Chưa build, ước lượng khó.** `3rdparty/Pangolin` và `3rdparty/eigen` **rỗng** (submodule chưa tải); `build.sh` và `CMakeLists.txt` viết cho Linux (`libpangolin.so`, `make`, thư viện `dl`, `GLEW`); `render.cpp` dùng `EGL.h` (EGL headless) và ba file (`ptex/EGL.cpp`, `ptex/PLYParser.cpp`, `ptex/PTexLib.cpp`) khớp mẫu include kiểu POSIX/EGL (`unistd.h|dlfcn|EGL/egl|pthread|sys/`, chưa đọc kỹ từng dòng). Có MSVC và CMake nhưng không có Pangolin: conda-forge chỉ có `pangolin-opengl` 0.9.x (API mới, khác bản SDK nhắm tới) và `glew` | Phải tải Pangolin/Eigen, vá mã Linux-only, xử lý EGL trên Windows: ước giờ–ngày, kết quả chưa chắc. Mô hình ptex HDR thì cho ảnh đẹp nhất |
| **c. WSL2** | `wsl --status`, `wsl -l -v` | WSL2 có (mặc định v2) nhưng **chỉ có distro `docker-desktop` (đang dừng)**, chưa có Ubuntu | Cần cài Ubuntu (nhiều GB, mặc định nằm ổ C chỉ còn ~19 GB), driver GPU trong WSL, rồi `conda install -c aihabitat habitat-sim` (có bản linux-64 headless). Đổi hệ thống máy: cần bạn đồng ý. Habitat-Sim đòi cả `habitat/` (xem mục 4) |
| **d. Ray casting CPU của Open3D (thêm, ngoài ba phương án bạn nêu)** | `probe_raycast.py` trên `room_0/mesh.ply` | **Chạy được ngay trong env hiện tại, không cài thêm.** Ảnh 640×480 màu + độ sâu chính xác trong 0,01–0,6 s/khung (CPU), trúng 100% pixel, ảnh thật (`room0_raycast_probe.png`: sofa, rèm, sàn nhận ra rõ; ảnh lật vì quy ước `up` của thử, sửa được). Lưu ý: Open3D **không đọc được** PLY tứ giác này ("polygon could not be decomposed", chỉ đọc được 16.516/1,9 triệu tam giác) nên dùng `trimesh` tam giác hoá (1.907.294 mặt) | Chỉ dùng **màu đỉnh** (độ phân giải thấp hơn ptex HDR), không xử lý kính/gương (thiếu `glass.sur`), không có ánh sáng/phản chiếu. **Chưa kiểm** COLMAP/VGGT có đăng ký được ảnh render kiểu này không. Cần tự thiết kế quỹ đạo camera (đĩa không có quỹ đạo) |

**Đề xuất:** làm M5 bằng **phương án d** (Open3D ray casting, Windows, không cài gì), nhưng trước hết chạy một thử nhỏ end-to-end trên một scene (vd. `room_0`): quỹ đạo ~100 khung → `pipeline.run` đến `eval`, để biết SfM có đăng ký ảnh vertex-colour hay không. Habitat-Sim (a) bị chặn trên Windows; ReplicaSDK (b) và WSL2 (c) là dự phòng đắt.

## 4. Nhãn thiếu có tải được không (chỉ HEAD, không tải)
- Nguồn chính thức: một file **`replica_v1_0.tar.gz` chia 17 phần** (`.partaa` … `.partaq`) ở `github.com/facebookresearch/Replica-Dataset/releases/download/v1.0/`; HEAD cho 16 phần × 2.000.000.000 B và phần cuối 1.859.047.808 B, **tổng 33.859.047.808 B ≈ 31,5 GiB (33,9 GB)**. Đây là **một kho nén duy nhất, không tải riêng từng nhãn hay từng scene được**.
- Ổ D còn ~26 GB < 33,9 GB nên **không lưu nổi các phần**. Cách khả thi: **tải dạng dòng và giải nén lọc ngay** (tải tuần tự từng phần, `cat` qua `tar -xz --wildcards` chỉ lấy `*/preseg*`, `*/semantic*`, `*/glass.sur`, `*/habitat/*` rồi bỏ phần còn lại), tốn băng thông ~33,9 GB nhưng đĩa chỉ cần cỡ nhãn (chưa đo, chưa có số). `tar` GNU 1.35 có sẵn.
- Ngoài ra `http://dl.fbaipublicfiles.com/habitat/Replica/additional_habitat_configs.zip` (HEAD 200, **40.793.904 B ≈ 40,8 MB**): cấu hình bổ sung cho Habitat (nội dung chưa mở).
- Theo AGENTS §7 mọi tải này cần bạn chấp thuận riêng; chưa thực hiện.

## 5. Chưa kiểm chứng
Nội dung và dung lượng thật của các file nhãn; `additional_habitat_configs.zip` chứa gì; ảnh render vertex-colour có dùng được cho COLMAP/VGGT không; ReplicaSDK có build được không (chưa thử build, chỉ đọc mã); WSL2 + Habitat-Sim headless có chạy không (chưa cài).
