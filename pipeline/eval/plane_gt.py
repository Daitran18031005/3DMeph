"""Đáp án mặt phẳng của Replica từ nhãn preseg (ĐC §11) và chỉ số (36): P2Plane, PlaneRecall (M5).

`preseg.bin`: chỉ số mặt tứ giác (uint64) xếp theo segment, đổi sang mã segment từng tam giác bằng `quad_segments_to_triangles`.
`preseg.json["segmentation"]`: các segment, lớp `plane` là mặt phẳng. Mặt GT = segment `plane` có diện tích ≥ `eval.plane.min_area_m2`,
(n, d) khớp bình phương tối thiểu trên điểm lấy mẫu của nó.
Chấm một đám điểm (đã ở hệ GT): mỗi điểm gán cho mẫu GT gần nhất nếu cách ≤ `assign_m`; với mỗi mặt GT có ≥ `min_points` điểm gán:
P2Plane của mặt = trung bình |nᵀp + d| (36); mặt "tìm thấy" nếu mặt khớp trên điểm mô hình lệch pháp tuyến ≤ `max_angle_deg` và lệch vị trí
(tại tâm điểm) ≤ `max_offset_m`. P2Plane của scene = trung bình theo mặt; PlaneRecall = số mặt tìm thấy / số mặt GT (36).
Ngưỡng đặt trước khi chấm [Suy luận], không chỉnh theo kết quả trên Replica.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import numpy as np


def fit_plane(pts: np.ndarray):
    c = pts.mean(axis=0)
    n = np.linalg.svd(pts - c, full_matrices=False)[2][-1]
    return n, -float(n @ c), c


def quad_segments_to_triangles(ids: np.ndarray, meta, n_tri: int) -> np.ndarray:
    """`preseg.bin` = chỉ số mặt tứ giác (uint64) xếp liền theo từng segment (segment k chiếm `numPrimitives` chỉ số, theo thứ tự `meta`).
    trimesh tam giác hoá N mặt tứ giác thành 2N tam giác: nửa đầu là tam giác thứ nhất của mọi mặt, nửa sau là tam giác thứ hai
    (đã kiểm trên room_0: segment `plane` lệch phẳng trung vị 0,1–0,6 cm; xếp xen kẽ cho 70–110 cm). Trả về mã segment theo tam giác."""
    nq = n_tri // 2
    if 2 * nq != n_tri or len(ids) != nq or sum(s["numPrimitives"] for s in meta) != nq:
        raise ValueError(f"preseg không khớp mesh: {len(ids)} chỉ số, {n_tri} tam giác")
    qseg = np.full(nq, -1, dtype=np.int64)
    off = 0
    for s in meta:
        qseg[ids[off:off + s["numPrimitives"]].astype(np.int64)] = s["id"]
        off += s["numPrimitives"]
    return np.r_[qseg, qseg]


def load_plane_gt(raw_dir: Path, cfg_plane: Dict, n_samples: int = 2_000_000, seed: int = 0) -> Dict:
    """Mẫu điểm trên mesh GT kèm chỉ số mặt GT (−1 = không phẳng/nhỏ) và danh sách mặt (n, d)."""
    import trimesh
    mesh = trimesh.load(raw_dir / "mesh.ply", process=False)
    meta = json.loads((raw_dir / "preseg.json").read_text(encoding="utf-8"))["segmentation"]
    seg = quad_segments_to_triangles(np.fromfile(raw_dir / "preseg.bin", dtype=np.uint64), meta, len(mesh.faces))
    plane_ids = {s["id"] for s in meta if s["class"] == "plane"}
    area = np.bincount(np.maximum(seg, 0), weights=mesh.area_faces * (seg >= 0), minlength=int(seg.max()) + 1)
    keep = [i for i in sorted(plane_ids) if i < len(area) and area[i] >= float(cfg_plane["min_area_m2"])]
    pts, face = trimesh.sample.sample_surface(mesh, n_samples, seed=seed)
    sid = seg[face]
    label = np.full(len(pts), -1, dtype=np.int64)
    planes = []
    for k, i in enumerate(keep):
        sel = sid == i
        if sel.sum() < 50:
            continue
        n, d, _ = fit_plane(pts[sel])
        label[sel] = len(planes)
        planes.append({"segment": int(i), "n": n, "d": d, "area_m2": float(area[i])})
    return {"points": np.asarray(pts), "label": label, "planes": planes}


def plane_metrics(model_pts: np.ndarray, gt: Dict, cfg_plane: Dict) -> Dict:
    """P2Plane (cm, trung bình theo mặt GT có đủ điểm) và PlaneRecall (36) của một đám điểm đã ở hệ GT."""
    from scipy.spatial import cKDTree
    planes = gt["planes"]
    if not planes:
        return {"p2plane_cm": None, "plane_recall": None, "n_gt_planes": 0, "n_planes_scored": 0}
    dist, j = cKDTree(gt["points"]).query(model_pts, distance_upper_bound=float(cfg_plane["assign_m"]))
    ok = np.isfinite(dist)
    lab = np.full(len(model_pts), -1)
    lab[ok] = gt["label"][j[ok]]
    p2, found = [], 0
    cos_max = np.cos(np.radians(float(cfg_plane["max_angle_deg"])))
    for k, p in enumerate(planes):
        q = model_pts[lab == k]
        if len(q) < int(cfg_plane["min_points"]):
            continue
        p2.append(float(np.mean(np.abs(q @ p["n"] + p["d"]))))
        n2, _, c2 = fit_plane(q)
        if abs(n2 @ p["n"]) >= cos_max and abs(c2 @ p["n"] + p["d"]) <= float(cfg_plane["max_offset_m"]):
            found += 1
    return {"p2plane_cm": float(np.mean(p2) * 100) if p2 else None, "plane_recall": found / len(planes),
            "n_gt_planes": len(planes), "n_planes_scored": len(p2)}
