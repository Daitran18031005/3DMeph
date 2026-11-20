"""Test bộ dò mặt phẳng cải tiến (lệch #53): tách hai tấm song song gần nhau và hai mảng đồng phẳng rời nhau, mà RANSAC 5 cm cũ gộp."""

import numpy as np

from pipeline.plane_gate import stage as gs

UP = np.array([0.0, 0.0, 1.0])


def _slab(rng, x0, x1, y0, y1, z, n=12000, noise=0.003):
    return np.c_[rng.uniform(x0, x1, n), rng.uniform(y0, y1, n), z + rng.normal(0, noise, n)]


def _normals(pts):
    return np.tile(UP, (len(pts), 1))


def _refined(pts, **kw):
    args = dict(ransac_m=0.01, normal_deg=20, eps=0.05, min_points=500, max_proposals=10)
    args.update(kw)
    return gs.find_planes_refined(pts, _normals(pts), UP, np.array([1.5]), 15, args["ransac_m"], args["normal_deg"], args["eps"],
                                  args["min_points"], args["max_proposals"])


def test_hai_tam_song_song_cach_3cm_ra_hai_mat_ransac_cu_ra_mot():
    rng = np.random.default_rng(0)
    pts = np.r_[_slab(rng, 0, 2, 0, 2, 0.0), _slab(rng, 0, 2, 0, 2, 0.03)]
    old = gs.find_planes(pts, UP, np.array([1.5]), 0.05, 15, 8, 0.2)
    assert len(old) == 1                                              # tấm dày 5 cm nuốt cả hai bề mặt
    new = _refined(pts)
    hs = sorted(-p["d"] / (np.array(p["n"]) @ UP) for p in new)
    assert len(new) == 2 and abs(hs[0] - 0.0) < 0.005 and abs(hs[1] - 0.03) < 0.005


def test_hai_mang_dong_phang_roi_nhau_ra_hai_mat():
    rng = np.random.default_rng(1)
    pts = np.r_[_slab(rng, 0, 1, 0, 1, 0.7), _slab(rng, 3, 4, 0, 1, 0.7)]
    assert len(_refined(pts)) == 2


def test_robust_fit_bo_diem_ngoai_lai():
    rng = np.random.default_rng(2)
    pts = np.r_[_slab(rng, 0, 1, 0, 1, 0.0, n=2000), np.c_[rng.uniform(0, 1, (50, 2)), np.full(50, 0.05)]]
    n, d, keep = gs.robust_fit(pts)
    assert abs(abs(n @ UP) - 1) < 1e-3 and abs(d) < 0.002 and keep[:2000].mean() > 0.95 and not keep[2000:].any()


def test_run_gate_refined_chi_gan_diem_cho_mat_co_mang_gan(tmp_path):
    """Mảng mặt bàn nhỏ không được hút điểm nằm trên phần kéo dài vô hạn của nó ở xa (gán theo mảng ≤ cluster_eps_m)."""


    from pipeline.common import config as cfgmod
    from pipeline.common import io as pio
    from pipeline.common.ply import read_ply, write_ply
    rng = np.random.default_rng(3)
    lay = pio.scene_layout(tmp_path / "scenes", "arkitscenes", "778")
    floor = np.c_[rng.uniform(0, 4, 20000), rng.normal(0, 0.003, 20000), rng.uniform(0, 4, 20000)]
    table = np.c_[rng.uniform(1, 1.6, 3000), 0.75 + rng.normal(0, 0.003, 3000), rng.uniform(1, 1.6, 3000)]
    stray = np.c_[rng.uniform(3.4, 3.5, 100), np.full(100, 0.77), rng.uniform(3.4, 3.5, 100)]   # cách phần kéo dài của mặt bàn 2 cm, cách mảng > 2 m
    pts = np.r_[floor, table, stray]
    write_ply(lay.fusion / "fused_points.ply", {"x": pts[:, 0].astype(np.float32), "y": pts[:, 1].astype(np.float32), "z": pts[:, 2].astype(np.float32),
                                                 "w_k": np.full(len(pts), 0.9, np.float32), "n_views": np.full(len(pts), 3, np.uint8)})
    pio.write_json(lay.alignment / "scale.json", {"s_m": 1.0})
    cams = {i: {"R": np.diag([1.0, -1.0, -1.0]), "center": np.array([2.0, 1.2, 1.5])} for i in range(3)}
    cfg = cfgmod.load_config()
    cfg["plane"].update(detector="refined", gate_scope="all", tau_w=0.0, min_walls=0)
    cfg["plane"]["refined"].update(ransac_m=0.01, cluster_eps_m=0.1, min_points=500)
    gs.run_gate(lay, cfg, log=lambda m: None, load_cameras=lambda _l: cams)
    out = read_ply(lay.plane_refinement / "refined_points.ply")
    s = slice(len(floor) + len(table), None)
    assert (out["g"][s] == 0).all() and np.allclose(out["y"][s], 0.77)            # điểm lạc ở xa giữ nguyên
    assert out["g"][len(floor):len(floor) + len(table)].mean() > 0.9               # điểm mặt bàn qua cổng
    assert (lay.plane_refinement / "plane_members.npy").is_file()

