"""Test stage sfm/mvs: đọc/ghi depth map COLMAP, tín hiệu e_reproj và σ_depth, chạy tiến trình con, chọn model tốt nhất.

Phần chạy COLMAP thật (patch_match_stereo cần GPU) không nằm trong test; nó được kiểm bằng lần chạy thật ở M1a.
"""

import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

from pipeline.colmap import depth_io, run_colmap, signals
from pipeline.common.errors import E_COLMAP_FAILED, E_SFM_FAILED, StageError

REPO_ROOT = Path(__file__).resolve().parents[1]
SPARSE = REPO_ROOT / "data" / "processed" / "images" / "sparse"
pycolmap = pytest.importorskip("pycolmap")


# ---------------------------------------------------------------------------
# depth_io
# ---------------------------------------------------------------------------


def test_depth_map_ghi_doc_khop_va_dung_thu_tu_hang_cot(tmp_path):
    d = np.arange(12, dtype=np.float32).reshape(3, 4)            # H=3, W=4: d[hàng, cột]
    p = tmp_path / "x.jpg.geometric.bin"
    depth_io.write_depth_map(p, d)
    assert p.read_bytes().startswith(b"4&3&1&")                  # width & height & channels
    got = depth_io.read_depth_map(p)
    assert got.shape == (3, 4) and np.array_equal(got, d)
    rgb = np.random.default_rng(0).random((5, 6, 3)).astype(np.float32)
    depth_io.write_depth_map(tmp_path / "c.bin", rgb)
    assert np.array_equal(depth_io.read_depth_map(tmp_path / "c.bin"), rgb)


def test_depth_map_hong(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"4&3&")
    with pytest.raises(ValueError, match="'&'"):
        depth_io.read_depth_map(tmp_path / "a.bin")
    (tmp_path / "b.bin").write_bytes(b"4&3&1&" + np.zeros(5, dtype="<f4").tobytes())
    with pytest.raises(ValueError, match="cần 4×3×1"):
        depth_io.read_depth_map(tmp_path / "b.bin")


# ---------------------------------------------------------------------------
# signals
# ---------------------------------------------------------------------------


def test_sigma_depth_tuyet_doi_va_nan_khi_thieu_depth():
    a = np.array([[1.0, 2.0], [0.0, 3.0]], dtype=np.float32)
    b = np.array([[1.5, 1.0], [2.0, -1.0]], dtype=np.float32)
    s = signals.sigma_depth_map(a, b)
    assert s[0, 0] == pytest.approx(0.5) and s[0, 1] == pytest.approx(1.0)
    assert np.isnan(s[1, 0]) and np.isnan(s[1, 1])
    with pytest.raises(ValueError):
        signals.sigma_depth_map(a, np.zeros((3, 3), dtype=np.float32))


def test_interpolate_e_reproj_idw_va_e_cap_ngoai_ban_kinh():
    xy = np.array([[10.5, 10.5], [20.5, 10.5]])
    e = np.array([1.0, 3.0])
    m = signals.interpolate_e_reproj(xy, e, (40, 60), e_cap=4.0, radius=8.0, k=2)
    assert m.shape == (40, 60) and m.dtype == np.float32
    assert m[10, 10] == pytest.approx(1.0, abs=1e-3) and m[10, 20] == pytest.approx(3.0, abs=1e-3)   # đúng tại quan sát
    assert m[10, 15] == pytest.approx(2.0, abs=1e-2)                                                  # chính giữa: trung bình
    assert m[35, 55] == pytest.approx(4.0)                                                            # xa hơn bán kính: e_cap
    assert np.all(m <= 4.0 + 1e-6) and np.all(m >= 1.0 - 1e-6)
    empty = signals.interpolate_e_reproj(np.empty((0, 2)), np.empty(0), (5, 5), 4.0)
    assert np.all(empty == 4.0)
    one = signals.interpolate_e_reproj(np.array([[2.5, 2.5]]), np.array([2.0]), (6, 6), 4.0, radius=10.0, k=8)
    assert one[2, 2] == pytest.approx(2.0, abs=1e-3) and np.all(one == pytest.approx(2.0, abs=1e-3))


