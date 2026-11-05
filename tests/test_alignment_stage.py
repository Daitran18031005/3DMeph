"""Test stage `align` (pipeline/alignment/stage.py) bằng camera và chunk tổng hợp: không cần COLMAP/VGGT thật."""

import numpy as np
import pytest

from pipeline.alignment import stage
from pipeline.common import io as pio
from pipeline.common.errors import E_ANCHOR_STALE, E_MISSING_INPUT, StageError
from pipeline.common.geometry import apply_sim3, rodrigues

S_TRUE, T_TRUE = 3.2, np.array([1.0, -2.0, 0.5])
R_TRUE = rodrigues(np.array([0.0, 0.0, np.pi / 2]))


def make_cams(n=25):
    rng = np.random.default_rng(1)
    ys = np.cumsum(rng.uniform(0.1, 0.3, (n, 3)), axis=0)
    return {i: {"center": ys[i], "K": np.eye(3), "R": np.eye(3), "t": -ys[i]} for i in range(n)}


def write_chunks(layout, cams, ranges, bad=()):
    """Mỗi chunk: x_i = Sim3⁻¹(y_i) (R_cw = I nên extrinsic = [I | −x_i]); `bad`: view bị lệch 5 đv."""
    for k, (a, b) in enumerate(ranges):
        ck = pio.ensure_dir(layout.vggt / f"chunk_{k:02d}")
        views = list(range(a, b))
        x = np.array([(R_TRUE.T @ (cams[v]["center"] - T_TRUE)) / S_TRUE for v in views])
        for j, v in enumerate(views):
            if v in bad:
                x[j] += 5.0
        ext = np.concatenate([np.tile(np.eye(3), (len(views), 1, 1)), -x[:, :, None]], axis=2)
        np.savez(ck / "vggt_raw.npz", extrinsic=ext, intrinsic=np.zeros((len(views), 3, 3)), depth=np.zeros((len(views), 2, 2)),
                 depth_conf=np.ones((len(views), 2, 2)))
        np.savez(ck / "vggt_out.npz", c_model=np.zeros((len(views), 2, 2)), points=np.zeros((len(views), 2, 2, 3)))
        pio.write_json(ck / "chunk_meta.json", {"chunk": k, "start": a, "end": b, "views": views})


@pytest.fixture
def layout(tmp_path):
    return pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777")


def cfg(ratio=1.0, method="centers"):
    return {"align": {"method": method, "scale_from": "distances", "min_pairs": 3, "ransac": {"max_error_ratio": ratio}, "anchor_file": "ground_truth/scale_anchor.json"}}


def test_run_align_khoi_phuc_sim3_va_loai_camera_sai(layout):
    cams = make_cams()
    write_chunks(layout, cams, [(0, 12), (10, 22), (20, 25)], bad={3})
    logs = []
    st = stage.run_align(layout, cfg(0.5), log=logs.append, load_cameras=lambda lay: cams, with_scale=False)
    assert st["n_chunks"] == 3 and st["n_accepted"] == 3 and st["rejected_chunks"] == []
    r0 = pio.read_json(layout.alignment / "chunk_00_sim3.json")
    assert r0["s"] == pytest.approx(S_TRUE, rel=1e-6) and np.allclose(r0["R"], R_TRUE, atol=1e-8) and np.allclose(r0["t"], T_TRUE, atol=1e-6)
    assert r0["n_pairs"] == 12 and r0["n_inliers"] == 11 and 3 not in r0["inlier_views"] and r0["rmse"] < 1e-8
    r2 = pio.read_json(layout.alignment / "chunk_02_sim3.json")
    assert r2["n_pairs"] == 5 and r2["accepted"] and (layout.alignment / "align_result.json").is_file()
    assert any("3/3 chunk" in m for m in logs)
    y = apply_sim3(r0["s"], np.array(r0["R"]), np.array(r0["t"]), np.array([[0.0, 0.0, 0.0]]))
    assert y.shape == (1, 3)


def test_chunk_it_view_dang_ky_bi_loai_co_ly_do(layout):
    cams = {k: v for k, v in make_cams().items() if k not in (4, 5, 6, 7, 8, 9, 10, 11)}
    write_chunks(layout, cams | {v: make_cams()[v] for v in range(25)}, [(0, 12), (10, 22)])
    st = stage.run_align(layout, cfg(0.5), log=lambda m: None, load_cameras=lambda lay: cams, with_scale=False)
    r0 = pio.read_json(layout.alignment / "chunk_00_sim3.json")
    assert r0["n_pairs"] == 4 and r0["accepted"]
    cams2 = {k: v for k, v in make_cams().items() if k in (0, 1, 15, 16, 17, 18, 19, 20, 21)}
    st = stage.run_align(layout, cfg(0.5), log=lambda m: None, load_cameras=lambda lay: cams2, with_scale=False)
    r0 = pio.read_json(layout.alignment / "chunk_00_sim3.json")
    assert not r0["accepted"] and "đã đăng ký" in r0["reason"] and st["rejected_chunks"] == [0]


