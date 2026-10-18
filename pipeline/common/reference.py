"""Đo V_ref và G_ref trên vga_wide của các scene Validation (kế hoạch §4.1; ĐC §10.3, §16.1).

  V_ref = trung vị (qua scene) của "blur trung bình mỗi scene", blur = phương sai Laplacian của ảnh xám  (3)
  G_ref = trung vị (qua scene) của "gradient cửa sổ 15×15 trung bình mỗi scene"                           (20)
Mỗi scene lấy mẫu mỗi `stride` khung (mặc định 10, như EDA). Ảnh không cần xoay: cả hai số đo bất biến khi xoay 90°.

Quy tắc dữ liệu: danh sách scene lấy từ splits.csv đã khoá; `guard_reference` chạy TRƯỚC khi đọc ảnh nên scene held-out
bị chặn ngay (HeldoutError), scene train cũng bị từ chối (chỉ val).
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np

from . import splits as sp
from .quality import compute_g_ref, compute_v_ref, laplacian_variance, mean_window_gradient

DEFAULT_STRIDE = 10
DEFAULT_ASSET = "vga_wide"
DEFAULT_WINDOW = 15


def list_png_entries(zf: zipfile.ZipFile) -> List[str]:
    """Các ảnh PNG trong zip, sắp theo tên (tên chứa timestamp nên cũng là thứ tự thời gian)."""
    return sorted(n for n in zf.namelist() if n.lower().endswith(".png"))


def scene_stats(zip_path, stride: int = DEFAULT_STRIDE, window: int = DEFAULT_WINDOW) -> Dict[str, float]:
    """Thống kê một scene từ zip ảnh: lấy khung thứ 0, stride, 2·stride, … rồi tính blur và gradient từng khung."""
    import cv2  # import muộn: gói `pipeline` đã import torch trước

    if stride < 1:
        raise ValueError("stride phải ≥ 1")
    blur: List[float] = []
    grad: List[float] = []
    with zipfile.ZipFile(zip_path) as zf:
        names = list_png_entries(zf)
        if not names:
            raise ValueError(f"không có ảnh PNG trong {zip_path}")
        picked = names[::stride]
        for n in picked:
            img = cv2.imdecode(np.frombuffer(zf.read(n), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise ValueError(f"không giải mã được {n} trong {zip_path}")
            blur.append(laplacian_variance(img))
            grad.append(mean_window_gradient(img, window))
    return {
        "n_frames": len(names), "n_sampled": len(picked),
        "blur_mean": float(np.mean(blur)), "blur_median": float(np.median(blur)), "blur_min": float(np.min(blur)),
        "grad_mean": float(np.mean(grad)), "grad_median": float(np.median(grad)), "grad_min": float(np.min(grad)),
    }


def measure_reference(root, splits_csv, scene_ids: Optional[Iterable[str]] = None, stride: int = DEFAULT_STRIDE,
                      window: int = DEFAULT_WINDOW, asset: str = DEFAULT_ASSET) -> Dict[str, object]:
    """Đo V_ref, G_ref. root = thư mục gốc repo (source_dir trong splits.csv tính từ đây).

    scene_ids mặc định là mọi scene `val` trong splits.csv. Truyền scene khác (held-out, train) sẽ bị từ chối trước khi đọc ảnh.
    """
    splits = sp.load_splits(splits_csv)                     # LockError nếu splits.csv bị sửa sau khi khoá
    rows = {r["video_id"]: r for r in sp.read_rows(splits_csv)}
    ids = [str(v) for v in (scene_ids if scene_ids is not None else (v for v, s in splits.items() if s == sp.SPLIT_VAL))]
    ids = sorted(ids, key=int)
    sp.guard_reference(ids, splits)                          # HeldoutError/ValueError ngay, chưa đọc ảnh nào
    per_scene = {}
    for v in ids:
        per_scene[v] = scene_stats(Path(root) / rows[v]["source_dir"] / f"{asset}.zip", stride, window)
        per_scene[v]["visit_id"] = rows[v]["visit_id"]
    v_ref = compute_v_ref({v: s["blur_mean"] for v, s in per_scene.items()}, splits)
    g_ref = compute_g_ref({v: s["grad_mean"] for v, s in per_scene.items()}, splits)
    return {"per_scene": per_scene, "v_ref": v_ref, "g_ref": g_ref, "n_scenes": len(ids),
            "stride": stride, "window": window, "asset": asset}