@pytest.mark.skipif(not (SPARSE / "points3D.bin").is_file(), reason="chưa có model COLMAP mẫu ở data/processed")
def test_observations_khop_point3d_error_cua_colmap():
    rec = pycolmap.Reconstruction(str(SPARSE))
    obs = signals.observations_from_model(rec)
    n = len(obs["e_reproj"])
    assert n == sum(len(p.track.elements) for p in rec.points3D.values())
    assert obs["xy"].shape == (n, 2) and obs["image_id"].shape == (n,)
    per_point = {}
    for pid, e in zip(obs["point3d_id"], obs["e_reproj"]):
        per_point.setdefault(int(pid), []).append(e)
    mine = np.array([np.mean(v) for v in per_point.values()])
    theirs = np.array([rec.points3D[k].error for k in per_point])
    assert np.corrcoef(mine, theirs)[0, 1] > 0.999
    assert np.median(np.abs(mine - theirs)) < 2e-3


# ---------------------------------------------------------------------------
# run_cmd, VramPoller, tham số lệnh, chọn model
# ---------------------------------------------------------------------------


def test_run_cmd_thanh_cong_va_that_bai():
    ok = run_colmap.run_cmd(sys.executable, ["-c", "print('xin chao')"], log=lambda m: None, poll_vram=False)
    assert ok["seconds"] >= 0 and ok["peak_vram_mib"] is None
    with pytest.raises(StageError) as e:
        run_colmap.run_cmd(sys.executable, ["-c", "import sys; print('loi that', file=sys.stderr); sys.exit(3)"], log=lambda m: None,
                           poll_vram=False)
    assert e.value.code == E_COLMAP_FAILED and "thoát mã 3" in str(e.value) and "loi that" in str(e.value)


def test_vram_poller_giu_gia_tri_lon_nhat():
    vals = iter([100.0, 300.0, 200.0, 250.0])
    poller = run_colmap.VramPoller(interval=0.01, probe=lambda: next(vals, 50.0))
    with poller:
        import time
        time.sleep(0.15)
    assert poller.baseline == 100.0 and poller.peak == 300.0


def test_tham_so_lenh(tmp_path):
    cam = {"camera_model": "PINHOLE", "fx": 528.5, "fy": 528.5, "cx": 239.3, "cy": 320.6}
    a = run_colmap.feature_extractor_args(tmp_path / "img", tmp_path / "db", cam)
    assert a[0] == "feature_extractor" and "--ImageReader.single_camera" in a
    assert a[a.index("--ImageReader.camera_params") + 1] == "528.5,528.5,239.3,320.6"
    assert "--FeatureExtraction.max_image_size" not in a
    assert a[a.index("--FeatureExtraction.use_gpu") + 1] == 1
    assert run_colmap.feature_extractor_args(tmp_path, tmp_path, cam, None, False)[-1] == 0
    assert "--FeatureExtraction.max_image_size" in run_colmap.feature_extractor_args(tmp_path, tmp_path, cam, 1000)
    assert "--SequentialMatching.overlap" not in run_colmap.sequential_matcher_args(tmp_path / "db")
    s = run_colmap.sequential_matcher_args(tmp_path / "db", 5)
    assert s[s.index("--SequentialMatching.overlap") + 1] == 5
    assert s[s.index("--FeatureMatching.use_gpu") + 1] == 1
    assert run_colmap.sequential_matcher_args(tmp_path / "db", None, False)[-1] == 0


@pytest.mark.skipif(not (SPARSE / "points3D.bin").is_file(), reason="chưa có model COLMAP mẫu ở data/processed")
def test_choose_best_model_doi_ve_sparse_0(tmp_path):
    sparse = tmp_path / "sparse"
    full, small = sparse / "1", sparse / "0"
    shutil.copytree(SPARSE, full)
    small.mkdir(parents=True)
    rec = pycolmap.Reconstruction(str(SPARSE))
    for iid in list(rec.images)[5:]:
        rec.deregister_image(iid)                                 # model nhỏ hơn: chỉ 5 ảnh đăng ký
    rec.write(str(small))
    best, n = run_colmap.choose_best_model(sparse)
    assert n == 2 and best.num_reg_images() == pycolmap.Reconstruction(str(SPARSE)).num_reg_images()
    assert pycolmap.Reconstruction(str(sparse / "0")).num_reg_images() == best.num_reg_images()   # model tốt nhất đã thành sparse/0
    assert pycolmap.Reconstruction(str(sparse / "1")).num_reg_images() == 5


def test_choose_best_model_khong_co_model(tmp_path):
    (tmp_path / "sparse").mkdir()
    with pytest.raises(StageError) as e:
        run_colmap.choose_best_model(tmp_path / "sparse")
    assert e.value.code == E_SFM_FAILED
