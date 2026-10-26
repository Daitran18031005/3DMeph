"""Test plane-gated refinement với bảng P1–P7 của đề cương (ĐC §17.2, §20.1)."""

import numpy as np
import pytest

from pipeline.plane_gate.gate import (
    angle_to_plane_deg,
    force_project,
    gate_mask,
    is_structural,
    project_to_plane,
    residual,
    signed_distance,
)

TAU_R, TAU_N, TAU_W, ALPHA = 0.05, 15.0, 0.5, 0.5
WALL = (np.array([1.0, 0.0, 0.0]), 0.0)    # tường x = 0
FLOOR = (np.array([0.0, 0.0, 1.0]), 0.0)   # sàn z = 0

# (khoảng cách tới mặt phẳng (m), θ (độ), nhãn, w, mặt phẳng)
TABLE = [
    (0.012, 6, "wall", 0.90, WALL),     # P1
    (0.020, 9, "wall", 0.80, WALL),     # P2
    (0.18, 0, "cabinet", 0.70, WALL),   # P3: trên tủ, xa tường
    (0.015, 5, "chair", 0.80, WALL),    # P4: sát tường nhưng không phải cấu trúc
    (0.025, 4, "wall", 0.30, WALL),     # P5: w < τ_w
    (0.008, 3, "wall", 0.95, WALL),     # P6
    (0.75, 2, "table", 0.90, FLOOR),    # P7: mặt bàn, xét với mặt phẳng sàn
]


def _points():
    pts = []
    for dist, _theta, _lab, _w, (n, _d) in TABLE:
        if n[0] == 1.0:
            pts.append([dist, 1.5, 1.2])
        else:
            pts.append([0.5, 1.2, dist])
    return np.array(pts)


def test_gate_matches_pdf_table():
    pts = _points()
    g = []
    for p, (dist, theta, lab, w, (n, d)) in zip(pts, TABLE):
        r = residual(p, n, d)
        assert r[0] == pytest.approx(dist)
        g.append(bool(gate_mask(r, np.array([theta]), is_structural([lab]), np.array([w]), TAU_R, TAU_N, TAU_W)[0]))
    assert g == [True, True, False, False, False, True, False]  # g = 1,1,0,0,0,1,0


def test_projection_shifts_match_pdf():
    pts = _points()
    expected_shift_cm = [0.6, 1.0, 0.0, 0.0, 0.0, 0.4, 0.0]
    gs = [1, 1, 0, 0, 0, 1, 0]
    for p, g, (dist, _t, _l, _w, (n, d)), exp in zip(pts, gs, TABLE, expected_shift_cm):
        p2 = project_to_plane(p, n, d, np.array([g]), ALPHA)[0]
        assert np.linalg.norm(p2 - p) * 100 == pytest.approx(exp, abs=1e-6)


def test_p1_example_coordinates():
    # §17.2: P = (0,012; 1,5; 1,2) → P' = (0,006; 1,5; 1,2): chỉ toạ độ vuông góc tường thay đổi
    p2 = project_to_plane(np.array([[0.012, 1.5, 1.2]]), *WALL, np.array([1]), ALPHA)[0]
    assert p2 == pytest.approx([0.006, 1.5, 1.2])


def test_all_four_conditions_are_required():
    base = dict(r=np.array([0.01]), theta_deg=np.array([5.0]), s_is_struct=np.array([True]), w=np.array([0.9]))
    assert gate_mask(**base, tau_r=TAU_R, tau_n_deg=TAU_N, tau_w=TAU_W)[0]
    for key, bad in (("r", np.array([0.2])), ("theta_deg", np.array([40.0])),
                     ("s_is_struct", np.array([False])), ("w", np.array([0.1]))):
        args = {**base, key: bad}
        assert not gate_mask(**args, tau_r=TAU_R, tau_n_deg=TAU_N, tau_w=TAU_W)[0]


def test_force_project_ablation_flattens_the_table():
    # §20.1: kéo mọi điểm về sàn → mặt bàn P7 (r = 75 cm) bị dịch 0,5 × 75 = 37,5 cm
    p7 = np.array([[0.5, 1.2, 0.75]])
    out = force_project(p7, [FLOOR], ALPHA)
    assert np.linalg.norm(out - p7) * 100 == pytest.approx(37.5)
    assert out[0, 2] == pytest.approx(0.375)


def test_force_project_picks_nearest_plane():
    p = np.array([[0.02, 1.0, 1.0]])  # sát tường hơn sàn
    out = force_project(p, [WALL, FLOOR], 1.0)
    assert out[0] == pytest.approx([0.0, 1.0, 1.0])


def test_angle_to_plane_is_unsigned_and_in_0_90():
    n = np.array([1.0, 0.0, 0.0])
    tilted = np.array([[np.cos(np.radians(6)), np.sin(np.radians(6)), 0.0]])
    assert angle_to_plane_deg(tilted, n)[0] == pytest.approx(6.0)
    assert angle_to_plane_deg(-tilted, n)[0] == pytest.approx(6.0)  # pháp tuyến đảo dấu vẫn 6°
    assert angle_to_plane_deg(np.array([[0.0, 1.0, 0.0]]), n)[0] == pytest.approx(90.0)


def test_alpha_must_be_in_unit_interval():
    for bad in (0.0, 1.5, -0.1):
        with pytest.raises(ValueError):
            project_to_plane(np.zeros((1, 3)), *WALL, np.array([1]), bad)


def test_signed_distance_keeps_sign():
    assert signed_distance(np.array([[-0.03, 0, 0]]), *WALL)[0] == pytest.approx(-0.03)
    assert residual(np.array([[-0.03, 0, 0]]), *WALL)[0] == pytest.approx(0.03)
