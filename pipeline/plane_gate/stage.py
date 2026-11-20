"""Stage `gate` (ĐC §17, kế hoạch §4.6, M1d): tìm mặt phẳng cấu trúc (sàn, trần, tường) rồi kéo điểm đủ tin cậy về mặt phẳng qua cổng (24), (25).

- Hướng lên `u`: trung bình −y của camera (ảnh đã upright) đổi sang hệ thế giới, tinh chỉnh bằng mặt phẳng ngang lớn nhất trong `plane.up_refine_deg`.
- Mặt phẳng: RANSAC tuần tự (Open3D `segment_plane`, độ dày `plane.tau_r`), tối đa `plane.max_planes`, mỗi mặt phẳng ≥ `plane.min_inlier_fraction` số điểm [Suy luận].
  Nhãn: pháp tuyến lệch `u` dưới `plane.tau_n_deg` → sàn (thấp hơn camera) hoặc trần (cao hơn camera); lệch trục ngang dưới `tau_n_deg` → tường; còn lại `other` (không thuộc S_struct).
  `plane.floor_rule: lowest` (M4 đợt 3d): chỉ mặt ngang thấp nhất (± `plane.floor_band_m`) là sàn, cao nhất là trần, mặt ngang khác `horizontal_other` (không thuộc S_struct);
  `plane.min_walls`/`extra_wall_passes`: thêm lượt RANSAC mặt đứng nếu chưa đủ tường.
- Mỗi điểm gắn với mặt phẳng gần nhất (theo r_k); θ_k từ pháp tuyến PCA của k láng giềng (`plane.gate_normal_knn`, mặc định bằng `plane.normal_knn`). Điểm KHÔNG qua cổng được giữ nguyên (ĐC Hình 20).
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from ..alignment.stage import load_colmap_cameras
from ..common import config as cfgmod
from ..common.errors import E_MISSING_INPUT, StageError
from ..common.io import SceneLayout, ensure_dir, read_json, write_json
from ..common.ply import read_ply, write_ply
from .gate import angle_to_plane_deg, force_project, gate_mask, project_to_plane, residual


def estimate_normals(points: np.ndarray, knn: int) -> np.ndarray:
    """Pháp tuyến cục bộ bằng PCA trên k láng giềng (Open3D). Chưa định hướng (dấu tuỳ ý)."""
    import open3d as o3d
    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.asarray(points, dtype=np.float64)))
    pcd.estimate_normals(o3d.geometry.KDTreeSearchParamKNN(knn=int(knn)))
    return np.asarray(pcd.normals)


def segment_plane(points: np.ndarray, thresh: float, iters: int = 1000) -> Optional[Tuple[np.ndarray, float, np.ndarray]]:
    """Một mặt phẳng RANSAC: (n, d, chỉ số inlier) với ‖n‖ = 1, nᵀx + d = 0; None nếu quá ít điểm."""
    import open3d as o3d
    if len(points) < 3:
        return None
    o3d.utility.random.seed(0)                                   # RANSAC lặp lại được
    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.asarray(points, dtype=np.float64)))
    model, inl = pcd.segment_plane(distance_threshold=float(thresh), ransac_n=3, num_iterations=int(iters))
    n = np.array(model[:3], dtype=np.float64)
    norm = np.linalg.norm(n)
    return n / norm, float(model[3] / norm), np.asarray(inl, dtype=np.int64)


def camera_up(cams: Dict[int, Dict]) -> np.ndarray:
    """u₀ = trung bình các hướng −y_cam (ảnh upright) trong hệ thế giới: R_cwᵀ · (0, −1, 0)."""
    ups = np.array([c["R"].T @ np.array([0.0, -1.0, 0.0]) for c in cams.values()])
    u = ups.mean(axis=0)
    return u / np.linalg.norm(u)


def refine_up(points: np.ndarray, normals: np.ndarray, u0: np.ndarray, refine_deg: float, thresh: float) -> Tuple[np.ndarray, Dict]:
    """Tinh chỉnh `u` bằng mặt phẳng ngang lớn nhất: lấy điểm có pháp tuyến cục bộ trong `refine_deg` quanh ±u0, RANSAC một mặt phẳng,
    nhận pháp tuyến của nó (cùng chiều u0) nếu lệch u0 không quá `refine_deg`. Không tìm được thì giữ u0."""
    ang = angle_to_plane_deg(normals, u0)                       # góc giữa pháp tuyến cục bộ và u0 (0–90°)
    cand = np.nonzero(ang < refine_deg)[0]
    info = {"u0": u0.tolist(), "n_candidates": int(len(cand)), "refined": False}
    if len(cand) < 50:
        return u0, info
    seg = segment_plane(points[cand], thresh)
    if seg is None:
        return u0, info
    n = seg[0] if seg[0] @ u0 > 0 else -seg[0]
    dev = float(np.degrees(np.arccos(np.clip(n @ u0, -1, 1))))
    info.update(n_inliers=int(len(seg[2])), deviation_deg=dev)
    if dev > refine_deg:
        return u0, info
    info["refined"] = True
    return n, info


def label_plane(n: np.ndarray, d: float, u: np.ndarray, cam_heights: np.ndarray, tau_n_deg: float) -> Tuple[str, float, float]:
    """(nhãn, góc giữa n và u (0–90°), độ cao mặt phẳng dọc u). Sàn thấp hơn camera trung vị, trần cao hơn."""
    a = float(np.degrees(np.arccos(np.clip(abs(n @ u), 0, 1))))
    if a < tau_n_deg:
        h = float(-d / (n @ u))                                  # điểm trên mặt phẳng có u·x = −d/(n·u)
        return ("floor" if h < float(np.median(cam_heights)) else "ceiling"), a, h
    if a > 90.0 - tau_n_deg:
        return "wall", a, float("nan")
    return "other", a, float("nan")


def restrict_horizontal(planes: List[Dict], rule: str, band: float) -> List[Dict]:
    """Quy tắc nhãn mặt ngang (M4 đợt 3d [Suy luận]). `any` (cũ): mọi mặt ngang dưới camera là sàn, trên camera là trần.
    `lowest`: chỉ mặt ngang THẤP NHẤT (và mặt cách nó ≤ `band` m, vì sàn có thể bị cong/tách đôi) là sàn, chỉ mặt CAO NHẤT (cùng band) là trần;
    mặt ngang khác nhãn `horizontal_other`, KHÔNG thuộc S_struct."""
    if rule == "any":
        return planes
    if rule != "lowest":
        raise ValueError(f"plane.floor_rule phải là any hoặc lowest, nhận {rule!r}")
    for lab, pick in (("floor", min), ("ceiling", max)):
        grp = [p for p in planes if p["label"] == lab]
        if not grp:
            continue
        ref = pick(p["height_m"] for p in grp)
        for p in grp:
            if abs(p["height_m"] - ref) > band + 1e-9:
                p["label"] = "horizontal_other"
    return planes


def find_planes(points: np.ndarray, u: np.ndarray, cam_heights: np.ndarray, tau_r: float, tau_n_deg: float, max_planes: int, min_frac: float,
                normals: Optional[np.ndarray] = None, floor_rule: str = "any", floor_band: float = 0.0, min_walls: int = 0,
                wall_passes: int = 0, wall_cand_deg: float = 60.0) -> List[Dict]:
    """RANSAC tuần tự: mỗi vòng lấy mặt phẳng nhiều inlier nhất trong số điểm còn lại, loại inlier, dừng khi dưới `min_frac` hoặc đủ `max_planes`.

    M4 đợt 3d [Suy luận], mặc định giữ hành vi cũ: nếu số tường < `min_walls`, chạy thêm tối đa `wall_passes` lượt RANSAC chỉ trên điểm có pháp tuyến cục bộ
    lệch hướng lên ≥ `wall_cand_deg` và cách mọi tường đã có hơn `tau_r` (cần `normals`); rồi áp quy tắc nhãn mặt ngang (`restrict_horizontal`)."""
    remaining = np.arange(len(points))
    planes: List[Dict] = []
    for _ in range(int(max_planes)):
        if len(remaining) < max(3, min_frac * len(points)):
            break
        seg = segment_plane(points[remaining], tau_r)
        if seg is None or len(seg[2]) < min_frac * len(points):
            break
        n, d, inl = seg
        label, a, h = label_plane(n, d, u, cam_heights, tau_n_deg)
        planes.append({"id": len(planes), "n": n.tolist(), "d": d, "label": label, "angle_to_up_deg": a, "height_m": None if np.isnan(h) else h,
                       "n_inliers": int(len(inl))})
        remaining = np.delete(remaining, inl)
    if min_walls > 0 and wall_passes > 0:
        if normals is None:
            raise ValueError("min_walls > 0 cần pháp tuyến cục bộ (normals)")
        cand = np.nonzero(angle_to_plane_deg(normals, u) >= wall_cand_deg)[0]
        for p in planes:
            if p["label"] == "wall" and len(cand):
                cand = cand[residual(points[cand], np.array(p["n"]), p["d"]) > tau_r]
        for _ in range(int(wall_passes)):
            if sum(p["label"] == "wall" for p in planes) >= min_walls or len(cand) < max(3, min_frac * len(points)):
                break
            seg = segment_plane(points[cand], tau_r)
            if seg is None:
                break
            n, d, inl = seg
            cand_next = np.delete(cand, inl)
            label, a, h = label_plane(n, d, u, cam_heights, tau_n_deg)
            if label == "wall" and len(inl) >= min_frac * len(points):
                planes.append({"id": len(planes), "n": n.tolist(), "d": d, "label": label, "angle_to_up_deg": a, "height_m": None, "n_inliers": int(len(inl)),
                               "source": "extra_wall_pass"})
            cand = cand_next
    return restrict_horizontal(planes, floor_rule, floor_band)


def robust_fit(points: np.ndarray, iters: int = 2, k_sigma: float = 2.5) -> Tuple[np.ndarray, float, np.ndarray]:
    """Khớp mặt phẳng PCA, lặp `iters` lần bỏ điểm có |r| > k_sigma·σ. Trả về (n, d, mask điểm giữ)."""
    keep = np.ones(len(points), bool)
    for _ in range(iters + 1):
        c = points[keep].mean(axis=0)
        n = np.linalg.svd(points[keep] - c, full_matrices=False)[2][-1]
        d = -float(n @ c)
        r = points @ n + d
        sigma = float(np.sqrt(np.mean(r[keep] ** 2)))                     # σ của residual có dấu (không phải của |r|)
        new = np.abs(r) <= max(k_sigma * sigma, 1e-6)
        if new.sum() < 3 or (new == keep).all():
            break
        keep = new
    return n, d, keep


def cluster_components(points: np.ndarray, eps: float, min_points: int) -> np.ndarray:
    """Nhãn mảng liền (DBSCAN Open3D, −1 = nhiễu)."""
    import open3d as o3d
    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.asarray(points, dtype=np.float64)))
    return np.asarray(pcd.cluster_dbscan(eps=float(eps), min_points=int(min_points), print_progress=False))


def find_planes_refined(points: np.ndarray, normals: np.ndarray, u: np.ndarray, cam_heights: np.ndarray, tau_n_deg: float,
                        ransac_m: float, normal_deg: float, eps: float, min_points: int, max_proposals: int,
                        floor_rule: str = "any", floor_band: float = 0.0, dbscan_min: int = 5, merge_deg: float = 0.0, merge_m: float = 0.0) -> List[Dict]:
    """Bộ dò mặt phẳng cải tiến (lệch #53, [Suy luận]): RANSAC độ dày mỏng `ransac_m` đề xuất (n, d); inlier phải có pháp tuyến cục bộ
    lệch n < `normal_deg` (bỏ điểm của bề mặt khác nằm trong tấm mỏng); tách inlier thành mảng liền (DBSCAN `eps`), mỗi mảng ≥ `min_points`
    là một mặt riêng, khớp lại bằng PCA bền (`robust_fit`). Mọi inlier của đề xuất bị loại khỏi tập còn lại để vòng lặp luôn tiến."""
    remaining = np.arange(len(points))
    planes: List[Dict] = []
    for _ in range(int(max_proposals)):
        if len(remaining) < min_points:
            break
        seg = segment_plane(points[remaining], ransac_m)
        if seg is None or len(seg[2]) < min_points:
            break
        n, _, inl = seg
        cand = remaining[inl]
        remaining = np.delete(remaining, inl)
        good = cand[angle_to_plane_deg(normals[cand], n) < normal_deg]
        if len(good) < min_points:
            continue
        lab = cluster_components(points[good], eps, dbscan_min)
        for c in np.unique(lab[lab >= 0]):
            comp = good[lab == c]
            if len(comp) < min_points:
                continue
            n2, d2, keep = robust_fit(points[comp])
            label, a, h = label_plane(n2, d2, u, cam_heights, tau_n_deg)
            planes.append({"id": len(planes), "n": n2.tolist(), "d": d2, "label": label, "angle_to_up_deg": a, "height_m": None if np.isnan(h) else h,
                           "n_inliers": int(keep.sum()), "source": "refined", "_members": comp[keep]})
    if merge_deg > 0 and merge_m > 0:
        planes = merge_coplanar(points, planes, u, cam_heights, tau_n_deg, merge_deg, merge_m)
    return restrict_horizontal(planes, floor_rule, floor_band)


def merge_coplanar(points: np.ndarray, planes: List[Dict], u: np.ndarray, cam_heights: np.ndarray, tau_n_deg: float,
                   merge_deg: float, merge_m: float) -> List[Dict]:
    """Gộp các mảng đồng phẳng (pháp tuyến lệch < `merge_deg`, mặt này cách tâm mảng kia < `merge_m`) rồi khớp lại trên hợp inlier.
    Sai số MVS gợn sóng tần số thấp: mảng nhỏ khớp theo gợn, mặt lớn trung bình hoá được (lệch #53, [Suy luận])."""
    parent = list(range(len(planes)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cos_max = np.cos(np.radians(merge_deg))
    ns = [np.array(p["n"]) for p in planes]
    cs = [points[p["_members"]].mean(axis=0) for p in planes]
    for i in range(len(planes)):
        for j in range(i + 1, len(planes)):
            if abs(ns[i] @ ns[j]) >= cos_max and abs(ns[i] @ cs[j] + planes[i]["d"]) < merge_m and abs(ns[j] @ cs[i] + planes[j]["d"]) < merge_m:
                parent[root(j)] = root(i)
    out: List[Dict] = []
    for r in sorted({root(i) for i in range(len(planes))}):
        idx = np.concatenate([planes[i]["_members"] for i in range(len(planes)) if root(i) == r])
        n2, d2, keep = robust_fit(points[idx])
        label, a, h = label_plane(n2, d2, u, cam_heights, tau_n_deg)
        out.append({"id": len(out), "n": n2.tolist(), "d": d2, "label": label, "angle_to_up_deg": a, "height_m": None if np.isnan(h) else h,
                    "n_inliers": int(keep.sum()), "source": "refined_merged", "n_patches": int(sum(root(i) == r for i in range(len(planes)))),
                    "_members": idx[keep]})
    return out


def run_gate(layout: SceneLayout, cfg: Dict, log: Callable[[str], None] = print,
             load_cameras: Callable[[SceneLayout], Dict[int, Dict]] = load_colmap_cameras) -> Dict:
    """Stage `gate`. Vào: `proposed/fusion/fused_points.ply`. Ra: `proposed/plane_refinement/{refined_points.ply, planes.json, gate_log.csv}`."""
    t0 = time.time()
    tau_r, tau_n, tau_w = (float(cfgmod.require(cfg, f"plane.{k}")) for k in ("tau_r", "tau_n_deg", "tau_w"))
    alpha, up_deg = float(cfgmod.require(cfg, "plane.alpha")), float(cfgmod.require(cfg, "plane.up_refine_deg"))
    max_planes, min_frac = int(cfgmod.require(cfg, "plane.max_planes")), float(cfgmod.require(cfg, "plane.min_inlier_fraction"))
    knn, force = int(cfgmod.require(cfg, "plane.normal_knn")), bool(cfgmod.require(cfg, "plane.force"))
    gate_knn = cfgmod.get(cfg, "plane.gate_normal_knn")
    knn = knn if gate_knn is None else int(gate_knn)                       # khoá riêng cho cổng: `plane.normal_knn` còn dùng cho Poisson ở export
    floor_rule, floor_band = str(cfgmod.require(cfg, "plane.floor_rule")), float(cfgmod.require(cfg, "plane.floor_band_m"))
    min_walls, wall_passes = int(cfgmod.require(cfg, "plane.min_walls")), int(cfgmod.require(cfg, "plane.extra_wall_passes"))
    src = layout.fusion / "fused_points.ply"
    if not src.is_file():
        raise StageError(E_MISSING_INPUT, f"thiếu {src}: chạy stage fuse trước")
    f = read_ply(src)
    pts = np.stack([f["x"], f["y"], f["z"]], axis=1).astype(np.float64)
    w_k = f["w_k"].astype(np.float64)
    s_m = float(read_json(layout.alignment / "scale.json")["s_m"])
    cams = load_cameras(layout)
    centers = np.array([c["center"] for c in cams.values()]) * s_m

    normals = estimate_normals(pts, knn)
    u0 = camera_up(cams)
    u, up_info = refine_up(pts, normals, u0, up_deg, tau_r)
    cam_heights = centers @ u
    detector, scope = str(cfgmod.get(cfg, "plane.detector") or "ransac"), str(cfgmod.get(cfg, "plane.gate_scope") or "struct")
    if detector == "refined":
        rc = cfgmod.require(cfg, "plane.refined")
        planes = find_planes_refined(pts, normals, u, cam_heights, tau_n, float(rc["ransac_m"]), float(rc["normal_deg"]), float(rc["cluster_eps_m"]),
                                     int(rc["min_points"]), int(rc["max_proposals"]), floor_rule, floor_band,
                                     merge_deg=float(rc.get("merge_deg") or 0), merge_m=float(rc.get("merge_m") or 0))
    elif detector == "ransac":
        planes = find_planes(pts, u, cam_heights, tau_r, tau_n, max_planes, min_frac, normals, floor_rule, floor_band, min_walls, wall_passes)
    else:
        raise ValueError(f"plane.detector phải là ransac hoặc refined, nhận {detector!r}")
    if scope not in ("struct", "all"):
        raise ValueError(f"plane.gate_scope phải là struct hoặc all, nhận {scope!r}")
    log(f"[gate] {len(pts):,} điểm; hướng lên: lệch u0 {up_info.get('deviation_deg', float('nan')):.1f}° ({'đã tinh chỉnh' if up_info['refined'] else 'giữ u0'}); "
        f"{len(planes)} mặt phẳng: " + ", ".join(f"{p['label']}({p['n_inliers']:,})" for p in planes))
    struct = [p for p in planes if scope == "all" or p["label"] in ("floor", "ceiling", "wall")]   # all: lệch #54, cả mặt đồ đạc
    if not struct:
        raise StageError(E_MISSING_INPUT, "không tìm được mặt phẳng cấu trúc nào (sàn, trần, tường); xem planes và plane.min_inlier_fraction")
    pn = np.array([p["n"] for p in struct])
    pd = np.array([p["d"] for p in struct])
    if detector == "refined":
        # mặt cục bộ: gán điểm cho mặt có mảng inlier gần nhất (≤ cluster_eps_m), không cho mặt vô hạn hút điểm ở xa (lệch #53)
        from scipy.spatial import cKDTree
        mem = np.concatenate([p["_members"] for p in struct])
        owner = np.concatenate([np.full(len(p["_members"]), i) for i, p in enumerate(struct)])
        dist, j = cKDTree(pts[mem]).query(pts, distance_upper_bound=float(cfgmod.require(cfg, "plane.refined.cluster_eps_m")))
        supported = np.isfinite(dist)
        nearest = np.where(supported, owner[np.minimum(j, len(owner) - 1)], 0)
        r_k = np.abs(np.einsum("ij,ij->i", pts, pn[nearest]) + pd[nearest])
        members = np.full(len(pts), -1, dtype=np.int32)
        members[mem] = [struct[i]["id"] for i in owner]
    else:
        r_all = np.stack([residual(pts, pn[i], pd[i]) for i in range(len(struct))], axis=1)         # (K, P)
        nearest = r_all.argmin(axis=1)
        r_k = r_all[np.arange(len(pts)), nearest]
        supported, members = np.ones(len(pts), bool), None
    theta_k = np.empty(len(pts))
    for i in range(len(struct)):
        sel = nearest == i
        if sel.any():
            theta_k[sel] = angle_to_plane_deg(normals[sel], pn[i])
    is_struct = supported                                                                        # `struct` chỉ gồm mặt phẳng thuộc S_struct; refined: thêm điều kiện có mảng gần
    g = gate_mask(r_k, theta_k, is_struct, w_k, tau_r, tau_n, tau_w)
    refined = force_project(pts, [(pn[i], pd[i]) for i in range(len(struct))], alpha) if force else np.empty_like(pts)
    if not force:
        refined = pts.copy()
        for i in range(len(struct)):
            sel = nearest == i
            refined[sel] = project_to_plane(pts[sel], pn[i], pd[i], g[sel], alpha)
    disp = np.linalg.norm(refined - pts, axis=1)

    out_dir = ensure_dir(layout.plane_refinement)
    for p in planes:
        p.pop("_members", None)
    if members is not None:
        np.save(out_dir / "plane_members.npy", members)                   # id mặt của điểm inlier (−1 = không thuộc mảng nào), cho A3
    write_ply(out_dir / "refined_points.ply", {"x": refined[:, 0].astype(np.float32), "y": refined[:, 1].astype(np.float32), "z": refined[:, 2].astype(np.float32),
                                                "w_k": w_k.astype(np.float32), "g": g.astype(np.uint8), "plane_id": np.array([struct[i]["id"] for i in nearest], dtype=np.int32)})
    write_json(out_dir / "planes.json", {"up": u.tolist(), "up_info": up_info, "camera_height_median_m": float(np.median(cam_heights)), "planes": planes,
                                         "structural_plane_ids": [p["id"] for p in struct], "params": {"tau_r": tau_r, "tau_n_deg": tau_n, "tau_w": tau_w, "alpha": alpha, "force": force, "normal_knn": knn,
                                                                                  "floor_rule": floor_rule, "floor_band_m": floor_band, "min_walls": min_walls, "detector": detector, "gate_scope": scope}})
    labels = np.array([struct[i]["label"] for i in nearest])
    with open(out_dir / "gate_log.csv", "w", encoding="utf-8", newline="") as fh:
        fh.write("point,plane_id,label,r_m,theta_deg,w_k,g,displacement_m\n")
        for k in range(len(pts)):
            fh.write(f"{k},{struct[nearest[k]]['id']},{labels[k]},{r_k[k]:.5f},{theta_k[k]:.2f},{w_k[k]:.4f},{int(g[k])},{disp[k]:.5f}\n")
    cond = {"r<tau_r": float((r_k < tau_r).mean()), "theta<tau_n": float((theta_k < tau_n).mean()), "w_k>tau_w": float((w_k > tau_w).mean())}
    stats = {"n_points": int(len(pts)), "n_planes": len(planes), "n_struct_planes": len(struct), "up_refined": up_info["refined"], "up_deviation_deg": up_info.get("deviation_deg"),
             "plane_labels": [p["label"] for p in planes], "plane_inliers": [p["n_inliers"] for p in planes], "frac_gate_pass": float(g.mean()), "n_gate_pass": int(g.sum()),
             "condition_pass_fraction": cond, "displacement_cm": {"median_of_passed": round(float(np.median(disp[g]) * 100), 2) if g.any() else None,
                                                                  "max": round(float(disp.max() * 100), 2)},
             "force": force, "seconds": round(time.time() - t0, 1)}
    write_json(out_dir / "gate_result.json", stats)
    log(f"[gate] qua cổng {stats['n_gate_pass']:,}/{len(pts):,} ({stats['frac_gate_pass'] * 100:.1f}%); riêng từng điều kiện: r<τ_r {cond['r<tau_r'] * 100:.1f}%, θ<τ_n {cond['theta<tau_n'] * 100:.1f}%, "
        f"w_k>τ_w {cond['w_k>tau_w'] * 100:.1f}%; dịch tối đa {stats['displacement_cm']['max']} cm; {stats['seconds']} s")
    return stats
