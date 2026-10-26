#!/usr/bin/env python3
"""
faro_align.py — căn point cloud Faro vào hệ toạ độ scene ARKitScenes (kế hoạch §4.0d, M0b).

KHÔNG có ngưỡng chấp nhận nào trong mã: script luôn in số liệu thật và dừng ở bước báo cáo; bản chính thức chỉ được
ghi bằng `--commit` sau khi người dùng đọc báo cáo và đồng ý. Dừng tự động (mã thoát 2) chỉ khi gặp lỗi khách quan
(cặp scan không trùng, không hội tụ, không giao nhau...), kèm số thật.

Pha 1 (kiểm giả thuyết về dữ liệu Faro, chỉ đọc raw; --phase 1):
  - các scan cùng `_pose.txt` có trùng xyz HOÀN TOÀN không (so từng byte toàn bộ điểm)
  - `.ply` đã ở hệ chung (giả thuyết A) hay phải áp `_pose.txt` (B1–B4): so khoảng cách láng giềng gần nhất giữa các scan khác pose

Cách chạy (từ thư mục gốc repo, trong env 3d_metric):
    python scripts/faro_align.py --scene arkitscenes/42444738 --phase 1

Mã thoát: 0 ok (đã in số liệu); 1 lỗi đầu vào (scene held-out, thiếu dữ liệu...); 2 dừng vì dữ liệu không như giả thuyết.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import pipeline  # noqa: E402,F401  (import torch trước cv2/open3d/pycolmap)

# isort: split
import adapters  # noqa: E402
import faro_registration as frs  # noqa: E402
import numpy as np  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

from pipeline.common import io as pio  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402

RAW_REL = Path("data") / "raw" / "arkitscenes"
SCENES_REL = Path("data") / "scenes"
VOXEL_CACHE = 0.02            # m, voxel của cache scan (kế hoạch: 2 cm)


class StopError(RuntimeError):
    """Dữ liệu không như giả thuyết: dừng và báo số thật (mã thoát 2), không tự chọn."""


# ---------------------------------------------------------------------------
# Scene, chặn held-out
# ---------------------------------------------------------------------------


def resolve_scene(root: Path, scene: str) -> Dict:
    """`arkitscenes/<video_id>` → thông tin scene. Chỉ nhận train/val; held-out → HeldoutError."""
    try:
        dataset, vid = scene.split("/", 1)
    except ValueError:
        raise ValueError(f"--scene cần dạng arkitscenes/<video_id>, nhận {scene!r}")
    if dataset != "arkitscenes":
        raise ValueError(f"chưa hỗ trợ dataset {dataset!r}")
    splits_csv = root / "data" / "splits.csv"
    splits = sp.load_splits(splits_csv)                 # kiểm splits.lock
    if splits.get(vid) == sp.SPLIT_HELDOUT:
        raise sp.HeldoutError(f"scene {vid} là held-out: không căn/chấm Faro ở bước này (chạy đúng một lần)")
    if vid not in splits:
        raise ValueError(f"scene {vid} không có trong splits.csv")
    row = next(r for r in sp.read_rows(splits_csv) if r["video_id"] == vid)
    split_dir = "Validation" if splits[vid] == sp.SPLIT_VAL else "Training"
    layout = pio.scene_layout(root / SCENES_REL, dataset, vid)
    return {"video_id": vid, "visit_id": row["visit_id"], "split": splits[vid],
            "raw_dir": root / RAW_REL / split_dir / vid, "faro_dir": root / RAW_REL / "laser_scanner_point_clouds" / row["visit_id"],
            "layout": layout}


# ---------------------------------------------------------------------------
# Pha 1a: các scan cùng pose có trùng xyz hoàn toàn không
# ---------------------------------------------------------------------------


def group_by_pose(scans: List[Dict]) -> List[List[Dict]]:
    """Nhóm các scan có `_pose.txt` giống hệt (so từng số)."""
    groups: List[List[Dict]] = []
    for s in scans:
        for g in groups:
            if np.array_equal(g[0]["pose"], s["pose"]):
                g.append(s)
                break
        else:
            groups.append([s])
    return groups


def compare_scans_exact(path_a: Path, path_b: Path, chunk: int = 2_000_000) -> Dict:
    """So từng điểm hai PLY cùng cấu trúc: xyz (toàn bộ, so bit), và các cột còn lại. Không nạp cả file."""
    ha, hb = adapters.read_ply_header(path_a), adapters.read_ply_header(path_b)
    out = {"n_a": ha["n"], "n_b": hb["n"], "same_dtype": ha["dtype"] == hb["dtype"]}
    if ha["n"] != hb["n"] or ha["dtype"] != hb["dtype"]:
        out.update(xyz_mismatch_points=None, xyz_identical=False)
        return out
    ma = np.memmap(path_a, dtype=ha["dtype"], mode="r", offset=ha["offset"], shape=(ha["n"],))
    mb = np.memmap(path_b, dtype=hb["dtype"], mode="r", offset=hb["offset"], shape=(hb["n"],))
    mism_xyz, max_abs = 0, 0.0
    mism_other = {n: 0 for n in ha["names"] if n not in ("x", "y", "z")}
    for a in range(0, ha["n"], chunk):
        ca, cb = ma[a:a + chunk], mb[a:a + chunk]
        bad = np.zeros(len(ca), dtype=bool)
        for ax in "xyz":
            diff = ca[ax] != cb[ax]
            bad |= diff
            if diff.any():
                max_abs = max(max_abs, float(np.abs(ca[ax][diff] - cb[ax][diff]).max()))
        mism_xyz += int(bad.sum())
        for name in mism_other:
            mism_other[name] += int((ca[name] != cb[name]).sum())
    del ma, mb
    out.update(xyz_mismatch_points=mism_xyz, xyz_identical=mism_xyz == 0, xyz_max_abs_diff_m=max_abs,
               other_columns_mismatch_points=mism_other)
    return out


# ---------------------------------------------------------------------------
# Cache voxel của từng scan
# ---------------------------------------------------------------------------


def scan_voxels(scan: Dict, cache_dir: Path, voxel: float = VOXEL_CACHE) -> np.ndarray:
    """Điểm Faro (hệ `.ply`) voxel hoá 2 cm, streaming; cache `.npz` (float64) để chạy lại không phải đọc 1,8 GB."""
    cache = cache_dir / f"faro_voxel_{int(round(voxel * 1000))}mm_{scan['scan_id']}.npz"
    if cache.is_file():
        z = np.load(cache)
        if int(z["n_points_source"]) == scan["n_points"] and float(z["voxel"]) == voxel:
            return z["xyz"]
    t0 = time.time()
    cen, cnt = adapters.voxel_downsample_stream(adapters.iter_ply_xyz(scan["ply"]), voxel)
    cache_dir.mkdir(parents=True, exist_ok=True)
    np.savez(cache, xyz=cen, count=cnt, voxel=voxel, n_points_source=scan["n_points"])
    print(f"    [cache] {scan['scan_id']}: {scan['n_points']:,} điểm → {len(cen):,} voxel {voxel * 100:g} cm "
          f"({time.time() - t0:.0f} s) → {cache.name}", flush=True)
    return cen


# ---------------------------------------------------------------------------
# Pha 1b: ý nghĩa của `_pose.txt`
# ---------------------------------------------------------------------------


def apply_variant(pts: np.ndarray, pose: np.ndarray, variant: str) -> np.ndarray:
    """A: giữ nguyên. B1: p' = [p 1]·M (vector hàng). B2: ngược của B1. B3: p' = R·p + t (R = 3 dòng đầu, t = dòng cuối).
    B4: ngược của B3."""
    r, t = pose[:3, :3], pose[3, :3]
    if variant == "A":
        return pts
    if variant == "B1":
        return pts @ r + t
    if variant == "B2":
        return (pts - t) @ r.T
    if variant == "B3":
        return pts @ r.T + t
    if variant == "B4":
        return (pts - t) @ r
    raise ValueError(variant)


VARIANTS = ("A", "B1", "B2", "B3", "B4")


def nn_stats(src: np.ndarray, dst: np.ndarray, max_query: int = 300_000, seed: int = 0) -> Dict:
    """Khoảng cách láng giềng gần nhất từ (mẫu của) src đến dst (m)."""
    rng = np.random.default_rng(seed)
    q = src if len(src) <= max_query else src[rng.choice(len(src), max_query, replace=False)]
    d, _ = cKDTree(dst).query(q, k=1)
    pct = np.percentile(d, [25, 50, 75, 90])
    return {"n_query": int(len(q)), "p25": float(pct[0]), "median": float(pct[1]), "p75": float(pct[2]), "p90": float(pct[3]),
            "frac_le_2cm": float((d <= 0.02).mean()), "frac_le_5cm": float((d <= 0.05).mean()),
            "frac_le_10cm": float((d <= 0.10).mean())}


def scanner_footprint(pts: np.ndarray, pose: np.ndarray) -> Dict:
    """Vị trí `pose[3,:3]` có nằm trong chính point cloud như vị trí máy quét không (giả thuyết A)?"""
    t = pose[3, :3]
    rel = pts - t
    horiz = np.hypot(rel[:, 0], rel[:, 1])
    near = horiz < 10.0
    az = np.degrees(np.arctan2(rel[near, 1], rel[near, 0])) % 360
    bins = np.histogram(az, bins=36, range=(0, 360))[0]
    return {"scanner_xyz": [float(v) for v in t], "n_voxels": int(len(pts)),
            "xyz_min": [float(v) for v in pts.min(0)], "xyz_max": [float(v) for v in pts.max(0)],
            "horiz_dist_min_m": float(horiz.min()), "horiz_dist_p1_m": float(np.percentile(horiz, 1)),
            "dz_p1_m": float(np.percentile(rel[:, 2], 1)), "dz_p50_m": float(np.percentile(rel[:, 2], 50)),
            "dz_p99_m": float(np.percentile(rel[:, 2], 99)),
            "azimuth_bins_occupied_of_36": int((bins > 0).sum())}


def phase1(info: Dict, out_dir: Path) -> Dict:
    scans = adapters.list_scans(info["faro_dir"])
    report: Dict = {"visit_id": info["visit_id"], "scans": [], "groups": [], "pairs_exact": [], "footprint": {}, "overlap": {}}
    print(f"[pha 1] visit {info['visit_id']}: {len(scans)} scan")
    for s in scans:
        report["scans"].append({"scan_id": s["scan_id"], "n_points": s["n_points"], "pose": s["pose"].tolist()})
        print(f"  scan {s['scan_id']}: {s['n_points']:,} điểm; tịnh tiến pose (dòng cuối) = {s['pose'][3, :3]}")
    groups = group_by_pose(scans)
    report["groups"] = [[s["scan_id"] for s in g] for g in groups]
    print(f"[pha 1a] nhóm theo `_pose.txt` giống hệt: {report['groups']}")

    # 1a: các cặp trùng pose có trùng xyz hoàn toàn không
    for g in groups:
        for other in g[1:]:
            t0 = time.time()
            res = compare_scans_exact(g[0]["ply"], other["ply"])
            res.update(scan_a=g[0]["scan_id"], scan_b=other["scan_id"])
            report["pairs_exact"].append(res)
            print(f"  {g[0]['scan_id']} vs {other['scan_id']}: n {res['n_a']:,}/{res['n_b']:,}; xyz khác nhau ở "
                  f"{res['xyz_mismatch_points']} điểm; cột khác: {res.get('other_columns_mismatch_points')} ({time.time() - t0:.0f} s)",
                  flush=True)
    bad = [r for r in report["pairs_exact"] if not r["xyz_identical"]]
    if bad:
        raise StopError("cặp scan cùng pose KHÔNG trùng xyz hoàn toàn: "
                        + "; ".join(f"{r['scan_a']}~{r['scan_b']} khác {r['xyz_mismatch_points']} điểm (max |Δ| "
                                    f"{r.get('xyz_max_abs_diff_m')} m)" for r in bad))

    # 1b: dùng 1 scan đại diện cho mỗi nhóm pose
    reps = [g[0] for g in groups]
    vox = {s["scan_id"]: scan_voxels(s, out_dir) for s in reps}
    for s in reps:
        report["footprint"][s["scan_id"]] = scanner_footprint(vox[s["scan_id"]], s["pose"])
        f = report["footprint"][s["scan_id"]]
        print(f"[pha 1b] {s['scan_id']}: máy quét tại {np.round(f['scanner_xyz'], 2)}, bbox z [{f['xyz_min'][2]:.2f}; {f['xyz_max'][2]:.2f}]; "
              f"khoảng cách ngang gần nhất tới vị trí đó {f['horiz_dist_min_m']:.2f} m; dz p1/p50/p99 = "
              f"{f['dz_p1_m']:.2f}/{f['dz_p50_m']:.2f}/{f['dz_p99_m']:.2f} m; {f['azimuth_bins_occupied_of_36']}/36 hướng có điểm")
    print("[pha 1b] khoảng cách láng giềng gần nhất giữa các scan khác pose (m), mẫu ≤ 300k điểm:")
    print(f"  {'cặp':>14} {'giả thuyết':>10} | {'p25':>8} {'trung vị':>9} {'p75':>8} {'p90':>8} | ≤2cm  ≤5cm  ≤10cm")
    for i in range(len(reps)):
        for j in range(len(reps)):
            if i == j:
                continue
            a, b = reps[i], reps[j]
            key = f"{a['scan_id']}->{b['scan_id']}"
            report["overlap"][key] = {}
            for v in VARIANTS:
                st = nn_stats(apply_variant(vox[a["scan_id"]], a["pose"], v), apply_variant(vox[b["scan_id"]], b["pose"], v))
                report["overlap"][key][v] = st
                print(f"  {key:>14} {v:>10} | {st['p25']:8.4f} {st['median']:9.4f} {st['p75']:8.4f} {st['p90']:8.3f} | "
                      f"{st['frac_le_2cm']:.2f}  {st['frac_le_5cm']:.2f}  {st['frac_le_10cm']:.2f}")
    return report


# ---------------------------------------------------------------------------
# Pha 2: Faro hợp nhất (các scan duy nhất, hệ `.ply` đã là hệ chung — kiểm ở pha 1)
# ---------------------------------------------------------------------------


def require_phase1(out_dir: Path) -> Dict:
    """Bắt buộc đã chạy pha 1 và các cặp cùng pose trùng xyz hoàn toàn; nếu không thì dừng (không đoán)."""
    p = out_dir / "phase1_report.json"
    if not p.is_file():
        raise StopError(f"chưa có {p.name}: chạy `--phase 1` trước")
    rep = json.loads(p.read_text(encoding="utf-8"))
    bad = [r for r in rep["pairs_exact"] if not r["xyz_identical"]]
    if bad:
        raise StopError("pha 1 ghi cặp scan cùng pose không trùng xyz hoàn toàn: " + str([(r["scan_a"], r["scan_b"]) for r in bad]))
    return rep


def load_faro_merged(info: Dict, out_dir: Path, rep1: Dict, voxel: float) -> Tuple[np.ndarray, List[str]]:
    """Gộp 1 scan đại diện của mỗi nhóm pose (bỏ bản trùng xyz để không đếm đôi), voxel hoá `voxel` (m)."""
    scans = {s["scan_id"]: s for s in adapters.list_scans(info["faro_dir"])}
    reps = [g[0] for g in rep1["groups"]]
    parts = [scan_voxels(scans[r], out_dir, voxel) for r in reps]
    cen, _ = adapters.voxel_downsample_stream(iter(parts), voxel)
    return cen, reps


# ---------------------------------------------------------------------------
# Pha 3: cloud đích từ highres_depth và kiểm quy ước (so với mesh ARKit, độc lập với Faro)
# ---------------------------------------------------------------------------

HIGHRES_SIZE = (1920, 1440)


def geometry_variants() -> List[Dict]:
    out = []
    for cam in ("opencv", "opengl"):
        for interp in (True, False):
            for intr, off in (("proportional", 0.5), ("pixel_center", 0.0)):
                out.append({"cam": cam, "interpolate": interp, "intrinsics": intr, "pixel_offset": off})
    return out


def variant_name(v: Dict) -> str:
    return f"{v['cam']}/{'interp' if v['interpolate'] else 'nearest'}/{v['intrinsics']}"


class HighresSource:
    """Mở một lần các asset của scene: highres_depth, vga_wide_intrinsics, .traj."""

    def __init__(self, raw_dir: Path):
        self.raw_dir = raw_dir
        self.depth = adapters.AssetReader(str(raw_dir), "highres_depth")
        self.intr_reader = adapters.AssetReader(str(raw_dir), "vga_wide_intrinsics")
        if not (self.depth.exists() and self.intr_reader.exists()):
            raise FileNotFoundError(f"thiếu highres_depth hoặc vga_wide_intrinsics trong {raw_dir}")
        self.traj = adapters.Trajectory.from_file(raw_dir / "lowres_wide.traj")
        self.intr = adapters.read_intrinsics(self.intr_reader)
        self.intr_ts = np.array(sorted(self.intr))
        self.entries = sorted(self.depth.list_pngs(), key=adapters.frame_timestamp)
        self.ts = np.array([adapters.frame_timestamp(e) for e in self.entries])

    def close(self):
        self.depth.close()
        self.intr_reader.close()

    def frame_points(self, i: int, variant: Dict, stride: int, dtype=np.float32) -> np.ndarray:
        ts = float(self.ts[i])
        p = self.intr[float(self.intr_ts[int(np.argmin(np.abs(self.intr_ts - ts)))])]
        k = adapters.intrinsics_matrix(adapters.scale_intrinsics(p, *HIGHRES_SIZE, variant["intrinsics"]))
        depth = self.depth.read(self.entries[i])
        t_wc = self.traj.pose_wc(ts, interpolate=variant["interpolate"])
        return adapters.unproject_depth(depth, k, t_wc, stride=stride, cam_convention=variant["cam"],
                                        pixel_offset=variant["pixel_offset"], dtype=dtype)


def load_mesh_vertices(raw_dir: Path, video_id: str) -> np.ndarray:
    import open3d as o3d
    m = o3d.io.read_triangle_mesh(str(raw_dir / f"{video_id}_3dod_mesh.ply"))
    v = np.asarray(m.vertices, dtype=np.float64)
    if len(v) == 0:
        raise FileNotFoundError("mesh ARKit rỗng")
    return v


def geometry_check(src: HighresSource, mesh_v: np.ndarray, stride: int = 16) -> List[Dict]:
    """So 8 phương án (trục camera × nội suy × quy ước tâm pixel) bằng khoảng cách điểm highres_depth → đỉnh mesh ARKit."""
    tree = cKDTree(mesh_v)
    rows = []
    for v in geometry_variants():
        pts = np.concatenate([src.frame_points(i, v, stride) for i in range(len(src.entries))]).astype(np.float64)
        d, _ = tree.query(pts, k=1, workers=-1)
        st = frs.distance_stats(d)
        st.update(variant=variant_name(v), params=v)
        rows.append(st)
    return rows


def build_target_frames(src: HighresSource, variant: Dict, stride: int, voxel: float) -> List[np.ndarray]:
    """Mỗi khung: điểm world (m), thưa theo voxel trong khung. Dùng cho thống kê theo khung và chia đôi."""
    out = []
    for i in range(len(src.entries)):
        pts = src.frame_points(i, variant, stride, dtype=np.float64)
        cen, _ = adapters.voxel_downsample_stream(iter([pts]), voxel)
        out.append(cen)
    return out


def merge_frames(frames: List[np.ndarray], voxel: float) -> np.ndarray:
    cen, _ = adapters.voxel_downsample_stream(iter(frames), voxel)
    return cen


# ---------------------------------------------------------------------------
# Pha 4–6: căn thô, tinh chỉnh, báo cáo
# ---------------------------------------------------------------------------


def estimate_normals(pts: np.ndarray, radius: float) -> np.ndarray:
    import open3d as o3d
    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(pts)
    pc.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=radius, max_nn=30))
    return np.asarray(pc.normals)


ICP_LEVELS = [(0.08, 0.30), (0.04, 0.15), (0.02, 0.08), (0.01, 0.04)]   # (voxel, max_corr) m — tham số thuật toán, không phải ngưỡng chấp nhận


def crop_box(pts: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    return pts[np.all((pts >= lo) & (pts <= hi), axis=1)]


def refine_icp(target_merged_1cm: np.ndarray, faro_1cm: np.ndarray, t_coarse: np.ndarray, margin: float = 1.0) -> Dict:
    """ICP đa tỉ lệ: query = đích (hệ scene), ref = Faro đã đặt vào hệ scene bằng t_coarse. Trả về T_faro→scene."""
    f_scene = frs.apply_T(t_coarse, faro_1cm)
    lo, hi = target_merged_1cm.min(axis=0) - margin, target_merged_1cm.max(axis=0) + margin
    keep = np.all((f_scene >= lo) & (f_scene <= hi), axis=1)
    f_scene = f_scene[keep]
    if len(f_scene) < 1000:
        raise StopError(f"Faro và cloud đích gần như không giao nhau sau căn thô ({len(f_scene)} điểm Faro trong hộp bao đích ± {margin} m)")
    T = np.eye(4)
    levels = []
    for voxel, max_corr in ICP_LEVELS:
        q, _ = adapters.voxel_downsample_stream(iter([target_merged_1cm]), voxel) if voxel > 0.01 else (target_merged_1cm, None)
        r_pts, _ = adapters.voxel_downsample_stream(iter([f_scene]), voxel) if voxel > 0.01 else (f_scene, None)
        nrm = estimate_normals(r_pts, radius=max(0.05, 3 * voxel))
        res = frs.icp_point_to_plane(q, r_pts, nrm, T, max_corr)
        T = res["T"]
        info = {k: v for k, v in res.items() if k != "T"}
        info.update(voxel=voxel, max_corr=max_corr, n_query=int(len(q)), n_ref=int(len(r_pts)))
        levels.append(info)
        if res["fitness"] == 0.0 and res.get("reason", "").startswith("chỉ"):
            break
    # T: scene → (Faro trong hệ scene theo t_coarse). Faro→scene = T⁻¹ · t_coarse
    t_f2s = frs.invert_T(T) @ t_coarse
    return {"T_faro_to_scene": t_f2s, "T_correction_scene": T, "levels": levels}


def fpfh_crosscheck(target_merged: np.ndarray, faro: np.ndarray, t_coarse: np.ndarray, seed: int = 0) -> Dict:
    """Căn toàn cục độc lập (FPFH + RANSAC của Open3D, 6 DoF) để xem có cùng bồn hút với căn thô 4 DoF không (chỉ báo cáo)."""
    import open3d as o3d
    voxel = 0.05
    f_scene = frs.apply_T(t_coarse, faro)
    lo, hi = target_merged.min(axis=0) - 1.0, target_merged.max(axis=0) + 1.0
    f_crop = f_scene[np.all((f_scene >= lo) & (f_scene <= hi), axis=1)]
    # Cho Faro về hệ gốc của nó để RANSAC không biết trước căn thô
    f_orig = frs.apply_T(frs.invert_T(t_coarse), f_crop)

    def prep(p):
        pc = o3d.geometry.PointCloud()
        pc.points = o3d.utility.Vector3dVector(p)
        pc = pc.voxel_down_sample(voxel)
        pc.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel * 2, max_nn=30))
        fp = o3d.pipelines.registration.compute_fpfh_feature(pc, o3d.geometry.KDTreeSearchParamHybrid(radius=voxel * 5, max_nn=100))
        return pc, fp
    o3d.utility.random.seed(seed)
    src, fs = prep(f_orig)
    dst, fd = prep(target_merged)
    res = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
        src, dst, fs, fd, True, voxel * 1.5, o3d.pipelines.registration.TransformationEstimationPointToPoint(False), 3,
        [o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
         o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(voxel * 1.5)],
        o3d.pipelines.registration.RANSACConvergenceCriteria(400000, 0.999))
    t = np.asarray(res.transformation)
    diff = frs.transform_difference(t_coarse, t, f_orig)
    return {"fitness": float(res.fitness), "inlier_rmse": float(res.inlier_rmse), "T": t,
            "tilt_deg": frs.tilt_deg(t[:3, :3]), "yaw_deg": frs.yaw_deg(t[:3, :3]),
            "diff_vs_coarse": diff}


def topdown_image(path: Path, a_pts: np.ndarray, b_pts: np.ndarray, cell: float = 0.02, max_side: int = 1800) -> None:
    """Ảnh nhìn từ trên xuống: a = đỏ, b = xanh, chồng khít = tím/trắng."""
    import cv2
    allp = np.concatenate([a_pts[:, :2], b_pts[:, :2]])
    lo, hi = allp.min(axis=0) - 0.2, allp.max(axis=0) + 0.2
    cell = max(cell, float((hi - lo).max()) / max_side)
    shape = tuple(int(v) for v in np.ceil((hi - lo) / cell).astype(int)[::-1] + 1)
    ia = frs.raster(a_pts[:, :2], lo, shape, cell)
    ib = frs.raster(b_pts[:, :2], lo, shape, cell)
    img = np.zeros(shape + (3,), dtype=np.uint8)
    img[..., 2] = (ia * 255).astype(np.uint8)       # BGR: đỏ = a
    img[..., 0] = (ib * 255).astype(np.uint8)       # xanh = b
    img = img[::-1]
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)


def residual_report(target_frames: List[np.ndarray], faro_scene: np.ndarray, faro_normals: np.ndarray, mesh_v: np.ndarray) -> Dict:
    tree = cKDTree(faro_scene)
    rep: Dict = {}
    all_d, all_r, per_frame = [], [], []
    for i, pts in enumerate(target_frames):
        d, idx = tree.query(pts, k=1, workers=-1)
        r = np.abs(((pts - faro_scene[idx]) * faro_normals[idx]).sum(axis=1))
        all_d.append(d)
        all_r.append(r)
        per_frame.append({"frame": i, "n": int(len(pts)), "median_nn_m": float(np.median(d)), "median_plane_m": float(np.median(r))})
    rep["target_to_faro_nn"] = frs.distance_stats(np.concatenate(all_d))
    rep["target_to_faro_plane"] = frs.distance_stats(np.concatenate(all_r))
    rep["per_frame"] = per_frame
    dm, _ = tree.query(mesh_v, k=1, workers=-1)
    rep["mesh_to_faro_nn_all_vertices"] = frs.distance_stats(dm)
    near = dm <= 0.5
    rep["mesh_to_faro_nn_vertices_within_0.5m"] = frs.distance_stats(dm[near])
    rep["mesh_vertices_within_0.5m_fraction"] = float(near.mean())
    return rep


def print_stats(label: str, st: Dict, unit_cm: bool = True) -> None:
    if not st.get("n"):
        print(f"  {label}: (không có dữ liệu)")
        return
    f = 100 if unit_cm else 1
    u = "cm" if unit_cm else "m"
    print(f"  {label}: n={st['n']:,}; trung bình {st['mean'] * f:.2f}, trung vị {st['median'] * f:.2f}, p90 {st['p90'] * f:.2f}, "
          f"p95 {st['p95'] * f:.2f}, p99 {st['p99'] * f:.2f}, max {st['max'] * f:.1f} {u}; ≤1cm {st['frac_le_1cm']:.2f}, "
          f"≤2cm {st['frac_le_2cm']:.2f}, ≤5cm {st['frac_le_5cm']:.2f}")


def decompose(T: np.ndarray) -> Dict:
    return {"yaw_deg": frs.yaw_deg(T[:3, :3]), "tilt_deg": frs.tilt_deg(T[:3, :3]), "translation_m": [float(v) for v in T[:3, 3]]}


def git_head(root: Path) -> str:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "?"


def run_alignment(info: Dict, out_dir: Path, args) -> int:
    root = Path(args.root)
    rep1 = require_phase1(out_dir)
    print(f"[pha 1] đã có báo cáo: {len(rep1['groups'])} nhóm pose, cặp trùng xyz hoàn toàn; giả thuyết A (`.ply` đã ở hệ chung)")
    t0 = time.time()
    src = HighresSource(info["raw_dir"])
    try:
        print(f"[pha 3] {len(src.entries)} khung highres_depth; pose {len(src.traj)} dòng, khoảng cách pose lớn nhất quanh khung: "
              f"{max(src.traj.gap_at(float(t)) for t in src.ts):.3f} s")
        mesh_v = load_mesh_vertices(info["raw_dir"], info["video_id"])
        rows = geometry_check(src, mesh_v)
        print("[pha 3] khoảng cách điểm highres_depth → đỉnh mesh ARKit (cm), mẫu mọi khung, bước 16 px:")
        for r in sorted(rows, key=lambda r: r["median"]):
            print(f"    {r['variant']:<34} trung vị {r['median'] * 100:6.2f}  p90 {r['p90'] * 100:7.2f}  p99 {r['p99'] * 100:8.1f}  "
                  f"≤2cm {r['frac_le_2cm']:.2f}  ≤5cm {r['frac_le_5cm']:.2f}")
        best = min(rows, key=lambda r: r["median"])
        variant = best["params"]
        print(f"[pha 3] chọn phương án có trung vị nhỏ nhất: {best['variant']} (không phải ngưỡng chấp nhận)")

        frames = build_target_frames(src, variant, stride=4, voxel=0.01)
        target = merge_frames(frames, 0.01)
        print(f"[pha 3] cloud đích: {sum(len(f) for f in frames):,} điểm theo khung → {len(target):,} voxel 1 cm; "
              f"bbox {np.round(target.min(0), 2)} … {np.round(target.max(0), 2)}")
    finally:
        src.close()

    faro, reps = load_faro_merged(info, out_dir, rep1, 0.01)
    print(f"[pha 2] Faro hợp nhất {reps}: {len(faro):,} voxel 1 cm; z từ {faro[:, 2].min():.2f} đến {faro[:, 2].max():.2f}")

    # --- căn thô ---
    scanner_xy = np.mean([np.array(s["pose"])[3, :2] for s in rep1["scans"]], axis=0)
    near = np.hypot(faro[:, 0] - scanner_xy[0], faro[:, 1] - scanner_xy[1]) <= args.faro_radius
    faro_c = faro[near]
    fs_mask = frs.structure_mask(faro_c)
    ts_mask = frs.structure_mask(target)
    print(f"[pha 4] điểm cấu trúc đứng: Faro {int(fs_mask.sum()):,}/{len(faro_c):,} (bán kính {args.faro_radius} m quanh máy quét), đích {int(ts_mask.sum()):,}/{len(target):,}")
    co = frs.coarse_yaw_xy(faro_c[fs_mask], target[ts_mask])
    t_xy = co["T"]
    moved = frs.apply_T(t_xy, faro_c)
    cz = frs.coarse_z(moved, target)
    t_coarse = frs.make_T(t_xy[:3, :3], t_xy[:3, 3] + np.array([0.0, 0.0, cz["tz"]]))
    sp2 = co["second_peak"]
    print(f"[pha 4] căn thô: yaw {co['yaw_deg']:.2f}°, điểm {co['score']:.3f} (tỉ lệ ô đích trùng); đỉnh yaw thứ hai (≥10° xa) {sp2['yaw_deg']:.1f}° điểm {sp2['score']:.3f}; "
          f"tz {cz['tz']:.3f} m (tương quan z {cz['score']:.3f}); tịnh tiến {np.round(t_coarse[:3, 3], 3)}")
    topdown_image(info["layout"].logs / "faro_align_topdown_coarse.png", frs.apply_T(t_coarse, faro_c), target)

    fp = None
    if not args.skip_fpfh:
        fp = fpfh_crosscheck(target, faro_c, t_coarse)
        print(f"[pha 4] cross-check FPFH+RANSAC (6 DoF, độc lập): fitness {fp['fitness']:.3f}, inlier rmse {fp['inlier_rmse'] * 100:.2f} cm, "
              f"yaw {fp['yaw_deg']:.2f}°, nghiêng {fp['tilt_deg']:.2f}°; lệch so với căn thô: xoay {fp['diff_vs_coarse']['rotation_deg']:.2f}°, "
              f"dời điểm rms {fp['diff_vs_coarse']['point_rms_m'] * 100:.2f} cm")

    # --- tinh chỉnh ---
    ref = refine_icp(target, faro, t_coarse)
    t_final = ref["T_faro_to_scene"]
    print("[pha 5] ICP point-to-plane đa tỉ lệ (query = đích, ref = Faro), scale cố định 1, 6 DoF:")
    for lv in ref["levels"]:
        print(f"    voxel {lv['voxel'] * 100:g} cm, max_corr {lv['max_corr'] * 100:g} cm: n_query {lv['n_query']:,}, fitness {lv['fitness']:.4f}, "
              f"inlier rmse {lv['inlier_rmse'] * 100:.3f} cm, rmse mặt phẳng {lv['rmse_plane'] * 100:.3f} cm, {lv['iterations']} vòng, "
              f"hội tụ theo dung sai: {lv['converged']} ({lv['reason']})")
    dec = decompose(t_final)
    print(f"[pha 5] Faro→scene: yaw {dec['yaw_deg']:.3f}°, nghiêng so với trục đứng {dec['tilt_deg']:.3f}°, tịnh tiến {np.round(dec['translation_m'], 4)}")
    faro_room = faro[np.all((frs.apply_T(t_final, faro) >= target.min(axis=0) - 1.0)
                            & (frs.apply_T(t_final, faro) <= target.max(axis=0) + 1.0), axis=1)]
    d_coarse = frs.transform_difference(t_coarse, t_final, faro_room)
    print(f"        so với căn thô (trên {d_coarse['n_points']:,} điểm Faro trong phòng): xoay {d_coarse['rotation_deg']:.3f}°, "
          f"dời điểm rms {d_coarse['point_rms_m'] * 100:.2f} cm, p95 {d_coarse['point_p95_m'] * 100:.2f} cm, max {d_coarse['point_max_m'] * 100:.2f} cm")

    # --- báo cáo residual ---
    f_scene = frs.apply_T(t_final, faro)
    lo, hi = target.min(axis=0) - 1.0, target.max(axis=0) + 1.0
    box = np.all((f_scene >= lo) & (f_scene <= hi), axis=1)
    f_box = f_scene[box]
    nrm = estimate_normals(f_box, radius=0.05)
    rep = residual_report(frames, f_box, nrm, mesh_v)
    print("[pha 6] residual (không phán xét):")
    print_stats("đích → Faro, khoảng cách điểm gần nhất (cm)", rep["target_to_faro_nn"])
    print_stats("đích → Faro, khoảng cách tới mặt phẳng (cm)", rep["target_to_faro_plane"])
    print_stats("mesh ARKit (độc lập highres_depth) → Faro, mọi đỉnh (cm)", rep["mesh_to_faro_nn_all_vertices"])
    print_stats(f"mesh ARKit → Faro, đỉnh cách Faro ≤ 0,5 m ({rep['mesh_vertices_within_0.5m_fraction']:.2f} số đỉnh) (cm)",
                rep["mesh_to_faro_nn_vertices_within_0.5m"])
    pf = sorted(rep["per_frame"], key=lambda r: -r["median_plane_m"])
    print(f"  theo khung (trung vị khoảng cách mặt phẳng, cm): tệ nhất {[(r['frame'], round(r['median_plane_m'] * 100, 2)) for r in pf[:5]]}; "
          f"trung vị các khung {np.median([r['median_plane_m'] for r in pf]) * 100:.2f}; tốt nhất {pf[-1]['median_plane_m'] * 100:.2f}")

    # --- ổn định hai nửa ---
    folds = {}
    for name, sel in (("chan", slice(0, None, 2)), ("le", slice(1, None, 2))):
        sub = merge_frames(frames[sel], 0.01)
        lv = ICP_LEVELS[-1]
        r_pts = f_box
        nrm_f = nrm
        res = frs.icp_point_to_plane(sub, r_pts, nrm_f, np.eye(4), lv[1])
        folds[name] = res
    t_a = frs.invert_T(folds["chan"]["T"]) @ t_final
    t_b = frs.invert_T(folds["le"]["T"]) @ t_final
    fold_diff = frs.transform_difference(t_a, t_b, faro_room)
    fold_vs_final = [frs.transform_difference(t_final, t, faro_room) for t in (t_a, t_b)]
    print(f"[pha 6] ổn định hai nửa (khớp lại mức 1 cm trên khung chẵn / lẻ, xuất phát từ kết quả chung): "
          f"hai nghiệm lệch nhau: xoay {fold_diff['rotation_deg']:.4f}°; độ dời của điểm Faro trong phòng rms {fold_diff['point_rms_m'] * 100:.3f} cm, "
          f"p95 {fold_diff['point_p95_m'] * 100:.3f} cm, max {fold_diff['point_max_m'] * 100:.3f} cm; "
          f"mỗi nửa so với nghiệm chung: rms {fold_vs_final[0]['point_rms_m'] * 100:.3f} / {fold_vs_final[1]['point_rms_m'] * 100:.3f} cm; "
          f"rmse mặt phẳng chẵn {folds['chan']['rmse_plane'] * 100:.3f} cm, lẻ {folds['le']['rmse_plane'] * 100:.3f} cm")

    # --- từng khung tự căn lại: cho biết lỗi còn lại đến từ pose từng khung hay từ phép căn chung ---
    pf_fit = []
    for i, fpts in enumerate(frames):
        r = frs.icp_point_to_plane(fpts, f_box, nrm, np.eye(4), 0.08)
        pf_fit.append({"frame": i, "rotation_deg": frs.rotation_angle_deg(r["T"][:3, :3]),
                       "translation_cm": float(np.linalg.norm(r["T"][:3, 3]) * 100), "rmse_plane_cm": r["rmse_plane"] * 100,
                       "fitness": r["fitness"], "converged": bool(r["converged"]),
                       "before_median_plane_cm": rep["per_frame"][i]["median_plane_m"] * 100})
    arr = lambda k: np.array([p[k] for p in pf_fit])   # noqa: E731
    print(f"[pha 6] mỗi khung tự căn lại 6 DoF (max_corr 8 cm) vào Faro: hiệu chỉnh xoay trung vị {np.median(arr('rotation_deg')):.3f}° "
          f"(p90 {np.percentile(arr('rotation_deg'), 90):.3f}°, max {arr('rotation_deg').max():.3f}°), tịnh tiến trung vị {np.median(arr('translation_cm')):.2f} cm "
          f"(p90 {np.percentile(arr('translation_cm'), 90):.2f}, max {arr('translation_cm').max():.2f} cm); rmse mặt phẳng sau khi tự căn trung vị "
          f"{np.median(arr('rmse_plane_cm')):.2f} cm (trước: trung vị khoảng cách {np.median(arr('before_median_plane_cm')):.2f} cm); "
          f"không hội tụ ở {int((~arr('converged').astype(bool)).sum())}/{len(pf_fit)} khung")
    bad = sorted(pf_fit, key=lambda p: -p["translation_cm"])[:5]
    print(f"        khung lệch nhiều nhất: {[(p['frame'], round(p['translation_cm'], 2), round(p['rotation_deg'], 3)) for p in bad]} (khung, cm, độ)")
    topdown_image(info["layout"].logs / "faro_align_topdown_final.png", f_box, target)

    cand = {"status": "candidate", "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "scene": args.scene,
            "git_head": git_head(root), "script_sha256": _sha256(Path(__file__)),
            "T_faro_to_scene": t_final.tolist(), "decomposition": dec, "scale": 1.0,
            "pose_txt_hypothesis": "A: .ply đã ở hệ chung, _pose.txt không áp (pha 1)",
            "unique_scans_used": reps, "geometry_variant": best["variant"], "geometry_check": [{k: v for k, v in r.items() if k != "params"} for r in rows],
            "coarse": {"T": t_coarse.tolist(), "yaw_deg": co["yaw_deg"], "score": co["score"], "second_peak_yaw_deg": sp2["yaw_deg"],
                       "second_peak_score": sp2["score"], "tz": cz["tz"], "tz_score": cz["score"]},
            "fpfh_crosscheck": None if fp is None else {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in fp.items()},
            "per_frame_refit": pf_fit, "coarse_vs_final": d_coarse,
            "icp_levels": ref["levels"], "residual": rep, "two_fold": {"diff": fold_diff, "vs_final": fold_vs_final, "even": {k: v for k, v in folds["chan"].items() if k != "T"},
                                                                    "odd": {k: v for k, v in folds["le"].items() if k != "T"}},
            "params": {"icp_levels": ICP_LEVELS, "target_stride": 4, "target_voxel_m": 0.01, "faro_radius_m": args.faro_radius,
                       "note": "tham số thuật toán, không phải ngưỡng chấp nhận; không có ngưỡng chấp nhận trong mã"}}
    last = ref["levels"][-1]
    cand["icp_converged_finest_level"] = bool(last["converged"])
    pio.write_json(out_dir / "faro_to_scene.candidate.json", cand)
    print(f"[ghi] bản ỨNG VIÊN {out_dir / 'faro_to_scene.candidate.json'} ({time.time() - t0:.0f} s). Chưa có bản chính thức; "
          f"đọc báo cáo rồi mới chạy lại với --commit.")
    if not last["converged"]:
        raise StopError(f"ICP mức {last['voxel'] * 100:g} cm KHÔNG hội tụ theo dung sai: {last['reason']}; Δfitness cuối {last.get('last_delta_fitness')}, "
                        f"Δrmse cuối {last.get('last_delta_rmse')} m. Số liệu ở trên là thật; không tự đổi dung sai.")
    return 0


def _sha256(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ---------------------------------------------------------------------------
# Pha 8: --commit
# ---------------------------------------------------------------------------


def write_ply_xyz(path: Path, pts: np.ndarray) -> None:
    pts = np.asarray(pts, dtype=np.float32)
    header = (f"ply\nformat binary_little_endian 1.0\ncomment faro_align.py\nelement vertex {len(pts)}\n"
              f"property float x\nproperty float y\nproperty float z\nend_header\n").encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(header)
        f.write(pts.astype("<f4").tobytes())


def commit_candidate(info: Dict, out_dir: Path, args) -> int:
    cand_path = out_dir / "faro_to_scene.candidate.json"
    if not cand_path.is_file():
        print(f"[LỖI] chưa có {cand_path.name}: chạy căn (không --commit) và đọc báo cáo trước")
        return 1
    cand = json.loads(cand_path.read_text(encoding="utf-8"))
    if args.source == "faro" and not cand.get("icp_converged_finest_level", False):
        print("[LỖI] bản ứng viên có ICP mức cuối KHÔNG hội tụ: không ghi bản chính thức với --source faro "
              "(dự phòng bạn đã chọn: --source highres_depth)")
        return 2
    voxel = args.gt_voxel
    if args.source == "highres_depth":
        src = HighresSource(info["raw_dir"])
        try:
            variant = next(v for v in geometry_variants() if variant_name(v) == cand["geometry_variant"])
            frames = build_target_frames(src, variant, stride=4, voxel=voxel)
        finally:
            src.close()
        gt = merge_frames(frames, voxel)
        t = np.eye(4)
        note = "GT = cloud highres_depth (dự phòng); phủ một phần nên Comp bị lệch"
        reps = []
    else:
        t = np.array(cand["T_faro_to_scene"])
        scans = {s["scan_id"]: s for s in adapters.list_scans(info["faro_dir"])}
        reps = cand["unique_scans_used"]

        def chunks():
            for r in reps:
                for c in adapters.iter_ply_xyz(scans[r]["ply"]):
                    yield frs.apply_T(t, c)
        gt, _ = adapters.voxel_downsample_stream(chunks(), voxel)
        note = "GT = Faro (các scan duy nhất) đã căn vào hệ scene"
    final = {k: cand[k] for k in ("scene", "T_faro_to_scene", "decomposition", "scale", "unique_scans_used", "geometry_variant")}
    final.update(status="committed", source=args.source, note=note, gt_voxel_m=voxel, n_points=int(len(gt)),
                 candidate_sha256=_sha256(cand_path), committed=time.strftime("%Y-%m-%dT%H:%M:%S"),
                 residual_summary={"target_to_faro_plane": cand["residual"]["target_to_faro_plane"],
                                   "target_to_faro_nn": cand["residual"]["target_to_faro_nn"]})
    if args.source == "highres_depth":
        final["T_faro_to_scene"] = np.eye(4).tolist()
    write_ply_xyz(out_dir / "faro_scene_frame.ply", gt)
    pio.write_json(out_dir / "faro_to_scene.json", final)
    print(f"[OK] ghi {out_dir / 'faro_to_scene.json'} và faro_scene_frame.ply ({len(gt):,} điểm, voxel {voxel * 100:g} cm; {note})")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Căn Faro vào hệ scene (không có ngưỡng chấp nhận trong mã)")
    ap.add_argument("--scene", required=True, help="arkitscenes/<video_id>")
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--phase", type=int, default=0, help="1 = chỉ kiểm giả thuyết dữ liệu Faro; 0 (mặc định) = pha 2–7, ghi bản ứng viên")
    ap.add_argument("--commit", action="store_true", help="ghi bản chính thức từ bản ứng viên (chỉ sau khi đã đọc báo cáo và đồng ý)")
    ap.add_argument("--source", choices=("faro", "highres_depth"), default="faro", help="nguồn GT khi --commit (highres_depth = dự phòng)")
    ap.add_argument("--gt-voxel", type=float, default=0.01, help="voxel (m) của faro_scene_frame.ply khi --commit")
    ap.add_argument("--faro-radius", type=float, default=15.0, help="bán kính (m) quanh máy quét giữ lại cho căn thô")
    ap.add_argument("--skip-fpfh", action="store_true", help="bỏ cross-check FPFH+RANSAC")
    args = ap.parse_args(argv)

    try:
        info = resolve_scene(Path(args.root), args.scene)
    except (sp.HeldoutError, sp.LockError, ValueError, FileNotFoundError) as e:
        print(f"[LỖI] {type(e).__name__}: {e}")
        return 1
    out_dir = info["layout"].faro
    try:
        if args.commit:
            return commit_candidate(info, out_dir, args)
        if args.phase == 1:
            rep = phase1(info, out_dir)
            pio.write_json(out_dir / "phase1_report.json", rep)
            print(f"[OK] pha 1 chạy xong; ghi {out_dir / 'phase1_report.json'}")
            return 0
        return run_alignment(info, out_dir, args)
    except StopError as e:
        print(f"[DỪNG] {e}")
        return 2
    except FileNotFoundError as e:
        print(f"[LỖI] thiếu dữ liệu: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
