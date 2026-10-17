"""Chia keyframe thành chunk cho VGGT. ĐC §7.1, công thức (2).

N_chunk = ⌈(N_kf − o) / (c − o)⌉, c = số ảnh mỗi chunk (8–16 trên GPU 8 GB), o = số ảnh gối (o = 2).
"""

from __future__ import annotations

import math
from typing import List, Tuple


def n_chunks(n_kf: int, c: int, o: int) -> int:
    """N_chunk = ⌈(N_kf − o)/(c − o)⌉  (2). Ví dụ N_kf=72, c=12, o=2 → 7."""
    if not (1 <= o < c):
        raise ValueError("cần 1 ≤ o < c")
    if n_kf <= 0:
        raise ValueError("n_kf phải > 0")
    return max(1, math.ceil((n_kf - o) / (c - o)))


def chunk_ranges(n_kf: int, c: int, o: int) -> List[Tuple[int, int]]:
    """Khoảng chỉ số [start, end) (0-based) cho từng chunk; hai chunk liền kề gối nhau o ảnh.

    Ví dụ N_kf=72, c=12, o=2 (ĐC Hình 7, 1-based): 1–12, 11–22, 21–32, …, 61–72.
    """
    count = n_chunks(n_kf, c, o)
    ranges = []
    for i in range(count):
        start = i * (c - o)
        end = min(start + c, n_kf)
        ranges.append((start, end))
    return ranges
