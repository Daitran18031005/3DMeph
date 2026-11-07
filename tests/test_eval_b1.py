"""Test pipeline/eval/b1.py bằng 3 chunk tổng hợp có Sim(3) giữa các chunk và scale mét biết trước."""

import numpy as np
import pytest
from PIL import Image

from pipeline.common import config as cfgmod
from pipeline.common.errors import StageError
from pipeline.common.io import SceneLayout, write_json
from pipeline.common.ply import read_ply
from pipeline.common.schema import write_keyframes_csv
from pipeline.eval import b1
from pipeline.vggt.infer import pad_geometry, vggt_to_original

F, C = 500.0, 259.0
N_VIEWS, CHUNK, OVERLAP = 8, 4, 2
S_TRUE = 2.5                                     # mét trên mỗi đơn vị hệ chunk 0


def _rot(axis, deg):
    c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))
    return {"x": np.array([[1, 0, 0], [0, c, -s], [0, s, c]]), "y": np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]]),
            "z": np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])}[axis]


def _center(v):
    return np.array([0.1 * v, 0.02 * v, 0.0])


def _world_points(v):
    """Điểm 3D (hệ chunk 0, đv VGGT) của từng pixel ảnh VGGT 518×518 ở view v: bề mặt cong nhìn từ camera đặt tại _center(v), nhìn theo +z."""
    ys, xs = np.mgrid[0:518, 0:518].astype(np.float64)
    z = 2.0 + 0.3 * np.sin(0.02 * xs) * np.cos(0.015 * ys) + 0.01 * v
    return np.stack([_center(v)[0] + (xs - C) / F * z, _center(v)[1] + (ys - C) / F * z, z], axis=-1)


def _make_scene(tmp_path, l_real):
    """Chunk k có hệ riêng (T_k: hệ chunk k → hệ chunk 0 = Sim(3) biết trước); camera nhìn +z, R_w = I."""
    layout = SceneLayout(tmp_path / "scene")
    geo = pad_geometry(48, 64)
    write_keyframes_csv([{"view_id": v, "w": 48, "h": 64} for v in range(N_VIEWS)], layout.metadata / "keyframes.csv")
    layout.keyframes.mkdir(parents=True, exist_ok=True)
    img = np.zeros((64, 48, 3), np.uint8)
    img[..., 0] = np.linspace(0, 255, 48, dtype=np.uint8)[None, :]            # đỏ tăng theo cột, xanh lá tăng theo hàng
    img[..., 1] = np.linspace(0, 255, 64, dtype=np.uint8)[:, None]
    for v in range(N_VIEWS):
        Image.fromarray(img).save(layout.keyframes / f"{v:04d}.jpg", quality=100)
    tfs = [(1.0, np.eye(3), np.zeros(3)), (1.07, _rot("y", 12.0), np.array([0.3, -0.1, 0.2])), (0.93, _rot("x", -9.0) @ _rot("z", 15.0), np.array([-0.2, 0.4, 0.1]))]
    cums = [tfs[0]]
    for k in (1, 2):
        cums.append(b1.compose(cums[k - 1], tfs[k]))                  # chunk k → chunk 0
    for k in range(3):
        s, r, t = cums[k]
        views = list(range(k * (CHUNK - OVERLAP), k * (CHUNK - OVERLAP) + CHUNK))
        ext, pts = [], []
        for v in views:
            ext.append(np.hstack([r, ((t - _center(v)) / s).reshape(3, 1)]))                                  # R_local = R_w R_k, t_local = R_w (t_k − C) / s, R_w = I
            pts.append((_world_points(v) - t) @ r / s)                                                    # X_local = R_kᵀ (X_world − t_k) / s
        ck = layout.vggt / f"chunk_{k:02d}"
        ck.mkdir(parents=True)
        np.savez(ck / "vggt_raw.npz", extrinsic=np.array(ext, np.float32), intrinsic=np.tile(np.array([[F, 0, C], [0, F, C], [0, 0, 1.0]], np.float32), (CHUNK, 1, 1)))
        np.savez(ck / "vggt_out.npz", points=np.array(pts, np.float32), c_model=np.full((CHUNK, 518, 518), 0.9, np.float32))
        write_json(ck / "chunk_meta.json", {"chunk": k, "views": views, "start": views[0], "end": views[-1] + 1})
    # mốc: hai điểm hệ chunk 0, quan sát ở view 3..5 (đều thuộc chunk 1) bằng pixel ảnh gốc
    pa, pb = np.array([0.1, 0.0, 2.0]), np.array([0.1, 0.9, 2.1])
    obs = []
    for key, p in (("a", pa), ("b", pb)):
        for v in (3, 4, 5):
            x = p - _center(v)
            uv = np.array([[F * x[0] / x[2] + C, F * x[1] / x[2] + C]])
            u0 = vggt_to_original(uv, geo)[0]
            obs.append({"view": v, "endpoint": key, "uv": [float(u0[0]), float(u0[1])]})
    write_json(layout.ground_truth / "scale_anchor.json", {"id": "S05", "L_real": S_TRUE * float(np.linalg.norm(pb - pa)) if l_real is None else l_real, "observations_2d": obs})
    return layout, cums


