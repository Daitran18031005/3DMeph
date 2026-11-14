#!/usr/bin/env python3
"""
render_mesh_views.py — vẽ mesh `model.glb` (mét, +Y lên) bằng ray casting CPU của Open3D (không cần GPU/OpenGL): nhìn từ trên xuống (chiếu thẳng) và góc xiên, tô theo pháp tuyến.

Dùng khung hình `view_params.json` do `render_cloud_views.py` ghi cho cùng scene (hộp 1–99% của cloud), nên ảnh mesh và ảnh điểm cùng khung. Ra `<tag>_topdown.png`, `<tag>_view.png`.

    python scripts/render_mesh_views.py --glb data/scenes/arkitscenes/42897599/proposed/export/model.glb --out-dir docs/evidence/m4_improve/export_d3/42897599 --tag mesh
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import pipeline  # noqa: F401,E402  (torch trước open3d)

SIZE = 800
LIGHT = np.array([0.4, 0.8, 0.45]) / np.linalg.norm([0.4, 0.8, 0.45])


def shade(scene, rays) -> np.ndarray:
    ans = scene.cast_rays(rays)
    hit = np.isfinite(ans["t_hit"].numpy())
    n = ans["primitive_normals"].numpy()
    lam = np.abs(n @ LIGHT)                                   # hai mặt: pháp tuyến có thể ngược chiều
    img = np.where(hit, 0.25 + 0.75 * lam, 1.0)
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def main(argv=None) -> int:
    import open3d as o3d
    import trimesh
    from PIL import Image

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--glb", required=True)
    ap.add_argument("--out-dir", required=True, help="thư mục có view_params.json (nếu chưa có, tính từ chính mesh)")
    ap.add_argument("--tag", default="mesh")
    a = ap.parse_args(argv)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    m = trimesh.load(a.glb, force="mesh")
    vp = out / "view_params.json"
    if vp.is_file():
        box = json.loads(vp.read_text(encoding="utf-8"))
    else:
        v = np.asarray(m.vertices)
        lo, hi = np.percentile(v, 1, axis=0), np.percentile(v, 99, axis=0)
        pad = 0.05 * (hi - lo)
        box = {"lo": (lo - pad).tolist(), "hi": (hi + pad).tolist()}
        vp.write_text(json.dumps(box), encoding="utf-8")
    lo, hi = np.array(box["lo"]), np.array(box["hi"])
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(np.asarray(m.vertices, dtype=np.float64)),
                                                                                         o3d.utility.Vector3iVector(np.asarray(m.faces, dtype=np.int32)))))
    # nhìn từ trên xuống: tia thẳng đứng (-y) từ phía trên trần, x ngang, z dọc (như ảnh điểm: z hướng lên trên ảnh)
    xs = np.linspace(lo[0], hi[0], SIZE)
    zs = np.linspace(hi[2], lo[2], SIZE)
    gx, gz = np.meshgrid(xs, zs)
    org = np.stack([gx, np.full_like(gx, hi[1] + 5.0), gz], axis=-1).astype(np.float32)
    top = shade(scene, o3d.core.Tensor(np.concatenate([org, np.tile(np.array([0, -1, 0], np.float32), (SIZE, SIZE, 1))], axis=-1)))
    Image.fromarray(top).save(out / f"{a.tag}_topdown.png")
    # góc xiên (cùng góc với ảnh điểm: phương vị 35°, độ cao 30°), camera phối cảnh nhìn vào tâm hộp
    ctr = (lo + hi) / 2
    az, el, dist = np.deg2rad(35.0), np.deg2rad(30.0), float(np.linalg.norm(hi - lo)) * 0.9
    eye = ctr + dist * np.array([np.cos(el) * np.sin(az), np.sin(el), np.cos(el) * np.cos(az)])
    rays = scene.create_rays_pinhole(fov_deg=50, center=o3d.core.Tensor(ctr, dtype=o3d.core.Dtype.Float32), eye=o3d.core.Tensor(eye, dtype=o3d.core.Dtype.Float32),
                                     up=o3d.core.Tensor([0, 1, 0], dtype=o3d.core.Dtype.Float32), width_px=SIZE, height_px=SIZE)
    Image.fromarray(shade(scene, rays)).save(out / f"{a.tag}_view.png")
    print(f"[ok] {out / (a.tag + '_topdown.png')}, {out / (a.tag + '_view.png')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