def test_thieu_dau_vao_va_ratio_null(layout):
    with pytest.raises(ValueError, match="max_error_ratio"):
        stage.run_align(layout, cfg(None), log=lambda m: None, load_cameras=lambda lay: {}, with_scale=False)
    with pytest.raises(StageError) as e:
        stage.run_align(layout, cfg(1.0), log=lambda m: None, load_cameras=lambda lay: {}, with_scale=False)
    assert e.value.code == E_MISSING_INPUT


def test_apply_scale_chan_mốc_cu_khi_model_colmap_doi(layout, monkeypatch):
    pio.write_json(layout.ground_truth / "scale_anchor.json", {"id": "S05", "L_real": 1.92, "L_model": 6.2, "colmap_model_sha256": "abc"})
    monkeypatch.setattr(stage, "model_fingerprint", lambda lay: "xyz")
    with pytest.raises(StageError) as e:
        stage.apply_scale(layout, cfg(), log=lambda m: None)
    assert e.value.code == E_ANCHOR_STALE and "click_anchor_2d" in str(e.value)
    monkeypatch.setattr(stage, "model_fingerprint", lambda lay: "abc")
    assert stage.apply_scale(layout, cfg(), log=lambda m: None)["s_m"] == pytest.approx(1.92 / 6.2)
    logs = []
    pio.write_json(layout.ground_truth / "scale_anchor.json", {"id": "S05", "L_real": 1.92, "L_model": 6.2})        # bản cũ không có dấu vân tay
    stage.apply_scale(layout, cfg(), log=logs.append)
    assert any("CẢNH BÁO" in m for m in logs)


def test_apply_scale_can_L_model_va_ghi_b0_met(layout):
    pio.write_json(layout.ground_truth / "scale_anchor.json", {"id": "S05", "L_real": 1.92, "source": "faro"})
    with pytest.raises(StageError) as e:
        stage.apply_scale(layout, cfg(), log=lambda m: None)
    assert e.value.code == E_MISSING_INPUT and "click_anchor_2d" in str(e.value)

    import open3d as o3d
    pio.ensure_dir(layout.colmap_mvs)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 2.0, 0.0]]))
    o3d.io.write_point_cloud(str(layout.colmap_mvs / "fused.ply"), pcd)
    pio.write_json(layout.ground_truth / "scale_anchor.json", {"id": "S05", "L_real": 1.92, "L_model": 6.2, "source": "faro"})
    sc = stage.apply_scale(layout, cfg(), log=lambda m: None)
    assert sc["s_m"] == pytest.approx(1.92 / 6.2) and pio.read_json(layout.alignment / "scale.json")["L_model"] == 6.2
    out = np.asarray(o3d.io.read_point_cloud(str(layout.colmap_metric / "fused_metric.ply")).points)
    assert np.allclose(out[1], [1.92 / 6.2, 0, 0], atol=1e-6) and sc["b0_points"] == 3


# ---------------------------------------------------------------------------
# align.method = orientation_depth (LỆCH ĐC §15.1)
# ---------------------------------------------------------------------------


def make_orientation_chunk(n_views=12, spread=0.3, center_noise=0.0, seed=0, n_pts=300):
    """Camera gần thẳng hàng (trải ngắn) nhìn các điểm phía trước; VGGT = Sim(3)⁻¹ của COLMAP. Trả (extrinsic VGGT, cams COLMAP, cặp điểm)."""
    rng = np.random.default_rng(seed)
    centers = np.stack([np.linspace(0, spread, n_views), rng.normal(0, 0.003, n_views), rng.normal(0, 0.003, n_views)], axis=1)
    rc = rodrigues(np.array([0.1, -0.2, 0.05]))                                  # hướng camera COLMAP (world→camera), chung cho mọi view
    cams = {i: {"R": rc, "center": centers[i], "t": -rc @ centers[i], "K": np.eye(3)} for i in range(n_views)}
    x_v = (centers - T_TRUE) @ R_TRUE / S_TRUE + rng.normal(0, center_noise, centers.shape)      # tâm camera trong hệ VGGT (có thể nhiễu)
    r_cw_v = rc @ R_TRUE                                                            # R_cw,vggt
    ext = np.concatenate([np.tile(r_cw_v, (n_views, 1, 1)), -(r_cw_v @ x_v.T).T[:, :, None]], axis=2)
    pts_c = np.array([2.0, 0.0, 0.0]) + rng.uniform(-1, 1, (n_pts, 3)) + np.array([0.0, 0.0, 3.0])   # điểm MVS (COLMAP) phía trước
    views = rng.integers(0, n_views, n_pts)
    p_v = (pts_c - T_TRUE) @ R_TRUE / S_TRUE                                        # cùng điểm trong hệ VGGT
    return ext, cams, views, pts_c, p_v


def angle_deg(r1, r2):
    return float(np.degrees(np.arccos(np.clip((np.trace(r1.T @ r2) - 1) / 2, -1, 1))))


