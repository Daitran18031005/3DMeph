"""Test stage `align` (pipeline/alignment/stage.py) bằng camera và chunk tổng hợp: không cần COLMAP/VGGT thật."""

import numpy as np
import pytest

from pipeline.alignment import stage
from pipeline.common import io as pio
from pipeline.common.errors import E_MISSING_INPUT, StageError
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


def cfg(ratio=1.0):
    return {"align": {"min_pairs": 3, "ransac": {"max_error_ratio": ratio}, "anchor_file": "ground_truth/scale_anchor.json"}}


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
