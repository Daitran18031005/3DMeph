#!/usr/bin/env python3
"""
render_replica.py — dựng một scene Replica thành gói quay (định dạng app: `capture.json` + `frames/*.jpg`) để chạy pipeline (M5).

Render: Open3D ray casting CPU trên `mesh.ply` (màu đỉnh nội suy barycentric; không dùng ptex HDR), camera OpenCV 640×480, HFOV 70°.
Quỹ đạo [Suy luận, đặt trước]: hai vòng tròn quanh tâm hộp bao (bán kính 30% cạnh ngắn), cao 1,3 m và 1,6 m trên sàn, nhìn ra ngoài
(lệch 10° xuống), mỗi vòng `--frames/2` khung; bỏ khung có vật gần hơn 0,3 m (camera kẹt trong đồ vật). Trục lên của Replica là +z.
Mốc scale theo (4) [ĐC §8.1], quy tắc đặt trước: hai điểm bề mặt GT cách nhau 1,8–2,5 m, mỗi điểm thấy rõ (không bị che) ở ≥ 3 khung,
chọn cặp có số khung thấy ít hơn lớn nhất; điểm được chiếu vào ảnh bằng pose GT (thay cho click tay, không sai số click), `L_real` = |B − A|.
Pose GT chỉ để định vị đầu mút và để eval, KHÔNG suy scale (scale do tam giác hoá COLMAP theo (4)).

    python scripts/render_replica.py --scene room_0 --frames 240
Ra `data/scenes/replica/<scene>/raw/capture/`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pipeline  # noqa: E402,F401  (import torch trước open3d)

# isort: split
import cv2  # noqa: E402
import numpy as np  # noqa: E402
import open3d as o3d  # noqa: E402
import trimesh  # noqa: E402

W, H, HFOV = 640, 480, 70.0
UP = np.array([0.0, 0.0, 1.0])


def look_rotation(forward: np.ndarray) -> np.ndarray:
    """R world→camera (OpenCV: x phải, y xuống, z tới) cho hướng nhìn `forward`, trục lên của thế giới là +z."""
    z = forward / np.linalg.norm(forward)
    x = np.cross(z, UP)
    x /= np.linalg.norm(x)
    return np.stack([x, np.cross(z, x), z])


def trajectory(v: np.ndarray, n: int):
    """Hai vòng theo hình chữ nhật sát tường (cách mép hộp bao 20% cạnh), cao 1,3 m và 1,6 m trên sàn, NHÌN VÀO giữa phòng (nơi có đồ đạc,
    nhiều hoạ tiết) lệch 15° xuống, lia ±20° theo hình sin (4 chu kỳ/vòng) để mỗi vùng được thấy từ nhiều góc. Đặt trước, không chỉnh theo kết quả.
    (Bản đầu nhìn ra tường trắng/rèm: room_0 chỉ đăng ký 60% ảnh, 3 model.) Trả về list (R, t) world→camera."""
    lo, hi = np.percentile(v, 1, axis=0), np.percentile(v, 99, axis=0)
    c, floor = (lo + hi) / 2, lo[2]
    a0, a1 = lo[:2] + 0.2 * (hi[:2] - lo[:2]), hi[:2] - 0.2 * (hi[:2] - lo[:2])
    corners = np.array([[a0[0], a0[1]], [a1[0], a0[1]], [a1[0], a1[1]], [a0[0], a1[1]], [a0[0], a0[1]]])
    seg = np.linalg.norm(np.diff(corners, axis=0), axis=1)
    cum = np.r_[0, np.cumsum(seg)]
    out = []
    for h in (1.3, 1.6):
        for i in range(n // 2):
            s = cum[-1] * i / (n // 2)
            k = min(np.searchsorted(cum, s, side="right") - 1, 3)
            xy = corners[k] + (corners[k + 1] - corners[k]) * (s - cum[k]) / seg[k]
            cam = np.array([xy[0], xy[1], floor + h])
            to_c = np.array([c[0] - xy[0], c[1] - xy[1], 0.0])
            yaw = np.arctan2(to_c[1], to_c[0]) + np.radians(20) * np.sin(2 * np.pi * 4 * i / (n // 2))
            fwd = np.array([np.cos(yaw), np.sin(yaw), 0.0]) * np.cos(np.radians(15)) - UP * np.sin(np.radians(15))
            R = look_rotation(fwd)
            out.append((R, -R @ cam))
    return out


def render(scene, verts, faces, cols, K, R, t):
    """Ảnh màu (H, W, 3) uint8 và độ sâu theo trục z camera (H, W), cùng điểm trúng (H·W, 3) world; NaN chỗ trượt."""
    u, w = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
    d_cam = np.stack([(u - K[0, 2]) / K[0, 0], (w - K[1, 2]) / K[1, 1], np.ones_like(u)], -1).reshape(-1, 3)
    d_world = d_cam @ R                                                   # Rᵀ · d (hàng)
    origin = -R.T @ t
    rays = np.concatenate([np.repeat(origin[None], len(d_world), 0), d_world], 1).astype(np.float32)
    ans = scene.cast_rays(o3d.core.Tensor(rays))
    th = ans["t_hit"].numpy()
    tri = ans["primitive_ids"].numpy().astype(np.int64)
    uv = ans["primitive_uvs"].numpy()
    ok = np.isfinite(th) & (tri >= 0) & (tri < len(faces))
    col = np.zeros((len(th), 3))
    bary = np.c_[1 - uv[ok].sum(1), uv[ok]]
    col[ok] = (cols[faces[tri[ok]]] * bary[:, :, None]).sum(1)
    depth = np.where(ok, th, np.nan)                                     # d_cam có z = 1 nên t_hit chính là độ sâu z
    pts = origin + d_world * depth[:, None]
    img = (np.clip(col.reshape(H, W, 3), 0, 1) * 255).astype(np.uint8)
    return img, depth.reshape(H, W), pts


def visible(p, K, R, t, depth, tol=0.03):
    """Điểm p (world) có nằm trong ảnh và không bị che (độ sâu khớp ảnh độ sâu ±tol m)."""
    x = R @ p + t
    if x[2] <= 0.1:
        return False
    u, w = K[0, 0] * x[0] / x[2] + K[0, 2], K[1, 1] * x[1] / x[2] + K[1, 2]
    if not (5 <= u < W - 5 and 5 <= w < H - 5):
        return False
    d = depth[int(w), int(u)]
    return bool(np.isfinite(d) and abs(d - x[2]) < tol)


def pick_anchor(cands, views, rng):
    """Cặp điểm 1,8–2,5 m, mỗi điểm thấy ở ≥ 3 khung; tối đa hoá số khung thấy của điểm kém hơn (quy tắc đặt trước)."""
    vis = np.array([sum(visible(p, *v) for v in views) for p in cands])
    good = np.flatnonzero(vis >= 3)
    best = None
    for i in good:
        dist = np.linalg.norm(cands[good] - cands[i], axis=1)
        for j in good[(dist >= 1.8) & (dist <= 2.5)]:
            score = min(vis[i], vis[j])
            if best is None or score > best[0]:
                best = (score, i, j)
    if best is None:
        raise SystemExit("không tìm được cặp mốc 1,8–2,5 m thấy ở ≥ 3 khung")
    return cands[best[1]], cands[best[2]], best[0]


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--frames", type=int, default=240)
    a = ap.parse_args(argv)
    mesh = trimesh.load(REPO / "data" / "raw" / "replica" / a.scene / "mesh.ply", process=False)
    verts, faces = np.asarray(mesh.vertices, dtype=np.float64), np.asarray(mesh.faces, dtype=np.int32)
    cols = np.asarray(mesh.visual.vertex_colors)[:, :3] / 255.0
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.core.Tensor(verts.astype(np.float32)), o3d.core.Tensor(faces.astype(np.uint32)))
    f = W / 2 / np.tan(np.radians(HFOV / 2))
    K = np.array([[f, 0, W / 2], [0, f, H / 2], [0, 0, 1]])
    out = REPO / "data" / "scenes" / "replica" / a.scene / "raw" / "capture"
    (out / "frames").mkdir(parents=True, exist_ok=True)
    frames, views, cands = [], [], []
    rng = np.random.default_rng(0)
    for k, (R, t) in enumerate(trajectory(verts, a.frames)):
        img, depth, pts = render(scene, verts, faces, cols, K, R, t)
        if np.nanmin(depth) < 0.3 or np.isnan(depth).mean() > 0.2:      # kẹt trong đồ vật hoặc nhìn ra ngoài mesh
            continue
        name = f"{len(frames):06d}.jpg"
        cv2.imwrite(str(out / "frames" / name), cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 92])
        m = np.eye(4)
        m[:3, :3], m[:3, 3] = R, t
        frames.append({"name": name, "t": 0.5 * len(frames), "w": W, "h": H, "fx": f, "fy": f, "cx": W / 2, "cy": H / 2, "T_cam_world": m.tolist()})
        views.append((K, R, t, depth))
        ok = np.flatnonzero(np.isfinite(pts[:, 0]))
        cands.extend(pts[rng.choice(ok, 4, replace=False)])
    A, B, nvis = pick_anchor(np.array(cands), views, rng)
    doc = {"device": f"Replica {a.scene} (render Open3D, màu đỉnh)", "scale_mode": "tape",
           "anchor": {"id": "R1", "label": "mốc chọn tự động trên mesh GT (render_replica.py)", "L_real": float(np.linalg.norm(B - A)),
                      "A": A.tolist(), "B": B.tolist()}, "frames": frames}
    (out / "capture.json").write_text(json.dumps(doc), encoding="utf-8")
    gt = out.parent.parent / "ground_truth"                               # đáp án cho eval: điểm trên mesh GT + dòng mốc (không có đoạn test)
    gt.mkdir(parents=True, exist_ok=True)
    pts, _ = trimesh.sample.sample_surface_even(trimesh.Trimesh(verts, faces, process=False), 2_000_000, seed=0)
    o3d.io.write_point_cloud(str(gt / "gt_points.ply"), o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.asarray(pts))))
    (gt / "measurements.csv").write_text("id,type,ground_truth_m,used_as_anchor,endpoints/notes\n"
                                         f"R1,local_distance,{doc['anchor']['L_real']:.4f},1,\"A=({A[0]:.4f}, {A[1]:.4f}, {A[2]:.4f}) "
                                         f"B=({B[0]:.4f}, {B[1]:.4f}, {B[2]:.4f}); mốc tự động trên mesh GT\"\n", encoding="utf-8")
    print(f"{a.scene}: {len(frames)} khung, mốc {doc['anchor']['L_real']:.3f} m thấy ở ≥ {nvis} khung → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
