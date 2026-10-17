"""Test tín hiệu chất lượng ảnh (ĐC §7.3, §16.1). V_ref=581 chỉ dùng để kiểm hàm theo ví dụ của PDF,
KHÔNG phải giá trị cấu hình (xem configs/README.md)."""

import numpy as np
import pytest

from pipeline.common.quality import (
    exposure_counts,
    laplacian_variance,
    q_blur,
    q_exposure,
    q_exposure_from_counts,
    q_texture,
    window_gradient_mean,
)

V_REF_PDF_EXAMPLE = 581.0


def test_q_blur_pdf_examples():
    assert q_blur(575, V_REF_PDF_EXAMPLE) == pytest.approx(0.99, abs=5e-3)   # nét
    assert q_blur(203, V_REF_PDF_EXAMPLE) == pytest.approx(0.35, abs=5e-3)   # mờ rõ
    assert q_blur(3, V_REF_PDF_EXAMPLE) == pytest.approx(0.005, abs=1e-3)    # hỏng
    assert q_blur(5000, V_REF_PDF_EXAMPLE) == 1.0                            # kẹp ở 1


def test_q_blur_requires_measured_v_ref():
    for bad in (None, 0, -1):
        with pytest.raises(ValueError):
            q_blur(100, bad)


def test_q_exposure_pdf_examples():
    total = 1920 * 1440
    assert total == 2_764_800
    assert q_exposure_from_counts(41_472, 13_824, total) == pytest.approx(0.98, abs=5e-3)  # ảnh tốt
    assert q_exposure_from_counts(0, 1_105_920, total) == pytest.approx(0.60, abs=5e-3)    # ảnh C ngược sáng
    with pytest.raises(ValueError):
        q_exposure_from_counts(0, 0, 0)


def test_q_exposure_on_image():
    img = np.full((10, 10), 128, dtype=np.uint8)
    img[:2] = 0       # 20 pixel tối (≤ 5)
    img[-1] = 255     # 10 pixel cháy (≥ 250)
    assert exposure_counts(img) == (20, 10, 100)
    assert q_exposure(img) == pytest.approx(0.70)


def test_q_texture_pdf_examples():
    assert q_texture(38, 30) == pytest.approx(1.00)   # mép bàn gỗ
    assert q_texture(9, 30) == pytest.approx(0.30)    # tường trắng
    with pytest.raises(ValueError):
        q_texture(10, None)


def test_laplacian_variance_separates_sharp_from_flat():
    rng = np.random.default_rng(0)
    sharp = (rng.uniform(size=(64, 64)) * 255).astype(np.uint8)
    flat = np.full((64, 64), 100, dtype=np.uint8)
    assert laplacian_variance(flat) == pytest.approx(0.0)
    assert laplacian_variance(sharp) > 100.0


def test_window_gradient_mean_flat_vs_textured():
    flat = np.full((60, 60), 90, dtype=np.uint8)
    # Bàn cờ 1 pixel không dùng được: nhân Sobel 3×3 lấy hai pixel cách nhau 2 nên triệt tiêu. Dùng nhiễu.
    noise = (np.random.default_rng(0).uniform(size=(60, 60)) * 255).astype(np.uint8)
    pts = np.array([[30.0, 30.0], [5.0, 5.0], [59.5, 59.5]])
    assert window_gradient_mean(flat, pts) == pytest.approx([0.0, 0.0, 0.0])
    assert (window_gradient_mean(noise, pts) > 100).all()  # kể cả điểm sát biên
    # Gradient phải lớn hơn ở vùng có kết cấu so với vùng phẳng (cơ sở của q_texture)
    half = flat.copy()
    half[:, 30:] = noise[:, 30:]
    left, right = window_gradient_mean(half, np.array([[10.0, 30.0], [50.0, 30.0]]))
    assert left == pytest.approx(0.0) and right > 100
