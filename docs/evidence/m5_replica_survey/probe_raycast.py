"""Thử nhỏ (M5): dựng ảnh màu 640×480 từ `mesh.ply` của Replica bằng ray casting CPU của Open3D (không Habitat-Sim, không GPU).

    python docs/evidence/m5_replica_survey/probe_raycast.py data/raw/replica/room_0/mesh.ply out.png
Open3D không đọc được PLY mặt tứ giác của Replica nên dùng trimesh để tam giác hoá. Màu lấy từ màu đỉnh nội suy theo toạ độ barycentric (không dùng ptex HDR).
"""

import sys
import time

import numpy as np

import pipeline  # noqa: F401  (import torch trước open3d)

import open3d as o3d  # isort: skip
import trimesh  # isort: skip
from PIL import Image  # isort: skip


def main(path: str, out: str) -> None:
    m = trimesh.load(path, process=False)
    v, f = np.asarray(m.vertices, dtype=np.float64), np.asarray(m.faces, dtype=np.int32)
    cols = np.asarray(m.visual.vertex_colors)[:, :3] / 255.0
    sc = o3d.t.geometry.RaycastingScene()
    sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(v), o3d.utility.Vector3iVector(f))))
    ctr, f32 = (v.min(0) + v.max(0)) / 2, o3d.core.Dtype.Float32
    imgs = []
    for ang in (0, 90):
        d = np.array([np.cos(np.deg2rad(ang)), np.sin(np.deg2rad(ang)), 0.0])
        rays = sc.create_rays_pinhole(fov_deg=90, center=o3d.core.Tensor(ctr + d, dtype=f32), eye=o3d.core.Tensor(ctr, dtype=f32),
                                      up=o3d.core.Tensor([0, 0, 1], dtype=f32), width_px=640, height_px=480)
        t0 = time.time()
        ans = sc.cast_rays(rays)
        tri, uv = ans["primitive_ids"].numpy().reshape(-1).astype(np.int64), ans["primitive_uvs"].numpy().reshape(-1, 2)
        ok = (tri >= 0) & (tri < len(f))
        c = np.zeros((tri.size, 3))
        c[ok] = (cols[f[tri[ok]]] * np.c_[1 - uv[ok].sum(1), uv[ok]][:, :, None]).sum(1)
        imgs.append((np.clip(c.reshape(480, 640, 3), 0, 1) * 255).astype(np.uint8))
        print(f"góc {ang}°: {time.time() - t0:.2f} s, trúng {np.isfinite(ans['t_hit'].numpy()).mean():.3f}")
    Image.fromarray(np.hstack(imgs)).save(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
