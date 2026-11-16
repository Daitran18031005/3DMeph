"""45662981: khoảng cách tường 2 ↔ tường 4 đo trên từng biến thể (B0, B1, B3, proposed) so với Faro, cùng vùng và cùng phép căn ICP của proposed. Chỉ đọc.

Câu hỏi: lệch +7,8 cm có ở đám MVS gốc (B0) không? Có → không do fusion/gate; không → do fusion.
    python docs/evidence/m4_improve/wall_45662981/wall_check.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
import pipeline  # noqa: E402,F401

# isort: split
import length_error as le  # noqa: E402
import length_error_v2 as v2  # noqa: E402
import numpy as np  # noqa: E402

from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common.io import read_json, scene_layout  # noqa: E402
from pipeline.eval import geometry as geo  # noqa: E402
from pipeline.eval.stage import gt_camera_centers  # noqa: E402
from pipeline.eval.variants import base_layout, cloud_path  # noqa: E402

SC, WALLS, BAND = "45662981", (2, 4), 0.15          # vùng: điểm cách mặt RANSAC của proposed ≤ 15 cm (đặt trước)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = cfgmod.load_config(REPO / "configs" / "default.yaml")
    lay = base_layout(scene_layout(REPO / cfgmod.require(cfg, "paths.data_root"), "arkitscenes", SC))
    pl = {p["id"]: p for p in read_json(lay.plane_refinement / "planes.json")["planes"]}
    gt = gt_camera_centers(lay)
    faro = geo.load_points(lay.faro / "faro_scene_frame.ply")
    _, r, t, prop = le.variant_rows(lay, cfg, "proposed", [], gt, 0.05, "icp", faro)
    lo, hi = prop.min(axis=0) - 0.3, prop.max(axis=0) + 0.3
    faro_m = faro @ r.T + t
    faro_m = faro_m[np.all((faro_m > lo) & (faro_m < hi), axis=1)]

    def region(pts, pid):
        """Điểm trong dải BAND quanh mặt `pid`, giới hạn theo hình chiếu của inlier proposed trên mặt (hộp 2D + 10 cm)."""
        p = pl[pid]
        n, d = np.array(p["n"]), p["d"]
        inl = prop[np.abs(prop @ n + d) < 0.05]
        u = np.linalg.svd(inl - inl.mean(0), full_matrices=False)[2][:2]
        lo2, hi2 = (inl @ u.T).min(0) - 0.1, (inl @ u.T).max(0) + 0.1
        m = (np.abs(pts @ n + d) < BAND) & np.all((pts @ u.T > lo2) & (pts @ u.T < hi2), axis=1)
        return pts[m]

    fa, fb = (v2.fit_plane(region(faro_m, w)) for w in WALLS)
    d_faro = v2.plane_dist(fa[0], fa[1], fb[0], fb[1])
    print(f"Faro tường {WALLS[0]}↔{WALLS[1]}: {d_faro:.4f} m (điểm {fa[2]}, {fb[2]})")
    for v in ("B0", "B1", "B3", "proposed"):
        p = cloud_path(lay, v)
        if not p.is_file():
            print(f"{v}: không có")
            continue
        pts = geo.load_points(p)
        ra, rb = region(pts, WALLS[0]), region(pts, WALLS[1])
        if min(len(ra), len(rb)) < 200:
            print(f"{v}: quá ít điểm ({len(ra)}, {len(rb)})")
            continue
        a, b = v2.fit_plane(ra), v2.fit_plane(rb)
        da, db = (float((x[1] - f[1]) @ f[0]) * 100 for x, f in ((a, fa), (b, fb)))
        d = v2.plane_dist(a[0], a[1], b[0], b[1])
        print(f"{v}: {d:.4f} m, lệch {(d - d_faro) * 100:+.1f} cm ({(d / d_faro - 1) * 100:+.2f}%); offset dọc pháp tuyến Faro: tường {WALLS[0]} {da:+.1f} cm, tường {WALLS[1]} {db:+.1f} cm; điểm {a[2]}, {b[2]}")


if __name__ == "__main__":
    main()