def test_rotation_from_orientations_loai_view_lech():
    rc = np.array([rodrigues(np.array([0.1, 0.2, 0.0]) * (1 + 0.01 * i)) for i in range(10)])
    r_true = rodrigues(np.array([0.3, -0.4, 0.2]))
    r_v = np.array([m @ r_true for m in rc])                                       # R_cw,vggt = R_cw,col · R
    r_v[3] = rodrigues(np.array([0.0, 1.0, 0.0])) @ r_v[3]                          # một view xoay sai 57°
    r, dev, keep = stage.rotation_from_orientations(rc, r_v)
    assert angle_deg(r, r_true) < 1.0 and not keep[3] and keep.sum() == 9 and dev[3] > 40


def test_align_chunk_orientation_khoi_phuc_sim3_ke_ca_khi_tam_camera_nhieu():
    ext, cams, views, x, p = make_orientation_chunk(center_noise=0.02)
    res = stage.align_chunk_orientation(ext, list(range(12)), cams, views, x, p, 3)
    assert res["accepted"] and res["s"] == pytest.approx(S_TRUE, rel=0.02)
    assert angle_deg(np.array(res["R"]), R_TRUE) < 0.5
    assert res["point_dev_colmap_units"]["median"] < 0.1 and res["n_point_pairs"] == 300
    old = stage.align_chunk(stage.vggt_centers(ext), list(range(12)), cams, 5.0, 3)         # cách ĐC §15.1 trên cùng dữ liệu
    assert old["accepted"] and angle_deg(np.array(old["R"]), R_TRUE) > angle_deg(np.array(res["R"]), R_TRUE) + 3        # xoay theo tâm camera kém hơn nhiều
    few = stage.align_chunk_orientation(ext, [0, 1], cams, views, x, p, 3)
    assert not few["accepted"] and "đã đăng ký" in few["reason"]
    none = stage.align_chunk_orientation(ext, list(range(12)), cams, views[:0], x[:0], p[:0], 3)
    assert not none["accepted"] and "cặp điểm" in none["reason"]


def test_scale_from_points_giu_khoang_cach_giua_hai_diem_khi_depth_vggt_khac_tinh_tien_camera():
    ext, cams, views, x, p = make_orientation_chunk()
    p_bad = p.mean(axis=0) + (p - p.mean(axis=0)) / 1.15          # độ sâu VGGT co 15% so với tịnh tiến camera: tỉ lệ camera→điểm lệch, khoảng cách điểm–điểm thì không
    d = stage.align_chunk_orientation(ext, list(range(12)), cams, views, x, p_bad, 3, "distances")
    pt = stage.align_chunk_orientation(ext, list(range(12)), cams, views, x, p_bad, 3, "points")
    assert pt["s"] == pytest.approx(S_TRUE * 1.15, rel=0.01) and abs(d["s"] - S_TRUE * 1.15) > 0.05 * S_TRUE
    assert pt["s_distances"] == pytest.approx(d["s"]) and pt["accepted"]
    assert pt["point_dev_colmap_units"]["median"] < 0.1 < d["point_dev_colmap_units"]["median"]          # t từ điểm: điểm khớp MVS; t từ tâm camera: không
    with pytest.raises(ValueError, match="scale_from"):
        stage.align_chunk_orientation(ext, list(range(12)), cams, views, x, p, 3, "khac")


def test_run_align_orientation_depth_ghi_file_va_phuong_phap(layout):
    ext, cams, views, x, p = make_orientation_chunk()
    ck = pio.ensure_dir(layout.vggt / "chunk_00")
    np.savez(ck / "vggt_raw.npz", extrinsic=ext, intrinsic=np.zeros((12, 3, 3)), depth=np.zeros((12, 2, 2)), depth_conf=np.ones((12, 2, 2)))
    np.savez(ck / "vggt_out.npz", c_model=np.zeros((12, 2, 2)), points=np.zeros((12, 2, 2, 3)))
    pio.write_json(ck / "chunk_meta.json", {"chunk": 0, "start": 0, "end": 12, "views": list(range(12))})
    pairs = {"view": views, "chunk": np.zeros(len(views), int), "x": x, "p": p}
    logs = []
    st = stage.run_align(layout, cfg(method="orientation_depth"), log=logs.append, load_cameras=lambda lay: cams, with_scale=False, load_pairs=lambda lay, c: pairs)
    r0 = pio.read_json(layout.alignment / "chunk_00_sim3.json")
    assert st["method"] == "orientation_depth" and st["n_accepted"] == 1 and r0["method"] == "orientation_depth" and r0["s"] == pytest.approx(S_TRUE, rel=1e-3)
    assert any("orientation_depth" in m for m in logs)
    with pytest.raises(ValueError, match="align.method"):
        stage.run_align(layout, cfg(method="khac"), log=lambda m: None, load_cameras=lambda lay: cams, with_scale=False)
