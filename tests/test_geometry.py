"""Test vector hình học lấy từ đề cương (ĐC §6.1, §10.2, §10.3, §14.2, §14.3, §15.1)."""

import numpy as np
import pytest

from pipeline.common.geometry import (
    apply_sim3,
    camera_center,
    euclid,
    invert_pose,
    overlap_percent,
    project,
    reproj_error,
    rodrigues,
    umeyama_sim3,
    valid_depth,
)
from pipeline.common.io import parse_traj_line

# ĐC §15.1: 4 camera quanh bàn ăn R02
X = np.array([[0, 0], [2, 0], [2, 1], [0, 1]], dtype=float)
Y = np.array([[1.0, 2.0], [1.0, 8.4], [-2.2, 8.4], [-2.2, 2.0]])


def test_umeyama_pdf_vector():
    s, r, t = umeyama_sim3(X, Y)
    assert s == pytest.approx(3.20, abs=1e-9)
    assert np.allclose(r, [[0, -1], [1, 0]], atol=1e-9)  # xoay 90° ngược chiều kim đồng hồ
    assert np.allclose(t, [1.0, 2.0], atol=1e-9)
    assert np.allclose(apply_sim3(s, r, t, X), Y, atol=1e-9)


def test_umeyama_intermediate_numbers_match_pdf():
    # Các số trung gian ghi trong §15.1: μx, μy, σx², Σxy, D
    mu_x, mu_y = X.mean(0), Y.mean(0)
    assert np.allclose(mu_x, [1.0, 0.5]) and np.allclose(mu_y, [-0.6, 5.2])
    sigma2 = ((X - mu_x) ** 2).sum(1).mean()
    assert sigma2 == pytest.approx(1.25)
    sigma_xy = (Y - mu_y).T @ (X - mu_x) / 4
    assert np.allclose(sigma_xy, [[0, -0.8], [3.2, 0]])
    assert np.allclose(np.linalg.svd(sigma_xy)[1], [3.2, 0.8])


def test_umeyama_distance_ratio():
    # ‖x2−x1‖ = 2,00 → ‖y2−y1‖ = 6,40; 6,40 / 2,00 = 3,20
    assert np.linalg.norm(X[1] - X[0]) == pytest.approx(2.0)
    assert np.linalg.norm(Y[1] - Y[0]) == pytest.approx(6.4)


def test_umeyama_recovers_random_3d_sim3():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(20, 3))
    s_true, r_true, t_true = 0.37, rodrigues([0.3, -1.1, 0.5]), np.array([4.0, -2.0, 0.5])
    y = apply_sim3(s_true, r_true, t_true, x)
    s, r, t = umeyama_sim3(x, y)
    assert s == pytest.approx(s_true, rel=1e-9)
    assert np.allclose(r, r_true, atol=1e-9) and np.allclose(t, t_true, atol=1e-9)
    assert np.linalg.det(r) == pytest.approx(1.0)


def test_umeyama_rejects_degenerate_input():
    with pytest.raises(ValueError):
        umeyama_sim3(np.zeros((4, 3)), np.ones((4, 3)))  # σx² = 0
    with pytest.raises(ValueError):
        umeyama_sim3(np.zeros((1, 3)), np.zeros((1, 3)))  # quá ít điểm
    with pytest.raises(ValueError):
        umeyama_sim3(np.zeros((4, 3)), np.zeros((3, 3)))  # shape lệch


def test_pose_inversion_pdf_example():
    # ĐC §10.2: dòng .traj "5201.456 0 0 -1.5708 -1.20 1.65 -1.40"
    ts, r, t = parse_traj_line("5201.456 0 0 -1.5708 -1.20 1.65 -1.40")
    assert ts == pytest.approx(5201.456)
    assert np.allclose(r, [[0, 1, 0], [-1, 0, 0], [0, 0, 1]], atol=1e-3)
    assert np.allclose(t, [-1.20, 1.65, -1.40])
    assert np.allclose(camera_center(r, t), [1.65, 1.20, 1.40], atol=1e-3)
    # Nếu quên đảo và lấy thẳng t làm tâm camera thì ra điểm ngoài phòng, dưới sàn
    assert t[0] < 0 and t[2] < 0
    twc = invert_pose(r, t)
    tcw = np.eye(4)
    tcw[:3, :3], tcw[:3, 3] = r, t
    assert np.allclose(twc @ tcw, np.eye(4), atol=1e-9)
    assert np.allclose(twc[:3, 3], [1.65, 1.20, 1.40], atol=1e-3)


def test_project_pdf_example():
    # ĐC §14.2: fx=fy=500, cx=320, cy=240, R=I, t=0, X=(0,40; −0,20; 2,00) → (420; 190)
    k = np.array([[500.0, 0, 320], [0, 500, 240], [0, 0, 1]])
    uv = project(k, np.eye(3), np.zeros(3), np.array([[0.40, -0.20, 2.00]]))
    assert np.allclose(uv, [[420.0, 190.0]])


def test_reproj_error_pdf_example():
    # ĐC §14.3: dự đoán (812,0; 440,0), quan sát (809,9; 441,2) → 2,42 px
    k = np.eye(3)
    err = reproj_error(k, np.eye(3), np.zeros(3), np.array([[812.0, 440.0, 1.0]]), [[809.9, 441.2]])
    assert err[0] == pytest.approx(2.42, abs=5e-3)


def test_overlap_percent_pdf_example():
    assert overlap_percent(2.0, 0.6) == pytest.approx(70.0)  # đạt
    assert overlap_percent(2.0, 1.0) == pytest.approx(50.0)  # dưới ngưỡng 60%
    with pytest.raises(ValueError):
        overlap_percent(2.0, 2.5)


def test_valid_depth_pdf_example():
    # ĐC §10.3: 2,05 hợp lệ; 14,2 (nhìn qua cửa sổ) và 0,02 (sát ống kính) không hợp lệ
    assert valid_depth(np.array([2.05, 14.2, 0.02])).tolist() == [True, False, False]
    assert valid_depth(np.array([0.05, 10.0])).tolist() == [True, True]  # biên đóng


def test_euclid_two_point_measure():
    # ĐC §19.1 (30): A=(0,52; 0,75; 1,20), B=(1,90; 0,75; 1,20) → 1,38 m
    assert euclid((0.52, 0.75, 1.20), (1.90, 0.75, 1.20)) == pytest.approx(1.38, abs=1e-9)
