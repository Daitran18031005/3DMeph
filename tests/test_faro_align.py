"""Test scripts/faro_registration.py và scripts/faro_align.py bằng cảnh tổng hợp (phòng chữ L + hộp bất đối xứng).

Dung sai trong test chỉ để kiểm hàm trên dữ liệu có đáp án; mã thật KHÔNG có ngưỡng chấp nhận residual.
"""

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path

import numpy as np
import pytest

from pipeline.common import splits as sp

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name + "_under_test", REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


frs = _load("faro_registration")
fa = _load("faro_align")


# ---------------------------------------------------------------------------
# Cảnh tổng hợp
# ---------------------------------------------------------------------------


def _wall(p0, p1, h=2.5, step=0.03):
    p0, p1 = np.array(p0, float), np.array(p1, float)
    n = max(int(np.linalg.norm(p1 - p0) / step), 2)
    xs = p0[None, :] + np.linspace(0, 1, n)[:, None] * (p1 - p0)[None, :]
    zs = np.arange(0.0, h + 1e-9, step)
    return np.array([[x[0], x[1], z] for x in xs for z in zs])


def make_room(rng):
    """Phòng chữ L 6×5 m (cắt góc 3×2), sàn, một hộp 0,8×0,6×1,2 m ở góc và một cột — không có đối xứng."""
    poly = [(0, 0), (6, 0), (6, 3), (3, 3), (3, 5), (0, 5)]
    walls = np.concatenate([_wall(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))])
    floor = np.array([[x, y, 0.0] for x in np.arange(0.05, 6, 0.05) for y in np.arange(0.05, 5, 0.05)
                      if (y < 3 or x < 3)])
    box = np.concatenate([_wall((4.0, 0.3), (4.8, 0.3), 1.2), _wall((4.8, 0.3), (4.8, 0.9), 1.2),
                          _wall((4.8, 0.9), (4.0, 0.9), 1.2), _wall((4.0, 0.9), (4.0, 0.3), 1.2)])
    pillar = _wall((1.0, 3.8), (1.2, 3.8), 2.5) + 0.0
    pts = np.concatenate([walls, floor, box, pillar])
    return pts + rng.normal(0, 0.001, pts.shape)


T_TRUE = frs.make_T(frs.rot_z(np.radians(37.0)), np.array([2.3, -1.1, -215.77]))     # Faro → scene


@pytest.fixture(scope="module")
def scene():
    rng = np.random.default_rng(3)
    room = make_room(rng)
    faro = room + np.array([0.0, 0.0, 215.77]) + np.array([-0.4, 0.2, 0.0])          # hệ Faro: z ≈ 215, lệch xy
    t_true = T_TRUE.copy()
    # T_true: Faro → scene, chọn sao cho scene ≈ room xoay 37° rồi dời
    scene_pts = frs.apply_T(t_true, faro)
    centre = scene_pts[:, :2].mean(axis=0)
    sel = np.hypot(scene_pts[:, 0] - centre[0] - 0.8, scene_pts[:, 1] - centre[1]) < 3.0   # đích chỉ phủ một phần phòng
    target = scene_pts[sel] + rng.normal(0, 0.002, (int(sel.sum()), 3))
    return faro, target, t_true


# ---------------------------------------------------------------------------
# faro_registration
# ---------------------------------------------------------------------------


def test_bien_doi_co_ban():
    t = frs.make_T(frs.rot_z(np.radians(30)), np.array([1.0, 2.0, 3.0]))
    p = np.array([[1.0, 0.0, 0.5], [0.0, 1.0, -2.0]])
    assert np.allclose(frs.apply_T(frs.invert_T(t), frs.apply_T(t, p)), p)
    assert frs.yaw_deg(t[:3, :3]) == pytest.approx(30.0)
    assert frs.tilt_deg(t[:3, :3]) == pytest.approx(0.0, abs=1e-6)
    r_tilt = frs.rodrigues_small(np.array([np.radians(5), 0, 0]))
    assert frs.tilt_deg(r_tilt) == pytest.approx(5.0, abs=1e-6)
    d = frs.transform_difference(t, frs.make_T(t[:3, :3], t[:3, 3] + np.array([0.0, 0.0, 0.1])))
    assert d["rotation_deg"] == pytest.approx(0.0, abs=1e-5) and d["translation_m"] == pytest.approx(0.1)


