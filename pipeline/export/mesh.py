"""Stage `export` (ĐC §19, kế hoạch §4.7, M1d): điểm đã làm phẳng → mesh Poisson → `model.glb` (mét, +Y là lên).

Pháp tuyến PCA hướng về camera gần nhất; Poisson độ sâu `export.poisson_depth`; cắt các đỉnh mật độ thấp (`export.density_quantile`); xoay hướng lên `u` về +Y
và đặt sàn (mặt phẳng sàn nhiều inlier nhất, nếu có) ở y = 0. Mốc đầu của phép đo vẫn chấm trên point cloud; mesh chỉ để xem và xuất [Suy luận, kế hoạch §4.7].
"""

from __future__ import annotations

import time
from typing import Callable, Dict, Tuple

import numpy as np

from ..alignment.stage import load_colmap_cameras
from ..common import config as cfgmod
from ..common.errors import E_MISSING_INPUT, StageError
from ..common.io import SceneLayout, ensure_dir, read_json, write_json
from ..common.ply import read_ply, write_ply
from ..plane_gate.stage import estimate_normals


def rotation_up_to_y(u: np.ndarray) -> np.ndarray:
    """Ma trận xoay 3×3 đưa vector đơn vị `u` về (0, 1, 0) (Rodrigues)."""
    u = np.asarray(u, dtype=np.float64) / np.linalg.norm(u)
    y = np.array([0.0, 1.0, 0.0])
    v = np.cross(u, y)
    c = float(u @ y)
    if np.linalg.norm(v) < 1e-12:
        return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))


def orient_towards_cameras(points: np.ndarray, normals: np.ndarray, centers: np.ndarray) -> np.ndarray:
    """Lật pháp tuyến để hướng về tâm camera gần nhất."""
    from scipy.spatial import cKDTree
    _, j = cKDTree(centers).query(points)
    to_cam = centers[j] - points
    flip = np.einsum("ij,ij->i", normals, to_cam) < 0
    out = normals.copy()
    out[flip] *= -1
    return out


def poisson_mesh(points: np.ndarray, normals: np.ndarray, depth: int, density_quantile: float) -> Tuple[np.ndarray, np.ndarray, int]:
    """Poisson (Open3D) rồi bỏ đỉnh có mật độ dưới phân vị `density_quantile`. Trả về (đỉnh, mặt, số đỉnh bị bỏ)."""
    import open3d as o3d
    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    pcd.normals = o3d.utility.Vector3dVector(normals)
    mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(pcd, depth=int(depth))
    dens = np.asarray(dens)
    drop = dens < np.quantile(dens, density_quantile)
    mesh.remove_vertices_by_mask(drop)
    return np.asarray(mesh.vertices), np.asarray(mesh.triangles), int(drop.sum())


def run_export(layout: SceneLayout, cfg: Dict, log: Callable[[str], None] = print,
               load_cameras: Callable[[SceneLayout], Dict[int, Dict]] = load_colmap_cameras) -> Dict:
    """Stage `export`. Vào: `proposed/plane_refinement/{refined_points.ply, planes.json}`. Ra: `proposed/export/{model.glb, model_points.ply, measurements.json}`."""
    import trimesh

    t0 = time.time()
    depth, dq = int(cfgmod.require(cfg, "export.poisson_depth")), float(cfgmod.require(cfg, "export.density_quantile"))
    knn = int(cfgmod.require(cfg, "plane.normal_knn"))
    if str(cfgmod.require(cfg, "export.up_axis")) != "y":
        raise ValueError("export.up_axis chỉ hỗ trợ y (glTF)")
    src, planes_path = layout.plane_refinement / "refined_points.ply", layout.plane_refinement / "planes.json"
    for p in (src, planes_path, layout.alignment / "scale.json"):
        if not p.is_file():
            raise StageError(E_MISSING_INPUT, f"thiếu {p}: chạy stage gate trước")
    f = read_ply(src)
    pts = np.stack([f["x"], f["y"], f["z"]], axis=1).astype(np.float64)
    pl = read_json(planes_path)
    u = np.array(pl["up"])
    s_m = float(read_json(layout.alignment / "scale.json")["s_m"])
    centers = np.array([c["center"] for c in load_cameras(layout).values()]) * s_m

    normals = orient_towards_cameras(pts, estimate_normals(pts, knn), centers)
    verts, faces, n_drop = poisson_mesh(pts, normals, depth, dq)
    if len(faces) == 0:
        raise StageError(E_MISSING_INPUT, "Poisson không tạo được mặt nào (quá ít điểm hoặc pháp tuyến hỏng)")
    rot = rotation_up_to_y(u)
    floors = [p for p in pl["planes"] if p["label"] == "floor"]
    y_floor = float(max(floors, key=lambda p: p["n_inliers"])["height_m"]) if floors else float(np.percentile(pts @ u, 1))
    shift = np.array([0.0, -y_floor, 0.0])
    v_up, p_up = verts @ rot.T + shift, pts @ rot.T + shift
    out_dir = ensure_dir(layout.export)
    mesh = trimesh.Trimesh(vertices=v_up, faces=faces, process=False)
    mesh.export(out_dir / "model.glb")
    write_ply(out_dir / "model_points.ply", {"x": p_up[:, 0].astype(np.float32), "y": p_up[:, 1].astype(np.float32), "z": p_up[:, 2].astype(np.float32),
                                              "w_k": f["w_k"], "g": f["g"]})
    ceilings = [p for p in pl["planes"] if p["label"] == "ceiling"]
    info = {"unit": "m", "up_axis": "y", "n_vertices": int(len(v_up)), "n_faces": int(len(faces)), "n_points": int(len(pts)), "poisson_depth": depth,
            "vertices_removed_low_density": n_drop, "bounds_min": v_up.min(axis=0).tolist(), "bounds_max": v_up.max(axis=0).tolist(),
            "extents_m": (v_up.max(axis=0) - v_up.min(axis=0)).tolist(),
            "frame": {"rotation_from_colmap_metric": rot.tolist(), "translation": shift.tolist(), "floor_height_in_colmap_metric_m": y_floor,
                      "note": "x_model = R · x_colmap_metric + translation (COLMAP × s_m)"},
            "floor_planes": len(floors), "ceiling_planes": len(ceilings), "segments": [],
            "seconds": round(time.time() - t0, 1)}
    write_json(out_dir / "measurements.json", info)
    log(f"[export] mesh {info['n_vertices']:,} đỉnh, {info['n_faces']:,} mặt (bỏ {n_drop:,} đỉnh mật độ thấp), hộp bao {[round(e, 2) for e in info['extents_m']]} m, "
        f"{len(floors)} mặt phẳng sàn, {len(ceilings)} trần; ghi {out_dir / 'model.glb'}; {info['seconds']} s")
    return info
