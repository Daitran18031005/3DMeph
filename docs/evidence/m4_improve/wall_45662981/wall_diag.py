"""45662981: chẩn đoán lệch tường 2/4 của B0 (MVS gốc) so với Faro. Chỉ đọc.

(1) offset dọc pháp tuyến HƯỚNG RA NGOÀI phòng (từ tâm camera ra tường) của điểm B0 so với mặt Faro: hai tường cùng ra ngoài = phòng phình; ngược dấu = dịch.
(2) offset theo khoảng cách tới camera gần nhất và góc tới (ray so với pháp tuyến): lệch tăng theo khoảng cách/góc xiên = bias depth của MVS.
(3) hướng các đoạn test dài so với pháp tuyến tường: đoạn dài có đo cùng phương 2↔4 không.
    python docs/evidence/m4_improve/wall_45662981/wall_diag.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))
import pipeline  # noqa: E402,F401

# isort: split
import length_error as le  # noqa: E402
import length_error_v2 as v2  # noqa: E402
import numpy as np  # noqa: E402
import wall_check as wc  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

from pipeline.alignment.stage import load_colmap_cameras  # noqa: E402
from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common.io import read_json, scene_layout  # noqa: E402
from pipeline.eval import geometry as geo  # noqa: E402
from pipeline.eval import lengths as ln  # noqa: E402
from pipeline.eval.stage import gt_camera_centers  # noqa: E402
from pipeline.eval.variants import base_layout, camera_centers, cloud_path  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = cfgmod.load_config(REPO / "configs" / "default.yaml")
    lay = base_layout(scene_layout(REPO / cfgmod.require(cfg, "paths.data_root"), "arkitscenes", wc.SC))
    pl = {p["id"]: p for p in read_json(lay.plane_refinement / "planes.json")["planes"]}
    gt = gt_camera_centers(lay)
    faro = geo.load_points(lay.faro / "faro_scene_frame.ply")
    _, r, t, prop = le.variant_rows(lay, cfg, "proposed", [], gt, 0.05, "icp", faro)
    faro_m = faro @ r.T + t
    cams = np.array(list(camera_centers(lay, "B0", load_colmap_cameras).values()))
    cc = cams.mean(axis=0)
    b0 = geo.load_points(cloud_path(lay, "B0"))
    ctree = cKDTree(cams)

    def region(pts, pid):
        p = pl[pid]
        n, d = np.array(p["n"]), p["d"]
        inl = prop[np.abs(prop @ n + d) < 0.05]
        u = np.linalg.svd(inl - inl.mean(0), full_matrices=False)[2][:2]
        lo2, hi2 = (inl @ u.T).min(0) - 0.1, (inl @ u.T).max(0) + 0.1
        return pts[(np.abs(pts @ n + d) < wc.BAND) & np.all((pts @ u.T > lo2) & (pts @ u.T < hi2), axis=1)]

    normals = {}
    for w in wc.WALLS:
        nf, cf, _ = v2.fit_plane(region(faro_m, w))
        nf = nf if (cf - cc) @ nf > 0 else -nf                                   # pháp tuyến hướng ra ngoài phòng
        normals[w] = nf
        pts = region(b0, w)
        off = (pts - cf) @ nf * 100
        keep = np.abs(off - np.median(off)) < 10                                # bỏ đồ vật sát tường
        pts, off = pts[keep], off[keep]
        dist, idx = ctree.query(pts)
        ray = pts - cams[idx]
        inc = np.degrees(np.arccos(np.clip(np.abs((ray / np.linalg.norm(ray, axis=1, keepdims=True)) @ nf), 0, 1)))
        print(f"tường {w}: tâm camera cách mặt Faro {(cf - cc) @ nf:.2f} m; B0 offset ra ngoài trung vị {np.median(off):+.1f} cm (n {len(off)})")
        for name, x, edges in (("cách camera gần nhất (m)", dist, [0, 1.5, 2.5, 3.5, 99]), ("góc tới (°)", inc, [0, 30, 50, 70, 90])):
            parts = [f"{lo:g}–{hi:g}: {np.median(off[(x >= lo) & (x < hi)]):+.1f} (n {((x >= lo) & (x < hi)).sum()})" for lo, hi in zip(edges, edges[1:]) if ((x >= lo) & (x < hi)).sum() > 100]
            print(f"   theo {name}: " + "; ".join(parts))
    n_avg = normals[wc.WALLS[0]] - normals[wc.WALLS[1]]
    n_avg /= np.linalg.norm(n_avg)
    print("đoạn test dài (> 2 m): |cos| giữa đoạn và phương 2↔4")
    for s in ln.read_measurements(lay.ground_truth / "measurements.csv"):
        if s["gt_m"] > 2:
            dvec = (np.array(s["b"]) - np.array(s["a"])) @ r.T
            print(f"   {s['id']} {s['gt_m']:.2f} m: {abs(dvec @ n_avg) / np.linalg.norm(dvec):.2f}")


if __name__ == "__main__":
    main()