@pytest.fixture()
def cfg():
    c = cfgmod.load_config()
    c["eval"]["b1"]["stride"] = 8
    return c


def test_noi_chunk_va_scale_met(tmp_path, cfg):
    layout, cums = _make_scene(tmp_path, None)
    stats = b1.build_b1(layout, cfg, log=lambda m: None)
    assert stats["n_chunks"] == 3 and len(stats["links"]) == 2
    assert stats["s_b1_m_per_vggt_unit"] == pytest.approx(S_TRUE, rel=1e-3)
    assert stats["links"][0]["rmse"] < 1e-4 and stats["links"][0]["shared_views"] == [2, 3]
    pts = read_ply(layout.vggt_metric / "points_metric.ply")
    p = np.stack([pts["x"], pts["y"], pts["z"]], axis=1)
    assert len(p) == stats["n_points"] and len(p) > 1000
    # màu lấy từ ảnh keyframe tại đúng pixel (chỉ để nhìn khi chấm tay): đủ ba kênh, đỏ và xanh lá phủ cả khoảng giá trị ảnh
    assert all(pts[c].dtype == np.uint8 and len(pts[c]) == len(p) for c in ("red", "green", "blue"))
    assert pts["red"].min() < 40 and pts["red"].max() > 215 and pts["green"].min() < 40 and pts["green"].max() > 215
    # điểm B1 = điểm hệ chunk 0 × s_true: độ sâu z trong [1,6 · 2,5, 2,4 · 2,5]
    assert 1.6 * S_TRUE - 0.1 < p[:, 2].min() and p[:, 2].max() < 2.4 * S_TRUE + 0.1
    cams = {int(k): np.array(v) for k, v in b1.read_json(layout.vggt_metric / "cameras_metric.json")["centers"].items()}
    assert sorted(cams) == list(range(N_VIEWS)) and all(np.allclose(cams[v], S_TRUE * _center(v), atol=1e-3) for v in cams)


def test_thieu_quan_sat_hoac_chunk_thi_bao_loi(tmp_path, cfg):
    layout, _ = _make_scene(tmp_path, None)
    write_json(layout.ground_truth / "scale_anchor.json", {"id": "S05", "L_real": 1.0})
    with pytest.raises(StageError, match="observations_2d"):
        b1.build_b1(layout, cfg, log=lambda m: None)
    with pytest.raises(StageError):
        b1.build_b1(SceneLayout(tmp_path / "trong"), cfg, log=lambda m: None)


def test_fit_sim3_trimmed_chiu_ngoai_lai():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(500, 3))
    s, r, t = 1.3, _rot("z", 40.0), np.array([0.5, 1.0, -1.0])
    y = s * x @ r.T + t
    y[:25] += 5.0                                                                    # 5% ngoại lai
    s_hat, r_hat, t_hat, info = b1.fit_sim3_trimmed(x, y)
    assert s_hat == pytest.approx(s, rel=1e-6) and np.allclose(r_hat, r) and np.allclose(t_hat, t) and info["n_used"] == 475
