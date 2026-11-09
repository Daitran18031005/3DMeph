"""Chamfer / F-score của một biến thể so với Faro (ĐC §20.2, (34)(35)) trên hệ scene.

Mô hình đã ở hệ scene nhờ phép cứng scale = 1 (Kabsch tâm camera, `lengths.kabsch_rigid`), tuỳ chọn tinh chỉnh bằng ICP cứng scale = 1 (Open3D,
`with_scaling=False`): GT chỉ định vị, không cho scale. Faro và mô hình cùng bị cắt theo hộp quỹ đạo camera GT ± lề, rồi voxel hoá.
Hộp, voxel và khoảng ICP chưa có trong đề cương [Suy luận, TẠM] (`eval.crop_margin_m`, `eval.voxel_m`, `eval.icp_max_dist_m`).
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np

from .metrics import accuracy_completeness, chamfer, f_score, precision_recall


def crop_box(points: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    return points[np.all((points >= lo) & (points <= hi), axis=1)]


def voxel_downsample(points: np.ndarray, voxel_m: float) -> np.ndarray:
    import open3d as o3d
    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.asarray(points, dtype=np.float64)))
    return np.asarray(pcd.voxel_down_sample(voxel_m).points)


def load_points(path) -> np.ndarray:
    import open3d as o3d
    return np.asarray(o3d.io.read_point_cloud(str(path)).points, dtype=np.float64)


def icp_rigid(src: np.ndarray, dst: np.ndarray, max_dist_m: float) -> Tuple[np.ndarray, Dict]:
    """ICP điểm-điểm, KHÔNG đổi scale. Trả về (T 4×4 src→dst, {fitness, inlier_rmse_m, shift_m, rot_deg})."""
    import open3d as o3d
    p = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(src))
    q = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(dst))
    res = o3d.pipelines.registration.registration_icp(
        p, q, max_dist_m, np.eye(4), o3d.pipelines.registration.TransformationEstimationPointToPoint(with_scaling=False),
        o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=50))
    t = np.asarray(res.transformation)
    rot = float(np.degrees(np.arccos(np.clip((np.trace(t[:3, :3]) - 1.0) / 2.0, -1.0, 1.0))))
    return t, {"fitness": float(res.fitness), "inlier_rmse_m": float(res.inlier_rmse), "shift_m": float(np.linalg.norm(t[:3, 3])), "rot_deg": rot}


def geometry_metrics(model: np.ndarray, gt: np.ndarray, delta_m: float) -> Dict:
    """Acc, Comp, Chamfer (34) [cm]; Prec, Rec, F (35) với δ = `delta_m`."""
    acc, comp, d_mg, d_gm = accuracy_completeness(model, gt)
    prec, rec = precision_recall(d_mg, d_gm, delta_m)
    return {"acc_cm": acc * 100.0, "comp_cm": comp * 100.0, "chamfer_cm": chamfer(acc, comp) * 100.0, "precision": prec, "recall": rec, "f_score": f_score(prec, rec)}


def evaluate_geometry(model_scene: np.ndarray, faro_scene: np.ndarray, box: Optional[Tuple[np.ndarray, np.ndarray]], voxel_m: float, delta_m: float,
                      icp_max_dist_m: float) -> Dict:
    """model_scene, faro_scene: điểm ở hệ scene (mét). Trả về {"kabsch": {...}, "icp": {...}, "icp_info": {...}, "n_model", "n_faro"}."""
    m = voxel_downsample(crop_box(model_scene, *box) if box is not None else model_scene, voxel_m)   # box=None: đã lọc theo vùng (eval/region.py)
    g = voxel_downsample(crop_box(faro_scene, *box) if box is not None else faro_scene, voxel_m)
    if len(m) < 10 or len(g) < 10:
        raise ValueError(f"quá ít điểm sau khi cắt hộp: mô hình {len(m)}, Faro {len(g)}")
    out = {"kabsch": geometry_metrics(m, g, delta_m), "n_model": int(len(m)), "n_faro": int(len(g))}
    t, info = icp_rigid(m, g, icp_max_dist_m)
    out["icp"] = geometry_metrics(m @ t[:3, :3].T + t[:3, 3], g, delta_m)
    out["icp_info"] = info
    return out