def test_transform_difference_khong_bi_don_bay_tinh_tien():
    """Xoay 0,25° quanh tâm phòng ở z = 215 m: vector tịnh tiến ~0,94 m nhưng điểm trong phòng chỉ dời vài cm."""
    r = frs.rodrigues_small(np.array([np.radians(0.25), 0.0, 0.0]))
    c = np.array([0.0, 0.0, 215.0])
    t_a = frs.make_T(np.eye(3), np.zeros(3))
    t_b = frs.make_T(r, c - r @ c)
    room = np.random.default_rng(0).uniform(-2, 2, (1000, 3)) + c
    d = frs.transform_difference(t_a, t_b, room)
    assert d["rotation_deg"] == pytest.approx(0.25, abs=1e-6)
    assert d["translation_m"] > 0.9                                  # con số gây hiểu lầm nếu dùng một mình
    assert d["point_rms_m"] < 0.02 and d["point_max_m"] < 0.02       # độ dời thật của điểm trong phòng
    assert "point_rms_m" not in frs.transform_difference(t_a, t_b)


def test_structure_mask_giu_tuong_bo_san():
    rng = np.random.default_rng(0)
    floor = np.column_stack([rng.uniform(1, 3, 500), rng.uniform(1, 3, 500), np.zeros(500)])
    wall = np.column_stack([np.full(300, 0.52), rng.uniform(0, 2, 300), rng.uniform(0, 2.5, 300)])
    m = frs.structure_mask(np.concatenate([floor, wall]))
    assert not m[:500].any() and m[500:].mean() > 0.9


def test_can_tho_phuc_hoi_yaw_va_tinh_tien(scene):
    faro, target, t_true = scene
    fs = faro[frs.structure_mask(faro)]
    ts = target[frs.structure_mask(target)]
    co = frs.coarse_yaw_xy(fs, ts)
    err_yaw = abs(((co["yaw_deg"] - 37.0 + 180) % 360) - 180)
    assert err_yaw < 1.0
    moved = frs.apply_T(co["T"], faro)
    assert np.allclose(co["T"][:2, 3], t_true[:2, 3], atol=0.1)
    cz = frs.coarse_z(moved, target)
    assert cz["tz"] == pytest.approx(t_true[2, 3], abs=0.03)
    assert co["score"] > co["second_peak"]["score"]


def test_icp_hoi_tu_va_sai_so_nho(scene):
    faro, target, t_true = scene
    perturb = frs.make_T(frs.rodrigues_small(np.radians([1.0, -1.0, 2.0])), np.array([0.04, -0.03, 0.02]))
    t0 = perturb @ t_true
    ref_pts = frs.apply_T(t0, faro)
    nrm = fa.estimate_normals(ref_pts, 0.05)
    res = frs.icp_point_to_plane(target, ref_pts, nrm, np.eye(4), max_corr=0.15)
    assert res["converged"] and res["fitness"] > 0.9
    t_f2s = frs.invert_T(res["T"]) @ t0
    diff = frs.transform_difference(t_true, t_f2s)
    assert diff["rotation_deg"] < 0.1 and diff["translation_m"] < 0.01


