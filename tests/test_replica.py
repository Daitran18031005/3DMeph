"""Test phần Replica (M5): lọc tên file khi tải nhãn, quy ước camera khi render, biến thể abl_gate."""

import importlib.util
import sys
from pathlib import Path

import numpy as np

from pipeline.common.io import SceneLayout
from pipeline.eval.variants import VARIANTS, cloud_path, variant_layout

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tai_nhan_chi_lay_file_nhan_va_chan_duong_dan_doc(tmp_path):
    dl = _load("download_replica_labels")
    assert dl.target_for("replica_v1/room_0/preseg.json", tmp_path) == tmp_path / "room_0" / "preseg.json"
    assert dl.target_for("replica_v1/room_0/mesh.ply", tmp_path) is None              # mesh đã có: bỏ qua
    assert dl.target_for("../evil/preseg.json", tmp_path) is None
    assert dl.target_for("/abs/room_0/glass.sur", tmp_path) is None


def test_look_rotation_la_quy_uoc_opencv_z_toi_y_xuong():
    rr = _load("render_replica")
    fwd = np.array([1.0, 0.0, 0.0])
    R = rr.look_rotation(fwd)
    assert np.allclose(R @ R.T, np.eye(3)) and np.isclose(np.linalg.det(R), 1)
    assert np.allclose(R @ fwd, [0, 0, 1])                        # hướng nhìn là +z camera
    assert np.allclose(R @ rr.UP, [0, -1, 0])                     # hướng lên của thế giới là −y camera (y xuống)


def test_preseg_chi_so_tu_giac_theo_segment_ra_ma_tam_giac_hai_nua():
    from pipeline.eval.plane_gt import quad_segments_to_triangles
    meta = [{"id": 7, "numPrimitives": 2}, {"id": 3, "numPrimitives": 1}]
    ids = np.array([2, 0, 1], dtype=np.uint64)                      # segment 7 = tứ giác 2, 0; segment 3 = tứ giác 1
    assert quad_segments_to_triangles(ids, meta, 6).tolist() == [7, 3, 7, 7, 3, 7]


def test_p2plane_va_plane_recall_tren_mat_tong_hop():
    from pipeline.eval.plane_gt import plane_metrics
    rng = np.random.default_rng(0)
    floor = np.c_[rng.uniform(0, 2, (4000, 2)), np.zeros(4000)]
    gt = {"points": floor, "label": np.zeros(4000, dtype=np.int64), "planes": [{"n": np.array([0, 0, 1.0]), "d": 0.0}]}
    cfg = {"assign_m": 0.10, "min_points": 200, "max_angle_deg": 10, "max_offset_m": 0.05}
    model = floor[:1000] + np.array([0, 0, 0.03])                    # mô hình lệch đều 3 cm
    m = plane_metrics(model, gt, cfg)
    assert abs(m["p2plane_cm"] - 3.0) < 1e-6 and m["plane_recall"] == 1.0
    m2 = plane_metrics(floor[:1000] + np.array([0, 0, 0.08]), gt, cfg)  # lệch 8 cm > 5 cm: còn chấm P2Plane nhưng không "tìm thấy"
    assert abs(m2["p2plane_cm"] - 8.0) < 1e-6 and m2["plane_recall"] == 0.0


def test_abl_gate_co_thu_muc_bien_the_rieng(tmp_path):
    lay = SceneLayout(tmp_path)
    assert "abl_gate" in VARIANTS
    assert variant_layout(lay, "abl_gate").plane_refinement == lay.proposed / "variants" / "abl_gate" / "plane_refinement"
    assert cloud_path(lay, "abl_gate") != cloud_path(lay, "proposed")
