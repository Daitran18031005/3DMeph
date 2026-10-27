"""Đọc và ghi PLY nhị phân nhỏ có thuộc tính tuỳ ý (xyz, w_k, n_views, ...). Chỉ dùng cho file do pipeline tự ghi (binary_little_endian, chỉ phần tử vertex)."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np

_TYPES = {"float32": "float", "float64": "double", "uint8": "uchar", "int32": "int", "uint32": "uint", "int64": "int64", "uint16": "ushort"}
_NP = {v: k for k, v in _TYPES.items()}


def write_ply(path, fields: Dict[str, np.ndarray]) -> None:
    """fields: tên → mảng 1 chiều cùng độ dài (x, y, z nên đứng đầu). Ghi binary_little_endian."""
    names = list(fields)
    n = len(fields[names[0]])
    dt = []
    for k in names:
        a = np.asarray(fields[k])
        if a.shape != (n,):
            raise ValueError(f"trường {k}: shape {a.shape}, cần ({n},)")
        if a.dtype.name not in _TYPES:
            raise ValueError(f"trường {k}: dtype {a.dtype} chưa hỗ trợ")
        dt.append((k, a.dtype.newbyteorder("<")))
    rec = np.empty(n, dtype=dt)
    for k in names:
        rec[k] = fields[k]
    head = ["ply", "format binary_little_endian 1.0", f"element vertex {n}"] + [f"property {_TYPES[np.asarray(fields[k]).dtype.name]} {k}" for k in names] + ["end_header"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(("\n".join(head) + "\n").encode("ascii"))
        f.write(rec.tobytes())


def read_ply(path) -> Dict[str, np.ndarray]:
    """Đọc file do `write_ply` ghi (hoặc PLY nhị phân little-endian chỉ có vertex với kiểu float/double/uchar/int/uint)."""
    with open(path, "rb") as f:
        data = f.read()
    end = data.find(b"end_header\n")
    if end < 0:
        raise ValueError(f"{path}: không có end_header")
    lines = data[:end].decode("ascii").splitlines()
    if "format binary_little_endian 1.0" not in lines:
        raise ValueError(f"{path}: chỉ hỗ trợ binary_little_endian")
    n = int(next(ln.split()[2] for ln in lines if ln.startswith("element vertex")))
    dt = []
    for ln in lines:
        if ln.startswith("property"):
            _, typ, name = ln.split()
            if typ not in _NP:
                raise ValueError(f"{path}: kiểu {typ} chưa hỗ trợ")
            dt.append((name, np.dtype(_NP[typ]).newbyteorder("<")))
    rec = np.frombuffer(data, dtype=dt, count=n, offset=end + len(b"end_header\n"))
    return {name: np.array(rec[name]) for name, _ in dt}