def test_icp_khong_hoi_tu_khi_het_vong_lap_va_khong_tuong_ung(scene):
    faro, target, t_true = scene
    ref_pts = frs.apply_T(t_true, faro)
    nrm = fa.estimate_normals(ref_pts, 0.05)
    perturb = frs.make_T(frs.rodrigues_small(np.radians([0, 0, 3.0])), np.array([0.05, 0, 0]))
    res = frs.icp_point_to_plane(target, ref_pts, nrm, perturb, max_corr=0.3, max_iter=2)
    assert not res["converged"] and res["iterations"] == 2 and "hết 2" in res["reason"]
    far = frs.make_T(np.eye(3), np.array([100.0, 0, 0]))
    res2 = frs.icp_point_to_plane(target, ref_pts, nrm, far, max_corr=0.1)
    assert res2["fitness"] == 0.0 and not res2["converged"] and "chỉ" in res2["reason"]


def test_icp_fix_up_chi_xoay_quanh_truc_dung(scene):
    faro, target, t_true = scene
    ref_pts = frs.apply_T(t_true, faro)
    nrm = fa.estimate_normals(ref_pts, 0.05)
    perturb = frs.make_T(frs.rot_z(np.radians(2.0)), np.array([0.03, 0.02, 0.01]))
    res = frs.icp_point_to_plane(target, ref_pts, nrm, perturb, max_corr=0.15, fix_up=True)
    assert res["converged"] and frs.tilt_deg(res["T"][:3, :3]) == pytest.approx(0.0, abs=1e-6)


def test_distance_stats():
    st = frs.distance_stats(np.array([0.0, 0.005, 0.015, 0.03, 0.2, np.nan]))
    assert st["n"] == 5 and st["median"] == pytest.approx(0.015) and st["frac_le_1cm"] == pytest.approx(0.4)
    assert frs.distance_stats(np.array([]))["n"] == 0


# ---------------------------------------------------------------------------
# faro_align: chặn held-out, cặp trùng, commit
# ---------------------------------------------------------------------------


def test_resolve_scene_chan_heldout_va_nhan_train():
    info = fa.resolve_scene(REPO, "arkitscenes/42444738")
    assert info["split"] == "train" and info["visit_id"] == "421267"
    assert info["raw_dir"].name == "42444738" and info["faro_dir"].name == "421267"
    for held in ("43828368", "44796254", "47331622", "47332314", "47332795"):
        with pytest.raises(sp.HeldoutError):
            fa.resolve_scene(REPO, f"arkitscenes/{held}")
    with pytest.raises(ValueError):
        fa.resolve_scene(REPO, "replica/room0")
    with pytest.raises(ValueError):
        fa.resolve_scene(REPO, "arkitscenes/00000000")
    assert fa.main(["--scene", "arkitscenes/43828368"]) == 1


def _write_faro_like(path, xyz, extra=0.5):
    dt = np.dtype([("x", "<f8"), ("y", "<f8"), ("z", "<f8"), ("r", "u1"), ("g", "u1"), ("b", "u1"), ("a", "u1"),
                   ("q", "<f8"), ("rad", "<f8")])
    arr = np.zeros(len(xyz), dtype=dt)
    arr["x"], arr["y"], arr["z"], arr["q"] = xyz[:, 0], xyz[:, 1], xyz[:, 2], extra
    header = (b"ply\nformat binary_little_endian 1.0\nelement vertex %d\nproperty double x\nproperty double y\nproperty double z\n"
              b"property uchar red\nproperty uchar green\nproperty uchar blue\nproperty uchar alpha\nproperty double quality\n"
              b"property double radius\nelement face 0\nproperty list uchar int vertex_indices\nend_header\n") % len(xyz)
    path.write_bytes(header + arr.tobytes())


def test_compare_scans_exact(tmp_path):
    xyz = np.random.default_rng(1).uniform(0, 5, (500, 3))
    a, b, c = tmp_path / "a.ply", tmp_path / "b.ply", tmp_path / "c.ply"
    _write_faro_like(a, xyz, 0.1)
    _write_faro_like(b, xyz, 0.9)                       # cùng xyz, khác quality
    xyz2 = xyz.copy()
    xyz2[123, 2] += 1e-9
    _write_faro_like(c, xyz2)
    same = fa.compare_scans_exact(a, b, chunk=100)
    assert same["xyz_identical"] and same["xyz_mismatch_points"] == 0 and same["other_columns_mismatch_points"]["quality"] == 500
    diff = fa.compare_scans_exact(a, c, chunk=100)
    assert not diff["xyz_identical"] and diff["xyz_mismatch_points"] == 1
    short = tmp_path / "d.ply"
    _write_faro_like(short, xyz[:10])
    assert fa.compare_scans_exact(a, short)["xyz_identical"] is False


