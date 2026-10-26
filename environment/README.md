# environment/

Dựng và kiểm tra môi trường conda `3d_metric`.

| File | Làm gì |
|---|---|
| `baseline-requirements.txt` | ghim các gói nền của env hiện có (đo bằng `pip list` ngày 17/10/2026), không gồm torch, vggt |
| `../requirements.txt` | chỉ các gói **bổ sung** (hiện: `pytest`) |
| `create_env.bat` | tạo hoặc cập nhật env; cài torch CUDA 12.1, gói nền, gói bổ sung, `vggt` (editable, `--no-deps`); rồi chạy `check_env.py` |
| `check_env.py` | kiểm tra chỉ đọc: torch + CUDA + VRAM, thứ tự import `torch → pycolmap`, thư viện bắt buộc, `colmap.exe`, `nvidia-smi` |

## Dùng

Mở **Anaconda Prompt** ở thư mục gốc repo:

```bat
environment\create_env.bat --dry-run
environment\create_env.bat
```

- `--dry-run`: chỉ in lệnh. `--recreate`: xoá env rồi tạo lại. `--with-weights`: `check_env.py` tải trọng số `facebook/VGGT-1B` (nặng; kích thước chưa kiểm chứng).
- Nếu env `3d_metric` đã có, script bỏ qua bước tạo và chỉ cài/cập nhật gói.
- Biến `VGGT_DIR` (repo vggt, mặc định `../../vggt`) và `COLMAP_EXE` (mặc định `../../colmap/bin/colmap.exe`).
- File `.bat` chỉ dùng ký tự ASCII (tránh lỗi mã hoá của `cmd.exe`).

Kiểm tra riêng: `python environment/check_env.py` (xem README gốc, mục "Cài đặt môi trường").

## Điều cần biết

- **`import torch` phải đứng trước `pycolmap`.** Trong env hiện tại `import open3d` hoặc `import cv2` trước `pycolmap` gây "DLL load failed";
  `check_env.py` chỉ cảnh báo các thứ tự này, còn `torch → pycolmap` là bắt buộc.
- Env hiện có dùng `pycolmap 3.10.dev0` (bản dev có CUDA, không có trên PyPI). `baseline-requirements.txt` ghim `pycolmap==3.10.0` (PyPI);
  sau khi cài phải chạy lại `tests/test_colmap_compat.py` (pycolmap đọc model do COLMAP 4.2 ghi).
- `torch 2.5.1+cu121` cài từ `https://download.pytorch.org/whl/cu121`; `vggt/requirements.txt` ghim `torch==2.3.1` nên **không** cài `vggt` bằng file đó.
- GPU kiểm chứng: RTX 4060 Laptop, 8.188 MiB, driver 573.22. COLMAP CLI: 4.2.0 (có CUDA).
