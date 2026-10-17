"""Test confidence fusion với ví dụ ba ảnh A, B, C nhìn cùng một điểm mép bàn (ĐC §16.4)."""

import numpy as np
import pytest

from pipeline.common.quality import f_err
from pipeline.fusion.fusion import (
    fuse, gate_weight, normalize_weights, raw_weight, weights_from_signals,
)

# Bảng "Bước 1" của §16.4 (đã đổi sang điểm 0..1): c_model, f(e_reproj), f(σ_depth), q_blur, q_texture, q_exposure
ROWS = np.array([
    [0.98, 0.97, 0.98, 0.99, 0.97, 1.00],  # A
    [0.90, 0.92, 0.95, 0.90, 0.95, 0.98],  # B
    [0.70, 0.30, 0.35, 0.35, 0.80, 0.60],  # C
])
DEPTH = np.array([2.00, 2.08, 3.40])


def test_raw_weights_pdf():
    w = raw_weight(*ROWS.T)
    assert w == pytest.approx([0.895, 0.659, 0.012], abs=1e-3)


def test_normalized_weights_and_fused_depth_pdf():
    w = raw_weight(*ROWS.T)
    p_hat, w_tilde = fuse(DEPTH, w)
    assert w_tilde == pytest.approx([0.571, 0.421, 0.008], abs=1e-3)
    assert w_tilde.sum() == pytest.approx(1.0)
    assert p_hat == pytest.approx(2.04, abs=5e-3)  # thật 2,05 m, sai ~1 cm
    assert DEPTH.mean() == pytest.approx(2.49, abs=5e-3)  # trung bình đơn giản sai ~44 cm
    assert w_tilde[2] < 0.01  # ảnh C chỉ còn dưới 1% phiếu


def test_gate_weight_choice_vs_alternatives():
    # w_k = Σ w̃·w (quyết định của nhóm): 0,79; trung bình cộng 0,52 (sát ngưỡng 0,5); max 0,895
    w = raw_weight(*ROWS.T)
    _, w_tilde = fuse(DEPTH, w)
    assert gate_weight(w, w_tilde) == pytest.approx(0.789, abs=2e-3)
    assert w.mean() == pytest.approx(0.522, abs=1e-3)
    assert w.max() == pytest.approx(0.895, abs=1e-3)


def test_gate_weight_single_view_equals_raw_weight():
    w = np.array([0.37])
    _, w_tilde = fuse(np.array([2.0]), w)
    assert w_tilde[0] == pytest.approx(1.0)
    assert gate_weight(w, w_tilde) == pytest.approx(0.37)


def test_f_err_pdf_values():
    # (21): f(0)=1, f(τ)=0,37, f(2τ)=0,14; ví dụ τ_e = 2 px
    assert f_err(0.0, 2.0) == pytest.approx(1.0)
    assert f_err(2.0, 2.0) == pytest.approx(0.37, abs=5e-3)
    assert f_err(4.0, 2.0) == pytest.approx(0.14, abs=5e-3)
    assert f_err([0.06, 0.17, 2.4], 2.0) == pytest.approx([0.97, 0.92, 0.30], abs=5e-3)
    assert f_err(0.21, 0.20) == pytest.approx(0.35, abs=5e-3)
    with pytest.raises(ValueError):
        f_err(1.0, 0.0)


def test_weights_from_signals_matches_pdf_within_rounding():
    # Cùng ví dụ nhưng đi từ tín hiệu thô (PDF làm tròn f xuống 2 chữ số nên cho sai lệch nhỏ)
    c = [0.98, 0.90, 0.70]
    e = [0.06, 0.17, 2.4]            # px
    sigma = [0.004, 0.010, 0.21]     # m
    q_blur = [0.99, 0.90, 0.35]
    q_tex = [0.97, 0.95, 0.80]
    q_exp = [1.00, 0.98, 0.60]
    w = weights_from_signals(c, e, sigma, q_blur, q_tex, q_exp, tau_e=2.0, tau_sigma=0.20)
    assert w == pytest.approx([0.895, 0.659, 0.012], abs=1e-2)
    p_hat, w_tilde = fuse(DEPTH, w)
    assert w_tilde == pytest.approx([0.571, 0.421, 0.008], abs=5e-3)
    assert p_hat == pytest.approx(2.04, abs=1e-2)


def test_ablation_without_quality_ignores_q_signals():
    c, e, sigma = [0.98, 0.70], [0.06, 2.4], [0.004, 0.21]
    with_q = weights_from_signals(c, e, sigma, [0.99, 0.35], [0.97, 0.80], [1.0, 0.60], 2.0, 0.20, use_quality=True)
    no_q = weights_from_signals(c, e, sigma, [0.99, 0.35], [0.97, 0.80], [1.0, 0.60], 2.0, 0.20, use_quality=False)
    expected = np.array(c) * f_err(e, 2.0) * f_err(sigma, 0.20)
    assert no_q == pytest.approx(expected)
    assert not np.allclose(with_q, no_q)


def test_normalize_respects_mask_and_zero_sum():
    w = np.array([[0.5, 0.5, 0.5], [0.0, 0.0, 0.0]])
    mask = np.array([[True, True, False], [True, True, False]])
    wt = normalize_weights(w, mask)
    assert wt[0] == pytest.approx([0.5, 0.5, 0.0])  # view ngoài V_k không có phiếu
    assert wt[1] == pytest.approx([0.5, 0.5, 0.0])  # tổng bằng 0 → chia đều cho view nhìn thấy
    assert np.isfinite(wt).all()


def test_fuse_3d_points():
    pts = np.array([[[0.0, 0.0, 2.0], [0.0, 0.0, 4.0]]])  # (K=1, V=2, 3)
    w = np.array([[3.0, 1.0]])
    p_hat, w_tilde = fuse(pts, w)
    assert p_hat.shape == (1, 3) and p_hat[0] == pytest.approx([0.0, 0.0, 2.5])
    assert w_tilde[0] == pytest.approx([0.75, 0.25])
    with pytest.raises(ValueError):
        fuse(np.zeros((1, 2, 3, 3)), w)
