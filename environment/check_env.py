#!/usr/bin/env python3
"""
check_env.py — Kiểm tra môi trường chạy 3DMeph (chỉ đọc, không cài gì).

Cách chạy (trong env `3d_metric`):
    python environment/check_env.py [--with-weights]

Kiểm tra:
  1. Python, torch + CUDA, VRAM trống.
  2. THỨ TỰ IMPORT: `import torch` rồi `import pycolmap` PHẢI chạy được. Trong env hiện tại,
     `import open3d` hoặc `import cv2` TRƯỚC pycolmap gây lỗi "DLL load failed" (đã kiểm chứng
     ngày 17/10/2026), nên script chỉ cảnh báo các thứ tự này, không coi là lỗi.
  3. Các thư viện bắt buộc: numpy, scipy, cv2, open3d, trimesh, yaml, pandas.
  4. colmap.exe (biến COLMAP_EXE; mặc định ../colmap/bin/colmap.exe so với repo).
  5. nvidia-smi.
  6. Gói vggt (cảnh báo nếu chưa cài).

--with-weights: tải trọng số facebook/VGGT-1B từ Hugging Face (kích thước chưa kiểm chứng,
chỉ chạy khi bạn chủ động truyền cờ này).

Mã thoát: 0 nếu mọi mục BẮT BUỘC đạt, 1 nếu có lỗi.
"""

import argparse
import importlib
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_COLMAP = REPO.parent / "colmap" / "bin" / "colmap.exe"

errors = []
warnings = []


def ok(msg):
    print(f"[ OK ] {msg}")


def warn(msg):
    warnings.append(msg)
    print(f"[WARN] {msg}")


def fail(msg):
    errors.append(msg)
    print(f"[FAIL] {msg}")


def check_python():
    print(f"Python {platform.python_version()} ({platform.platform()})")
    if sys.version_info[:2] != (3, 12):
        warn("Env chuẩn dùng Python 3.12; phiên bản khác chưa được kiểm chứng")


def check_torch():
    try:
        import torch  # noqa: F401  (phải import trước pycolmap)
    except Exception as e:  # noqa: BLE001
        fail(f"import torch lỗi: {e!r}")
        return None
    import torch
    ok(f"torch {torch.__version__}")
    if not torch.cuda.is_available():
        fail("torch.cuda.is_available() = False (cần torch bản CUDA, xem create_env.bat)")
        return torch
    name = torch.cuda.get_device_name(0)
    free, total = torch.cuda.mem_get_info(0)
    ok(f"CUDA OK: {name}, VRAM trống {free / 2**20:.0f} / {total / 2**20:.0f} MiB")
    if total / 2**30 < 7.5:
        warn("VRAM dưới 8 GB; ngân sách VGGT chunk có thể phải giảm (vggt.chunk)")
    return torch


def run_import_order(order):
    code = "; ".join(f"import {m}" for m in order)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    return r.returncode == 0, (r.stderr.strip().splitlines() or [""])[-1]


def check_import_order():
    good, err = run_import_order(["torch", "pycolmap"])
    if good:
        ok("import torch → pycolmap chạy được")
        import_ok = True
    else:
        fail(f"import torch → pycolmap lỗi: {err}")
        import_ok = False
    for first in ("open3d", "cv2"):
        good, err = run_import_order([first, "pycolmap"])
        if good:
            ok(f"import {first} → pycolmap chạy được")
        else:
            warn(f"import {first} → pycolmap lỗi ({err}). Đã biết: luôn `import torch` trước "
                 f"(pipeline/__init__.py làm việc này)")
    return import_ok


def check_libs():
    for mod in ("numpy", "scipy", "cv2", "open3d", "trimesh", "yaml", "pandas"):
        try:
            m = importlib.import_module(mod)
            ok(f"{mod} {getattr(m, '__version__', '')}".strip())
        except Exception as e:  # noqa: BLE001
            fail(f"import {mod} lỗi: {e!r}")
    try:
        import pycolmap
        ok(f"pycolmap {pycolmap.__version__} (has_cuda={getattr(pycolmap, 'has_cuda', '?')})")
    except Exception as e:  # noqa: BLE001
        fail(f"import pycolmap lỗi: {e!r}")
    try:
        import vggt  # noqa: F401
        ok("vggt import được")
    except Exception as e:  # noqa: BLE001
        warn(f"chưa import được vggt ({e!r}); cài bằng create_env.bat hoặc `pip install -e <vggt> --no-deps`")


def check_colmap():
    exe = Path(os.environ.get("COLMAP_EXE", DEFAULT_COLMAP))
    if not exe.is_file():
        fail(f"không thấy colmap.exe tại {exe} (đặt biến COLMAP_EXE)")
        return
    r = subprocess.run([str(exe), "-h"], capture_output=True, text=True)
    text = (r.stdout or "") + (r.stderr or "")
    m = re.search(r"COLMAP\s+(\d+\.\d+\.\d+)[^\n]*", text)
    if not m:
        fail(f"chạy {exe} -h nhưng không đọc được phiên bản")
        return
    ok(f"colmap.exe: {m.group(0).strip()}")
    if "CUDA" not in m.group(0):
        warn("COLMAP không có CUDA; patch_match_stereo (MVS) cần CUDA")


def check_nvidia_smi():
    exe = shutil.which("nvidia-smi")
    if not exe:
        fail("không thấy nvidia-smi trong PATH")
        return
    r = subprocess.run([exe, "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
                       capture_output=True, text=True)
    ok(f"nvidia-smi: {r.stdout.strip()}")


def download_weights():
    from huggingface_hub import snapshot_download
    print("Tải facebook/VGGT-1B từ Hugging Face (cờ --with-weights)...")
    path = snapshot_download("facebook/VGGT-1B")
    ok(f"trọng số VGGT-1B tại {path}")


def main():
    # Console Windows (cp1252) không in được tiếng Việt có dấu nếu không ép UTF-8
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Kiểm tra môi trường 3DMeph (chỉ đọc)")
    ap.add_argument("--with-weights", action="store_true", help="tải trọng số VGGT-1B (nặng)")
    args = ap.parse_args()

    check_python()
    check_torch()
    check_import_order()
    check_libs()
    check_colmap()
    check_nvidia_smi()
    if args.with_weights:
        try:
            download_weights()
        except Exception as e:  # noqa: BLE001
            fail(f"tải trọng số lỗi: {e!r}")

    print()
    print(f"Tổng kết: {len(errors)} lỗi, {len(warnings)} cảnh báo")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
