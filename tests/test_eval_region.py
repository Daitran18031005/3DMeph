"""Test vùng đánh giá Chamfer/F (pipeline/eval/region.py): box so với visible_gt/visible_both, camera GT sai, che khuất, hỗ trợ của Faro, vùng chung cho mọi biến thể."""

import copy

import numpy as np
import pytest

from pipeline.common import config as cfgmod
from pipeline.common.io import SceneLayout, write_json
from pipeline.common.schema import write_keyframes_csv
from pipeline.common.visibility import point_visibility
from pipeline.eval import region as rg

S_M = 0.5
R_M = np.array([[np.cos(0.5), -np.sin(0.5), 0], [np.sin(0.5), np.cos(0.5), 0], [0, 0, 1.0]])    # scene → mô hình: p_model = R_M·p_scene + T_M
T_M = np.array([1.0, 2.0, 3.0])
R_WC = np.array([[0, 0, 1.0], [-1, 0, 0], [0, -1, 0]])                                            # camera nhìn +x (scene), x phải = −y, y xuống = −z
K = np.array([[200.0, 0, 160], [0, 200.0, 120], [0, 0, 1.0]])
W, H = 320, 240
N = 8
CENTERS = {v: np.array([0.05 * v, 0.1 * v, 0.04 * (v % 3)]) for v in range(N)}                  # không thẳng hàng: Kabsch xác định đủ xoay


def _plane_x(x, y0=-1.0, y1=1.0, z0=-1.0, z1=1.0, step=0.05):
    y, z = np.meshgrid(np.arange(y0, y1 + 1e-9, step), np.arange(z0, z1 + 1e-9, step))
    return np.stack([np.full(y.size, x), y.ravel(), z.ravel()], axis=1)


@pytest.fixture()
def world(tmp_path):
    layout = SceneLayout(tmp_path / "scene")
    write_keyframes_csv([{"view_id": v, "w": W, "h": H} for v in range(N)], layout.metadata / "keyframes.csv")
    write_json(layout.alignment / "scale.json", {"s_m": S_M})
    cams = {}
    for v, c in CENTERS.items():
        r_cw = (R_M @ R_WC).T                                                                    # world→camera trong hệ mô hình
        c_colmap = (R_M @ c + T_M) / S_M                                                         # đv COLMAP = mét / s_m
        cams[v] = {"K": K, "R": r_cw, "t": -r_cw @ c_colmap, "center": c_colmap}
    wall = _plane_x(3.0)                                                                          # W: thấy bởi mọi camera
    behind = _plane_x(5.0)                                                                        # O: sau W, bị che
    outside = np.stack([np.linspace(0.0, 3.0, 61), np.full(61, 20.0), np.zeros(61)], axis=1)     # X: y = 20, ngoài tầm nhìn mọi camera
    faro = np.concatenate([wall, behind, outside])
    return layout, cams, faro, len(wall), len(behind), len(outside)


@pytest.fixture()
def cfg():
    c = copy.deepcopy(cfgmod.load_config())
    c["eval"]["crop_margin_m"] = 5.0                                                              # hộp rộng như khi pose GT sai: chứa cả vùng ngoài tầm nhìn
    return c


def _build(world, cfg, mode, gt):
    layout, cams, faro, *_ = world
    c = copy.deepcopy(cfg)
    c["eval"]["region"]["mode"] = mode
    return rg.build_region(layout, c, gt, faro, lambda _l: cams)


def test_visible_gt_bo_vung_ngoai_tam_nhin_va_vung_bi_che_con_box_giu_thua(world, cfg):
    gt = {v: c.copy() for v, c in CENTERS.items()}
    gt[7] = np.array([0.0, 30.0, 0.0])                                                            # pose ARKit nhảy xa (như 42445022)
    n_wall, n_behind, n_out = world[3:]
    box = _build(world, cfg, "box", gt)
    assert box.n_views == N and (np.abs(box.faro[:, 1] - 20.0) < 1e-9).sum() == n_out                # hộp phình theo camera sai: giữ cả vùng X
    assert box.gt_kept_frac > 0.9
    vg = _build(world, cfg, "visible_gt", gt)
    assert vg.dropped_views == [7] and vg.n_views == N - 1                                         # camera sai bị cắt tỉa
    kept = vg.faro
    assert not (np.abs(kept[:, 1] - 20.0) < 1e-9).any()                                            # X (ngoài tầm nhìn) bị bỏ
    assert not np.isclose(kept[:, 0], 5.0).any()                                                   # O (sau tường) bị che nên bị bỏ
    assert np.isclose(kept[:, 0], 3.0).sum() >= 0.9 * n_wall                                       # W giữ lại
    assert vg.gt_kept_frac == pytest.approx(len(kept) / (n_wall + n_behind + n_out))


def test_vung_khong_doi_khi_them_camera_gt_sai_da_bi_cat_tia(world, cfg):
    gt = {v: c.copy() for v, c in CENTERS.items()}
    gt[7] = np.array([0.0, 30.0, 0.0])
    a = _build(world, cfg, "visible_gt", gt)
    gt2 = dict(gt)
    gt2[6] = np.array([0.0, -40.0, 5.0])                                                           # thêm một pose GT sai nữa (view 6 vốn đúng)
    b = _build(world, cfg, "visible_gt", gt2)
    assert set(b.dropped_views) == {6, 7}
    assert len(b.faro) >= 0.95 * len(a.faro) and not (np.abs(b.faro[:, 1] - 20.0) < 1e-9).any()      # vùng gần như không đổi, vẫn không có X


def test_visible_both_bo_diem_mo_hinh_khong_co_faro_ho_tro_hoac_ngoai_tam_nhin(world, cfg):
    gt = {v: c.copy() for v, c in CENTERS.items()}
    reg = _build(world, cfg, "visible_both", gt)
    on_wall = _plane_x(3.0, -0.5, 0.5)                                                              # trùng Faro, được thấy
    floating = _plane_x(2.0, 0.6, 0.9, -0.2, 0.2)                                                    # được thấy (lệch sang bên, không che tường) nhưng cách Faro 1 m (> gt_support_m)
    outside = np.stack([np.linspace(0.0, 3.0, 20), np.full(20, 20.0), np.zeros(20)], axis=1)        # ngoài tầm nhìn
    model = np.concatenate([on_wall, floating, outside])
    kept, frac = reg.filter_model(model)
    assert frac == pytest.approx(len(kept) / len(model))
    assert len(kept) >= 0.9 * len(on_wall) and np.isclose(kept[:, 0], 3.0).sum() >= 0.9 * len(on_wall)
    assert not np.isclose(kept[:, 0], 2.0).any() and not (np.abs(kept[:, 1] - 20.0) < 1e-9).any()
    assert _build(world, cfg, "visible_gt", gt).filter_model(model)[1] is None                       # visible_gt không lọc mô hình


def test_point_visibility_che_khuat_diem_sau_tuong_bi_loai():
    cam = {"R": R_WC, "c": np.zeros(3), "k": (200.0, 200.0, 160.0, 120.0), "rot": "none"}
    wall, behind = _plane_x(3.0), _plane_x(5.0)
    nvis, _ = point_visibility(np.concatenate([wall, behind]), [cam], (W, H), with_spread=False)
    assert (nvis[: len(wall)] >= 1).mean() > 0.9 and (nvis[len(wall):] == 0).all()


def test_che_do_khong_hop_le_bi_tu_choi(world, cfg):
    with pytest.raises(ValueError, match="không hợp lệ"):
        _build(world, cfg, "tuy_y", {v: c for v, c in CENTERS.items()})

