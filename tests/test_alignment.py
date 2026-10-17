"""Test căn hệ toạ độ và đổi sang mét (ĐC §15.1, §15.2)."""

import numpy as np
import pytest

from pipeline.alignment.ransac import (
    metric_scale, ransac_sim3, reference_distance, threshold_from_ratio, to_metric, total_scale,
)
from pipeline.common.geometry import apply_sim3, rodrigues, umeyama_sim3


def _synthetic_pairs():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(12, 3))
    s_true, r_true, t_true = 3.2, rodrigues([0.1, -0.4, 0.9]), np.array([1.0, 2.0, 3.0])
    y = apply_sim3(s_true, r_true, t_true, x)
    return x, y, s_true, r_true, t_true


def test_ransac_rejects_two_wrong_pairs_out_of_twelve():
    # ĐC §15.1: 12 cặp tâm camera của chunk 1, 2 cặp sai → giữ 10 inlier
    x, y, s_true, r_true, t_true = _synthetic_pairs()
    y_bad = y.copy()
    y_bad[3] += [5.0, -4.0, 3.0]
    y_bad[8] += [-6.0, 2.0, 7.0]

    s_all, _, _ = umeyama_sim3(x, y_bad)  # bình phương tối thiểu trên cả 12 cặp bị kéo lệch
    assert abs(s_all - s_true) > 1e-2

    res = ransac_sim3(x, y_bad, thresh=0.05)
    assert res["n_pairs"] == 12 and res["n_inliers"] == 10
    assert not res["inliers"][3] and not res["inliers"][8]
    assert res["s"] == pytest.approx(s_true, rel=1e-9)
    assert np.allclose(res["R"], r_true, atol=1e-9) and np.allclose(res["t"], t_true, atol=1e-9)
    assert res["rmse"] < 1e-9


def test_ransac_random_sampling_branch_is_deterministic():
    x, y, *_ = _synthetic_pairs()
    y_bad = y.copy()
    y_bad[0] += 9.0
    a = ransac_sim3(x, y_bad, thresh=0.05, max_iters=50, seed=7)  # C(12,3)=220 > 50: lấy mẫu ngẫu nhiên
    b = ransac_sim3(x, y_bad, thresh=0.05, max_iters=50, seed=7)
    assert a["s"] == b["s"] and np.array_equal(a["inliers"], b["inliers"])
    assert a["n_inliers"] == 11


def test_ransac_needs_enough_pairs_and_inliers():
    x, y, *_ = _synthetic_pairs()
    with pytest.raises(ValueError):
        ransac_sim3(x[:2], y[:2], thresh=0.1)
    with pytest.raises(ValueError):
        ransac_sim3(x, np.random.default_rng(3).normal(size=y.shape) * 50, thresh=1e-6)


def test_metric_chain_pdf_example():
    # ĐC §15.2: bàn 0,215 đv VGGT; s = 3,20; mốc 1,50 m / 0,75 đv → s_m = 2,00
    s_m = metric_scale(1.50, 0.75)
    assert s_m == pytest.approx(2.00)
    s, r, t = 3.20, np.eye(3), np.zeros(3)
    a = np.array([[0.118, -0.021, 0.402]])
    b = np.array([[0.333, -0.021, 0.402]])
    assert np.linalg.norm(b - a) == pytest.approx(0.215)
    in_colmap = np.linalg.norm(apply_sim3(s, r, t, b) - apply_sim3(s, r, t, a))
    assert in_colmap == pytest.approx(0.688, abs=1e-3)
    in_metres = np.linalg.norm(to_metric(b, s, r, t, s_m) - to_metric(a, s, r, t, s_m))
    assert in_metres == pytest.approx(1.376, abs=1e-3)
    assert total_scale(s, s_m) == pytest.approx(6.40)
    assert 0.215 * total_scale(s, s_m) == pytest.approx(1.376, abs=1e-3)


def test_metric_scale_pdf_room_example():
    # §8.1: phòng 1,62 đv × 2,00 = 3,24 m; sai 6 cm so với laser 3,30 m
    s_m = metric_scale(1.50, 0.75)
    assert 1.62 * s_m == pytest.approx(3.24)
    with pytest.raises(ValueError):
        metric_scale(1.5, 0.0)


def test_threshold_from_ratio():
    y = np.array([[0, 0, 0], [1, 0, 0], [3, 0, 0], [6, 0, 0]], dtype=float)
    assert reference_distance(y) == pytest.approx(2.0)  # trung vị của 1, 2, 3
    assert threshold_from_ratio(y, 0.1) == pytest.approx(0.2)
    with pytest.raises(ValueError):
        threshold_from_ratio(y, None)  # align.ransac.max_error_ratio chưa có căn cứ
