"""Đọc và ghi depth map nhị phân của COLMAP (`*.photometric.bin`, `*.geometric.bin`).

Định dạng: tiêu đề ASCII `width&height&channels&` rồi mảng float32 lưu theo thứ tự cột (Fortran) với trục (width, height, channels).
Đơn vị depth: đơn vị COLMAP (chưa mét).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def read_depth_map(path) -> np.ndarray:
    """Trả về mảng (H, W) float32 (hoặc (H, W, C) nếu nhiều kênh). Giá trị ≤ 0 là điểm không có depth."""
    with open(path, "rb") as f:
        data = f.read()
    pos, ends = 0, []
    while len(ends) < 3:
        i = data.find(b"&", pos)
        if i < 0:
            raise ValueError(f"{path}: tiêu đề depth map không đủ 3 dấu '&'")
        ends.append(i)
        pos = i + 1
    width, height, channels = (int(x) for x in data[: ends[2]].decode("ascii").split("&"))
    arr = np.frombuffer(data[ends[2] + 1:], dtype="<f4")
    if arr.size != width * height * channels:
        raise ValueError(f"{path}: {arr.size} giá trị float, cần {width}×{height}×{channels}")
    arr = arr.reshape((width, height, channels), order="F")
    return np.transpose(arr, (1, 0, 2)).squeeze().astype(np.float32)


def write_depth_map(path, depth: np.ndarray) -> None:
    """Ghi theo định dạng COLMAP (dùng cho test và dữ liệu tổng hợp)."""
    d = np.asarray(depth, dtype=np.float32)
    if d.ndim == 2:
        d = d[:, :, None]
    h, w, c = d.shape
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(f"{w}&{h}&{c}&".encode("ascii"))
        f.write(np.transpose(d, (1, 0, 2)).astype("<f4").tobytes(order="F"))
