"""Stage `align` (ĐC §15, kế hoạch §4.4, M1c): căn Sim(3) VGGT → COLMAP từng chunk và đổi sang mét bằng một mốc scale.

- Mỗi chunk VGGT có hệ riêng (camera đầu chunk là gốc) nên căn từng chunk: x_i = −Rᵀt của VGGT, y_i = tâm camera COLMAP cùng view (13)–(17).
- Ngưỡng inlier = `align.ransac.max_error_ratio` × khoảng cách trung vị giữa hai camera COLMAP liên tiếp của chính chunk đó (`threshold_from_ratio`).
  Chunk dưới `align.min_pairs` inlier bị loại (`accepted = false`) và không dùng ở fusion.
- Mốc scale: `ground_truth/scale_anchor.json` phải có `L_model` (do `scripts/click_anchor_2d.py` điền); `s_m = L_real / L_model` (4).
  B0 mét = `fused.ply` × `s_m` ở `baselines/colmap/metric/`.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List

import numpy as np

from ..common import config as cfgmod
from ..common.errors import E_MISSING_INPUT, StageError
from ..common.geometry import camera_center
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


def apply_scale(layout: SceneLayout, cfg: Dict, log: Callable[[str], None]) -> Dict:
    """`s_m` từ `scale_anchor.json` (cần `L_model`) rồi ghi `scale.json` và B0 mét (`fused.ply` × s_m)."""
    path = layout.root / str(cfgmod.require(cfg, "align.anchor_file"))
    anchor = read_json(path) if path.is_file() else {}
    if "L_model" not in anchor:
        raise StageError(E_MISSING_INPUT, f"{path} chưa có L_model: chạy `python scripts/click_anchor_2d.py --scene ...` để click mốc {anchor.get('id', '?')}")
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
              load_cameras: Callable[[SceneLayout], Dict[int, Dict]] = load_colmap_cameras, with_scale: bool = True) -> Dict:
    """Stage `align`. Vào: `baselines/vggt/chunk_XX/`, `baselines/colmap/sfm/sparse/0`, `ground_truth/scale_anchor.json`.
    Ra: `proposed/alignment/chunk_XX_sim3.json`, `scale.json`, `baselines/colmap/metric/fused_metric.ply`."""
    t0 = time.time()
    ratio = float(cfgmod.require(cfg, "align.ransac.max_error_ratio"))
    min_pairs = int(cfgmod.require(cfg, "align.min_pairs"))
    cks = sorted(p for p in layout.vggt.glob("chunk_*") if (p / "vggt_raw.npz").is_file())
    if not cks:
        raise StageError(E_MISSING_INPUT, f"thiếu {layout.vggt}/chunk_XX: chạy stage vggt trước")
    cams = load_cameras(layout)
    out_dir = ensure_dir(layout.alignment)
    results = []
    for k in range(len(cks)):
        raw, _, meta = read_chunk(layout, k)
        r = align_chunk(vggt_centers(raw["extrinsic"]), [int(v) for v in meta["views"]], cams, ratio, min_pairs)
        r.update(chunk=k, start=meta["start"], end=meta["end"])
        write_json(out_dir / f"chunk_{k:02d}_sim3.json", r)
        results.append(r)
        log(f"[align] chunk {k:02d} ảnh [{r['start']}, {r['end']}): " + (
            f"s {r['s']:.4f}, {r['n_inliers']}/{r['n_pairs']} inlier, rmse {r['rmse']:.5f} đv COLMAP (ngưỡng {r['threshold']:.5f})" if r["accepted"]
            else f"BỊ LOẠI: {r['reason']}"))
    acc = [r for r in results if r["accepted"]]
    stats = {"ratio": ratio, "n_chunks": len(results), "n_accepted": len(acc), "rejected_chunks": [r["chunk"] for r in results if not r["accepted"]],
             "rmse_median": float(np.median([r["rmse"] for r in acc])) if acc else None,
             "rmse_max": float(max(r["rmse"] for r in acc)) if acc else None,
             "s_median": float(np.median([r["s"] for r in acc])) if acc else None}
    write_json(out_dir / "align_result.json", stats)
    log(f"[align] {len(acc)}/{len(results)} chunk được nhận; rmse tâm camera trung vị {stats['rmse_median']}, lớn nhất {stats['rmse_max']} đv COLMAP")
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

