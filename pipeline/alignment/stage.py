"""Stage `align` (ĐC §15, kế hoạch §4.4, M1c): căn Sim(3) VGGT → COLMAP từng chunk và đổi sang mét bằng một mốc scale.

- Mỗi chunk VGGT có hệ riêng (camera đầu chunk là gốc) nên căn từng chunk. Hai phương pháp (`align.method`):
  * `centers` (ĐC §15.1): x_i = −Rᵀt của VGGT, y_i = tâm camera COLMAP cùng view, RANSAC + Umeyama (13)–(17). Ngưỡng inlier = `align.ransac.max_error_ratio` ×
    khoảng cách trung vị giữa hai camera COLMAP liên tiếp. Kém điều kiện khi 12 camera trải ngắn (WORKING_LOG, lệch #36).
  * `orientation_depth` (LỆCH ĐC §15.1, mặc định): xoay R lấy từ hướng camera (trung bình R_wc,COLMAP · R_cw,VGGT có loại ngoại lai), scale s = trung vị tỉ lệ khoảng cách
    camera→điểm MVS (COLMAP) so với camera→điểm VGGT cùng pixel, tịnh tiến t = trung vị (y_i − s R x_i) trên tâm camera.
- Chunk dưới `align.min_pairs` view đăng ký (hoặc không có cặp điểm) bị loại (`accepted = false`) và không dùng ở fusion.
- Mốc scale: `ground_truth/scale_anchor.json` phải có `L_model` (do `scripts/click_anchor_2d.py` điền); `s_m = L_real / L_model` (4).
  B0 mét = `fused.ply` × `s_m` ở `baselines/colmap/metric/`.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from ..common import config as cfgmod
from ..common.errors import E_ANCHOR_STALE, E_MISSING_INPUT, StageError
from ..common.geometry import camera_center, umeyama_sim3
from ..common.io import SceneLayout, ensure_dir, read_json, write_json
from ..vggt.infer import read_chunk
from .ransac import metric_scale, ransac_sim3, reference_distance, threshold_from_ratio


def load_colmap_cameras(layout: SceneLayout) -> Dict[int, Dict]:
    """view_id → {K, R, t, center} của mọi ảnh đã đăng ký trong `baselines/colmap/sfm/sparse/0` (đv COLMAP)."""
    import pycolmap
    sparse = layout.colmap_sfm / "sparse" / "0"
    if not (sparse / "images.bin").is_file():
        raise StageError(E_MISSING_INPUT, f"thiếu {sparse}: chạy stage sfm trước")
    rec = pycolmap.Reconstruction(str(sparse))
    out: Dict[int, Dict] = {}
    for img in rec.images.values():
        cfw = img.cam_from_world
        r, t = np.asarray(cfw.rotation.matrix(), dtype=np.float64), np.asarray(cfw.translation, dtype=np.float64)
        out[int(img.name.split(".")[0])] = {"K": np.asarray(rec.cameras[img.camera_id].calibration_matrix(), dtype=np.float64),
                                            "R": r, "t": t, "center": camera_center(r, t)}
    return out


def model_fingerprint(layout: SceneLayout) -> str:
    """SHA-256 của `sparse/0/images.bin`: nhận diện model COLMAP mà mốc scale đã được click trên đó (đv COLMAP đổi theo từng lần chạy SfM)."""
    import hashlib
    return hashlib.sha256((layout.colmap_sfm / "sparse" / "0" / "images.bin").read_bytes()).hexdigest()


def vggt_centers(extrinsic: np.ndarray) -> np.ndarray:
    """Tâm camera x_i = −Rᵀt từ extrinsic VGGT world→camera (S, 3, 4)."""
    e = np.asarray(extrinsic, dtype=np.float64)
    return np.stack([camera_center(m[:, :3], m[:, 3]) for m in e])


def align_chunk(x_all: np.ndarray, views: List[int], cams: Dict[int, Dict], ratio: float, min_pairs: int) -> Dict:
    """Căn một chunk: ghép x_i với tâm COLMAP theo view, RANSAC + Umeyama. Trả dict kết quả (kể cả khi bị loại)."""
    idx = [i for i, v in enumerate(views) if v in cams]
    res: Dict = {"views": views, "n_views": len(views), "n_pairs": len(idx), "accepted": False, "reason": None}
    if len(idx) < min_pairs:
        res["reason"] = f"chỉ {len(idx)} view đã đăng ký COLMAP (< {min_pairs})"
        return res
    x = np.asarray(x_all)[idx]
    y = np.array([cams[views[i]]["center"] for i in idx])
    thresh = threshold_from_ratio(y, ratio)
    res.update(threshold=thresh, reference_distance=reference_distance(y))
    try:
        r = ransac_sim3(x, y, thresh, min_pairs=min_pairs)
    except ValueError as e:
        res["reason"] = str(e)
        return res
    inl = [int(views[idx[j]]) for j in np.nonzero(r["inliers"])[0]]
    res.update(s=r["s"], R=np.asarray(r["R"]).tolist(), t=np.asarray(r["t"]).tolist(), n_inliers=r["n_inliers"], rmse=r["rmse"],
               inlier_views=inl, accepted=r["n_inliers"] >= min_pairs)
    if not res["accepted"]:
        res["reason"] = f"{r['n_inliers']} inlier (< {min_pairs})"
    return res


def rotation_from_orientations(r_col_cw: np.ndarray, r_vggt_cw: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """R (VGGT world → COLMAP world) từ hướng camera: mỗi view cho R_i = R_wc,COLMAP · R_cw,VGGT; lấy trung bình bằng SVD, loại view lệch hơn
    median + 3·max(1,4826·MAD, 1°) (góc) rồi lấy lại. Trả về (R, góc lệch từng view (độ), mặt nạ giữ) [Suy luận cho 3·MAD và sàn 1°]."""
    ri = np.einsum("nji,njk->nik", np.asarray(r_col_cw), np.asarray(r_vggt_cw))          # R_wc,col = R_cw,colᵀ
    keep = np.ones(len(ri), dtype=bool)

    def mean_rot(sel):
        u, _, vt = np.linalg.svd(ri[sel].sum(axis=0))
        return u @ np.diag([1.0, 1.0, np.sign(np.linalg.det(u @ vt))]) @ vt

    def dev(r):
        c = (np.einsum("nij,ij->n", ri, r) - 1.0) / 2.0
        return np.degrees(np.arccos(np.clip(c, -1.0, 1.0)))

    r = mean_rot(keep)
    for _ in range(2):
        d = dev(r)
        med = np.median(d[keep])
        mad = 1.4826 * np.median(np.abs(d[keep] - med))
        new = d <= med + 3.0 * max(mad, 1.0)                    # sàn 1°: nhiễu hướng camera VGGT [Suy luận]; tránh MAD ≈ 0 loại nhầm view tốt
        if new.sum() < 2 or np.array_equal(new, keep):
            break
        keep = new
        r = mean_rot(keep)
    return r, dev(r), keep


def points_scale(pair_p: np.ndarray, pair_x: np.ndarray, rounds: int = 4, keep_frac: float = 0.8) -> float:
    """Scale khớp điểm VGGT → điểm MVS của chunk: Umeyama (14)–(17) lặp `rounds` vòng, mỗi vòng giữ `keep_frac` cặp ít lệch nhất [Suy luận cho 4 vòng, 80%].
    Giữ đúng khoảng cách giữa hai điểm, khác tỉ lệ khoảng cách camera→điểm (WORKING_LOG 05/11: thấp hơn 4–19% trên 42444738)."""
    p, x = np.asarray(pair_p, dtype=np.float64), np.asarray(pair_x, dtype=np.float64)
    keep = np.ones(len(p), dtype=bool)
    s = float("nan")
    for _ in range(rounds):
        if keep.sum() < 3:
            break
        s, r, t = umeyama_sim3(p[keep], x[keep])
        res = np.linalg.norm(s * (p @ np.asarray(r).T) + np.asarray(t) - x, axis=1)
        keep = res <= np.percentile(res[keep], keep_frac * 100)
    return float(s)


def align_chunk_orientation(extrinsic: np.ndarray, views: List[int], cams: Dict[int, Dict], pair_view: np.ndarray, pair_x: np.ndarray,
                            pair_p: np.ndarray, min_pairs: int, scale_from: str = "distances") -> Dict:
    """Căn một chunk theo hướng camera + scale + tâm camera (LỆCH ĐC §15.1).

    pair_view/pair_x/pair_p: các cặp (view của chunk, điểm MVS trong hệ COLMAP, điểm VGGT cùng pixel trong hệ chunk VGGT).
    scale_from: `distances` = trung vị tỉ lệ khoảng cách camera→điểm; `points` = khớp điểm–điểm (`points_scale`)."""
    if scale_from not in ("distances", "points"):
        raise ValueError(f"align.scale_from không hợp lệ: {scale_from!r} (distances | points)")
    ext = np.asarray(extrinsic, dtype=np.float64)
    idx = [i for i, v in enumerate(views) if v in cams]
    res: Dict = {"views": views, "n_views": len(views), "n_pairs": len(idx), "accepted": False, "reason": None, "method": "orientation_depth"}
    if len(idx) < min_pairs:
        res["reason"] = f"chỉ {len(idx)} view đã đăng ký COLMAP (< {min_pairs})"
        return res
    if len(pair_view) == 0:
        res["reason"] = "không có cặp điểm MVS nào để ước lượng scale"
        return res
    r_col = np.array([cams[views[i]]["R"] for i in idx])
    r, dev_deg, keep = rotation_from_orientations(r_col, ext[idx][:, :, :3])
    x_cent = vggt_centers(ext)
    c_of = {views[i]: x_cent[i] for i in idx}
    cam_col = np.array([cams[v]["center"] for v in pair_view])
    cam_vg = np.array([c_of[v] for v in pair_view])
    d_vggt = np.linalg.norm(np.asarray(pair_p) - cam_vg, axis=1)
    d_col = np.linalg.norm(np.asarray(pair_x) - cam_col, axis=1)
    ok = d_vggt > 1e-9
    if not ok.any():
        res["reason"] = "khoảng cách camera→điểm VGGT bằng 0"
        return res
    s = float(np.median(d_col[ok] / d_vggt[ok]))
    res["s_distances"] = s
    if scale_from == "points":
        s = points_scale(np.asarray(pair_p)[ok], np.asarray(pair_x)[ok])
    y = np.array([cams[views[i]]["center"] for i in idx])
    if scale_from == "points":      # camera VGGT có thể không cùng tỉ lệ với điểm VGGT: đặt t để điểm khớp MVS, không theo tâm camera
        t = np.median(np.asarray(pair_x)[ok] - s * (np.asarray(pair_p)[ok] @ r.T), axis=0)
    else:
        t = np.median(y[keep] - s * (x_cent[idx][keep] @ r.T), axis=0)
    resid = np.linalg.norm(y - (s * (x_cent[idx] @ r.T) + t), axis=1)
    pdev = np.linalg.norm(s * (np.asarray(pair_p) @ r.T) + t - np.asarray(pair_x), axis=1)[ok]
    res.update(s=s, R=r.tolist(), t=t.tolist(), n_inliers=int(keep.sum()), rmse=float(np.sqrt(np.mean(resid[keep] ** 2))),
               inlier_views=[int(views[idx[j]]) for j in np.nonzero(keep)[0]], rotation_dev_deg={"median": float(np.median(dev_deg[keep])), "max": float(dev_deg[keep].max())},
               n_point_pairs=int(ok.sum()), point_dev_colmap_units={"median": float(np.median(pdev)), "p90": float(np.percentile(pdev, 90))},
               accepted=bool(np.isfinite(s) and s > 0))
    if not res["accepted"]:
        res["reason"] = f"scale không hợp lệ ({s})"
    return res


def collect_point_pairs(layout: SceneLayout, cams: Dict[int, Dict], log: Callable[[str], None]) -> Dict[str, np.ndarray]:
    """Cặp (view, điểm MVS COLMAP, điểm VGGT hệ chunk) cho mọi cặp (i, k) của `fused.ply.vis`; view gán cho chunk xa biên hơn như ở stage fuse.
    Trả về dict: view (n,), chunk (n,), x (n, 3) đv COLMAP, p (n, 3) đv VGGT của chunk."""
    from ..common.schema import read_keyframes_csv
    from ..fusion import stage as fs  # nhập muộn: fusion.stage nhập alignment.stage
    from ..vggt.infer import pad_geometry
    mvs = layout.colmap_mvs
    for f in (mvs / "fused.ply", mvs / "fused.ply.vis"):
        if not f.is_file():
            raise StageError(E_MISSING_INPUT, f"thiếu {f}: chạy stage mvs trước (align theo hướng camera cần điểm MVS để ước lượng scale)")
    kf = read_keyframes_csv(layout.metadata / "keyframes.csv")
    geo = pad_geometry(int(kf[0]["w"]), int(kf[0]["h"]))
    chunks = []
    for p in sorted(layout.vggt.glob("chunk_*")):
        if (p / "vggt_raw.npz").is_file():
            k = int(p.name.split("_")[1])
            chunks.append({"chunk": k, "views": [int(v) for v in read_json(p / "chunk_meta.json")["views"]], "s": 1.0, "R": np.eye(3), "t": np.zeros(3)})
    xyz = fs.read_ply_xyz(mvs / "fused.ply")
    counts, flat = fs.read_vis(mvs / "fused.ply.vis")
    names = fs.read_fusion_image_names(mvs)
    idx_to_view = np.array([int(n.split(".")[0]) for n in names])
    kk, view = np.repeat(np.arange(len(counts)), counts), idx_to_view[flat]
    pr = fs.sample_pairs(layout, xyz, kk, view, cams, chunks, 1.0, geo, 4.0, 1.0, lambda m: None)
    v2c = fs.view_to_chunk(chunks)
    ok = pr["valid"]
    return {"view": view[ok], "chunk": np.array([v2c[int(v)][0] for v in view[ok]]), "x": xyz[kk[ok]], "p": pr["P"][ok]}


def apply_scale(layout: SceneLayout, cfg: Dict, log: Callable[[str], None]) -> Dict:
    """`s_m` từ `scale_anchor.json` (cần `L_model`) rồi ghi `scale.json` và B0 mét (`fused.ply` × s_m)."""
    path = layout.root / str(cfgmod.require(cfg, "align.anchor_file"))
    anchor = read_json(path) if path.is_file() else {}
    if "L_model" not in anchor:
        raise StageError(E_MISSING_INPUT, f"{path} chưa có L_model: chạy `python scripts/click_anchor_2d.py --scene ...` để click mốc {anchor.get('id', '?')}")
    fp = anchor.get("colmap_model_sha256")
    if fp is None:
        log("[align] CẢNH BÁO: scale_anchor.json không ghi dấu vân tay model COLMAP (click bằng bản cũ); không kiểm được mốc có còn khớp model hiện tại")
    elif fp != model_fingerprint(layout):
        raise StageError(E_ANCHOR_STALE, f"{path.name} được click trên model COLMAP khác model hiện tại (stage sfm đã chạy lại, đơn vị COLMAP đã đổi): "
                                         "chạy lại `python scripts/click_anchor_2d.py --scene ... --overwrite`")
    s_m = metric_scale(float(anchor["L_real"]), float(anchor["L_model"]))
    scale = {"s_m": s_m, "L_real": anchor["L_real"], "L_model": anchor["L_model"], "anchor_id": anchor.get("id"),
             "L_real_source": anchor.get("source"), "endpoint_uncertainty_m": anchor.get("endpoint_uncertainty_m")}
    write_json(layout.alignment / "scale.json", scale)
    fused = layout.colmap_mvs / "fused.ply"
    if fused.is_file():
        import open3d as o3d
        pcd = o3d.io.read_point_cloud(str(fused))
        pcd.scale(s_m, center=(0.0, 0.0, 0.0))
        ensure_dir(layout.colmap_metric)
        o3d.io.write_point_cloud(str(layout.colmap_metric / "fused_metric.ply"), pcd)
        scale["b0_points"] = len(pcd.points)
    log(f"[align] mốc {scale['anchor_id']}: L_real {scale['L_real']} m, L_model {scale['L_model']:.5f} đv COLMAP → s_m = {s_m:.4f} m/đv"
        + (f"; B0 mét {scale['b0_points']:,} điểm" if "b0_points" in scale else "; chưa có fused.ply nên chưa ghi B0 mét"))
    return scale


def run_align(layout: SceneLayout, cfg: Dict, log: Callable[[str], None] = print,
              load_cameras: Callable[[SceneLayout], Dict[int, Dict]] = load_colmap_cameras, with_scale: bool = True,
              load_pairs: Optional[Callable[[SceneLayout, Dict[int, Dict]], Dict[str, np.ndarray]]] = None) -> Dict:
    """Stage `align`. Vào: `baselines/vggt/chunk_XX/`, `baselines/colmap/{sfm,mvs}`, `ground_truth/scale_anchor.json`.
    Ra: `proposed/alignment/chunk_XX_sim3.json`, `align_result.json`, `scale.json`, `baselines/colmap/metric/fused_metric.ply`."""
    t0 = time.time()
    method = str(cfgmod.require(cfg, "align.method"))
    if method not in ("centers", "orientation_depth"):
        raise ValueError(f"align.method không hợp lệ: {method!r} (centers | orientation_depth)")
    ratio = float(cfgmod.require(cfg, "align.ransac.max_error_ratio")) if method == "centers" else None
    min_pairs = int(cfgmod.require(cfg, "align.min_pairs"))
    scale_from = str(cfgmod.require(cfg, "align.scale_from"))
    cks = sorted(p for p in layout.vggt.glob("chunk_*") if (p / "vggt_raw.npz").is_file())
    if not cks:
        raise StageError(E_MISSING_INPUT, f"thiếu {layout.vggt}/chunk_XX: chạy stage vggt trước")
    cams = load_cameras(layout)
    pairs = (load_pairs or (lambda lay, c: collect_point_pairs(lay, c, log)))(layout, cams) if method == "orientation_depth" else None
    out_dir = ensure_dir(layout.alignment)
    results = []
    for k in range(len(cks)):
        raw, _, meta = read_chunk(layout, k)
        views = [int(v) for v in meta["views"]]
        if method == "centers":
            r = align_chunk(vggt_centers(raw["extrinsic"]), views, cams, ratio, min_pairs)
        else:
            sel = pairs["chunk"] == k
            r = align_chunk_orientation(raw["extrinsic"], views, cams, pairs["view"][sel], pairs["x"][sel], pairs["p"][sel], min_pairs, scale_from)
        r.update(chunk=k, start=meta["start"], end=meta["end"])
        write_json(out_dir / f"chunk_{k:02d}_sim3.json", r)
        results.append(r)
        if not r["accepted"]:
            log(f"[align] chunk {k:02d} ảnh [{r['start']}, {r['end']}): BỊ LOẠI: {r['reason']}")
        elif method == "centers":
            log(f"[align] chunk {k:02d} ảnh [{r['start']}, {r['end']}): s {r['s']:.4f}, {r['n_inliers']}/{r['n_pairs']} inlier, rmse {r['rmse']:.5f} đv COLMAP (ngưỡng {r['threshold']:.5f})")
        else:
            log(f"[align] chunk {k:02d} ảnh [{r['start']}, {r['end']}): s {r['s']:.4f}, xoay lệch trung vị {r['rotation_dev_deg']['median']:.1f}° (lớn nhất {r['rotation_dev_deg']['max']:.1f}°, "
                f"{r['n_inliers']}/{r['n_pairs']} view), tâm camera rmse {r['rmse']:.5f}, điểm VGGT lệch MVS trung vị {r['point_dev_colmap_units']['median']:.4f} / p90 {r['point_dev_colmap_units']['p90']:.4f} đv COLMAP "
                f"({r['n_point_pairs']:,} cặp)")
    acc = [r for r in results if r["accepted"]]
    stats = {"method": method, "ratio": ratio, "n_chunks": len(results), "n_accepted": len(acc), "rejected_chunks": [r["chunk"] for r in results if not r["accepted"]],
             "rmse_median": float(np.median([r["rmse"] for r in acc])) if acc else None,
             "rmse_max": float(max(r["rmse"] for r in acc)) if acc else None,
             "s_median": float(np.median([r["s"] for r in acc])) if acc else None}
    if method == "orientation_depth" and acc:
        stats["point_dev_median_colmap_units"] = float(np.median([r["point_dev_colmap_units"]["median"] for r in acc]))
    write_json(out_dir / "align_result.json", stats)
    log(f"[align] phương pháp {method}: {len(acc)}/{len(results)} chunk được nhận; rmse tâm camera trung vị {stats['rmse_median']}, lớn nhất {stats['rmse_max']} đv COLMAP")
    if with_scale:
        stats["scale"] = apply_scale(layout, cfg, log)
    stats["seconds"] = round(time.time() - t0, 1)
    return stats


def preview_ratios(layout: SceneLayout, ratios: List[float], min_pairs: int = 3,
                   load_cameras: Callable[[SceneLayout], Dict[int, Dict]] = load_colmap_cameras) -> List[Dict]:
    """Chỉ đọc, không ghi: số inlier và rmse từng chunk với nhiều giá trị `max_error_ratio` (để người dùng chọn)."""
    cams = load_cameras(layout)
    rows = []
    for k in range(len(list(layout.vggt.glob("chunk_*")))):
        raw, _, meta = read_chunk(layout, k)
        x = vggt_centers(raw["extrinsic"])
        for ratio in ratios:
            r = align_chunk(x, [int(v) for v in meta["views"]], cams, ratio, min_pairs)
            rows.append({"chunk": k, "ratio": ratio, "n_pairs": r["n_pairs"], "n_inliers": r.get("n_inliers"), "rmse": r.get("rmse"),
                         "reference_distance": r.get("reference_distance"), "accepted": r["accepted"], "s": r.get("s")})
    return rows

