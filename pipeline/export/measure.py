"""Đo khoảng cách hai điểm trên mô hình đã ở mét: ‖B − A‖₂  (30), ĐC §19.1.

Thay cho thao tác chạm hai điểm trong Unity (mốc đầu chưa làm Unity). Mô hình đã ở mét nên không đổi
đơn vị gì thêm.

Cách chạy:
    python -m pipeline.export.measure --a 0.52 0.75 1.20 --b 1.90 0.75 1.20
    python -m pipeline.export.measure --glb model.glb --a ... --b ...   # kiểm tra thêm file GLB mở được
"""

from __future__ import annotations

import argparse
import sys

from ..common.geometry import euclid


def distance(a, b) -> float:
    """‖B − A‖₂ (m)."""
    return euclid(a, b)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Đo khoảng cách hai điểm trên mô hình (mét)")
    ap.add_argument("--a", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"))
    ap.add_argument("--b", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"))
    ap.add_argument("--glb", help="tuỳ chọn: file GLB để kiểm tra mở được và in kích thước hộp bao")
    args = ap.parse_args(argv)

    if args.glb:
        import trimesh

        scene = trimesh.load(args.glb)
        ext = scene.extents if hasattr(scene, "extents") else None
        print(f"GLB: {args.glb}, kích thước hộp bao (m): {None if ext is None else [round(float(v), 3) for v in ext]}")
    print(f"‖B − A‖ = {distance(args.a, args.b):.3f} m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
