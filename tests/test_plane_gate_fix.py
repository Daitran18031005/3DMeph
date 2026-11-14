"""Test sửa cổng plane gate (M4 đợt 3d): nhãn sàn thấp nhất, thêm lượt tìm tường, khoá k riêng cho cổng. Mặc định phải giữ hành vi cũ."""

import json

import numpy as np
import pytest
import test_m1d_stages as base

from pipeline.common import config as cfgmod
from pipeline.plane_gate import stage as gs


def _planes(heights, label="floor"):
    return [{"id": i, "label": label, "height_m": h, "n_inliers": 100} for i, h in enumerate(heights)]


def test_restrict_horizontal_mac_dinh_giu_nguyen_va_lowest_chi_giu_mat_thap_nhat():
    ps = _planes([-1.40, -1.32, -0.50])
    assert [p["label"] for p in gs.restrict_horizontal([dict(p) for p in ps], "any", 0.0)] == ["floor"] * 3          # hành vi cũ
    out0 = gs.restrict_horizontal([dict(p) for p in ps], "lowest", 0.0)
    assert [p["label"] for p in out0] == ["floor", "horizontal_other", "horizontal_other"]                              # chỉ mặt thấp nhất
    out1 = gs.restrict_horizontal([dict(p) for p in ps], "lowest", 0.10)
    assert [p["label"] for p in out1] == ["floor", "floor", "horizontal_other"]                                         # sàn cong: mặt cách 8 cm vẫn là sàn
    ceil = gs.restrict_horizontal(_planes([2.4, 1.9, 2.45], "ceiling"), "lowest", 0.0)
    assert [p["label"] for p in ceil] == ["horizontal_other", "horizontal_other", "ceiling"]                            # trần = mặt cao nhất
    with pytest.raises(ValueError):
        gs.restrict_horizontal(ps, "nhat", 0.0)


def _scene_thieu_tuong(rng):
    """Ba mặt ngang lớn (sàn, mặt giữa, trần) và một bức tường nhỏ hơn: RANSAC tuần tự với max_planes = 3 không bao giờ tới tường."""
    def hor(y, n):
        return np.stack([rng.uniform(0, 4, n), np.full(n, y), rng.uniform(0, 3, n)], axis=1)
    wall = np.stack([np.zeros(4000), rng.uniform(0, 2.5, 4000), rng.uniform(0, 3, 4000)], axis=1)
    return np.vstack([hor(0.0, 20000), hor(1.0, 15000), hor(2.5, 20000), wall]) + rng.normal(0, 0.005, (59000, 3))


def test_find_planes_them_luot_tim_tuong_khi_thieu_va_mac_dinh_khong_them():
    rng = np.random.default_rng(0)
    pts = _scene_thieu_tuong(rng)
    u, ch = np.array([0.0, 1.0, 0.0]), np.array([1.2])
    cu = gs.find_planes(pts, u, ch, 0.05, 15, 3, 0.02)                                                                  # cũ: không tường
    assert sum(p["label"] == "wall" for p in cu) == 0 and sum(p["label"] == "floor" for p in cu) == 2                  # sàn (y=0) và mặt giữa (y=1) đều là "sàn" dưới camera 1,2 m
    nm = gs.find_planes(pts, u, ch, 0.05, 15, 3, 0.02, normals=gs.estimate_normals(pts, 30), floor_rule="lowest", floor_band=0.0, min_walls=1, wall_passes=4)
    walls = [p for p in nm if p["label"] == "wall"]
    assert len(walls) == 1 and abs(abs(walls[0]["n"][0]) - 1) < 0.02 and walls[0]["source"] == "extra_wall_pass"       # pháp tuyến ≈ ±x
    assert sum(p["label"] == "floor" for p in nm) == 1 and sum(p["label"] == "horizontal_other" for p in nm) == 1      # một sàn, mặt giữa không còn là sàn
    with pytest.raises(ValueError):
        gs.find_planes(pts, u, ch, 0.05, 15, 3, 0.02, min_walls=1, wall_passes=2)                                      # thiếu normals


def test_mac_dinh_moi_khoa_ngay_15_11_va_cau_hinh_cu_chon_lai_duoc(tmp_path):
    cfg = cfgmod.load_config()
    assert cfg["plane"]["gate_normal_knn"] == 300 and cfg["plane"]["floor_rule"] == "lowest" and cfg["plane"]["min_walls"] == 1 and cfg["plane"]["floor_band_m"] == 0.0
    lay, cams = base.synthetic_gate_scene(tmp_path, w_k=0.9)
    gs.run_gate(lay, cfg, log=lambda m: None, load_cameras=lambda _l: cams)
    p0 = json.loads((lay.plane_refinement / "planes.json").read_text(encoding="utf-8"))["params"]
    assert p0["normal_knn"] == 300 and p0["floor_rule"] == "lowest"
    old = cfgmod.load_config()
    old["plane"].update(gate_normal_knn=None, floor_rule="any", min_walls=0)                                              # cấu hình cũ chọn lại được
    lay1, cams1 = base.synthetic_gate_scene(tmp_path / "old", w_k=0.9)
    gs.run_gate(lay1, old, log=lambda m: None, load_cameras=lambda _l: cams1)
    p1 = json.loads((lay1.plane_refinement / "planes.json").read_text(encoding="utf-8"))["params"]
    assert p1["normal_knn"] == old["plane"]["normal_knn"] and p1["floor_rule"] == "any"
    cfg2 = cfgmod.load_config()
    cfg2["plane"]["gate_normal_knn"] = 100
    lay2, cams2 = base.synthetic_gate_scene(tmp_path / "k100", w_k=0.9)
    gs.run_gate(lay2, cfg2, log=lambda m: None, load_cameras=lambda _l: cams2)
    assert json.loads((lay2.plane_refinement / "planes.json").read_text(encoding="utf-8"))["params"]["normal_knn"] == 100
