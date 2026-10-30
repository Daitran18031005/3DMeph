"""Chẩn đoán: số match đã kiểm hình học giữa các keyframe liền kề + ảnh nào được đăng ký (chỉ đọc)."""
import sqlite3
import sys
from pathlib import Path

import numpy as np

root = Path(sys.argv[1])
db = sqlite3.connect(str(root / "baselines/colmap/sfm/database.db"))
M = 2147483647
names = {i: n for i, n in db.execute("select image_id, name from images")}
kp = {i: r for i, r in db.execute("select image_id, rows from keypoints")}
order = sorted(names, key=lambda i: names[i])
pos = {i: k for k, i in enumerate(order)}
inl = {}
for pid, rows in db.execute("select pair_id, rows from two_view_geometries"):
    a, b = divmod(pid, M)
    inl[(a, b)] = rows

import pycolmap
sparse = root / "baselines/colmap/sfm/sparse"
reg = {}
for d in sorted(p for p in sparse.iterdir() if p.is_dir()):
    rec = pycolmap.Reconstruction(str(d))
    for im in rec.images.values():
        reg[im.name] = d.name
    print("model", d.name, "ảnh", rec.num_reg_images(), "điểm", len(rec.points3D))

print("keypoints/ảnh: trung vị", np.median(list(kp.values())), "min", min(kp.values()))
adj = np.array([inl.get((order[k], order[k + 1]), 0) for k in range(len(order) - 1)])
print("match liền kề (inlier): trung vị", np.median(adj), "p10", np.percentile(adj, 10), "min", adj.min(), "| cặp <15:", int((adj < 15).sum()), "/", len(adj))
# chuỗi: R = đăng ký, . = không; số match tới ảnh kế
line = "".join(("0123456789"[int(reg[names[i]])] if names[i] in reg and reg[names[i]].isdigit() else "R") if names[i] in reg else "." for i in order)
print(line)
print("match liền kề theo thứ tự (cắt ở 99):", " ".join(str(min(int(x), 99)) for x in adj))