def test_require_phase1_dung_khi_thieu_hoac_khong_trung(tmp_path):
    with pytest.raises(fa.StopError, match="chạy `--phase 1`"):
        fa.require_phase1(tmp_path)
    fa.pio.write_json(tmp_path / "phase1_report.json", {"pairs_exact": [{"scan_a": "1", "scan_b": "2", "xyz_identical": False}], "groups": []})
    with pytest.raises(fa.StopError, match="không trùng"):
        fa.require_phase1(tmp_path)
    fa.pio.write_json(tmp_path / "phase1_report.json", {"pairs_exact": [{"scan_a": "1", "scan_b": "2", "xyz_identical": True}], "groups": [["1", "2"]]})
    assert fa.require_phase1(tmp_path)["groups"] == [["1", "2"]]


def test_group_by_pose():
    p1, p2 = np.eye(4), np.eye(4) * 2
    scans = [{"scan_id": "a", "pose": p1}, {"scan_id": "b", "pose": p2}, {"scan_id": "c", "pose": p1.copy()}]
    groups = fa.group_by_pose(scans)
    assert [[s["scan_id"] for s in g] for g in groups] == [["a", "c"], ["b"]]


def test_apply_variant_nhat_quan():
    pose = np.eye(4)
    pose[:3, :3] = frs.rot_z(np.radians(20))
    pose[3, :3] = [1.0, 2.0, 3.0]
    p = np.array([[0.3, -0.2, 0.7]])
    assert np.array_equal(fa.apply_variant(p, pose, "A"), p)
    assert np.allclose(fa.apply_variant(fa.apply_variant(p, pose, "B1"), pose, "B2"), p)
    assert np.allclose(fa.apply_variant(fa.apply_variant(p, pose, "B3"), pose, "B4"), p)
    with pytest.raises(ValueError):
        fa.apply_variant(p, pose, "Z")


def _info(tmp_path):
    return {"faro_dir": tmp_path, "raw_dir": tmp_path, "video_id": "x"}


def test_commit_tu_choi_khi_khong_co_ung_vien_hoac_khong_hoi_tu(tmp_path, capsys):
    args = Namespace(source="faro", gt_voxel=0.01)
    assert fa.commit_candidate(_info(tmp_path), tmp_path, args) == 1
    fa.pio.write_json(tmp_path / "faro_to_scene.candidate.json", {"icp_converged_finest_level": False})
    assert fa.commit_candidate(_info(tmp_path), tmp_path, args) == 2
    out = capsys.readouterr().out
    assert "KHÔNG hội tụ" in out and "highres_depth" in out
    assert not (tmp_path / "faro_to_scene.json").exists()


def test_write_ply_xyz_doc_lai_duoc(tmp_path):
    ad = fa.adapters
    pts = np.random.default_rng(2).uniform(-3, 3, (100, 3)).astype(np.float32)
    fa.write_ply_xyz(tmp_path / "x.ply", pts)
    got = np.concatenate(list(ad.iter_ply_xyz(tmp_path / "x.ply")))
    assert np.array_equal(got.astype(np.float32), pts)


def test_topdown_image_ghi_file(tmp_path):
    rng = np.random.default_rng(0)
    a, b = rng.uniform(0, 4, (200, 3)), rng.uniform(0, 4, (200, 3))
    fa.topdown_image(tmp_path / "t.png", a, b)
    assert (tmp_path / "t.png").stat().st_size > 0
