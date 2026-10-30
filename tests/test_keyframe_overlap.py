"""Test overlap RGB (pipeline/keyframe/overlap.py): vector ĐC (1) và chọn keyframe theo overlap bằng hàm overlap giả."""

import cv2
import numpy as np
import pytest

from pipeline.common.geometry import overlap_percent
from pipeline.keyframe import overlap as ov

W, H = 640, 480


def scene_image(seed=0, n_shapes=400):
    """Cảnh tổng hợp nhiều hình tương phản mạnh để ORB có đủ điểm."""
    rng = np.random.default_rng(seed)
    img = np.full((H, W * 2), 128, np.uint8)
    for _ in range(n_shapes):
        c = int(rng.integers(0, 256))
        x, y = int(rng.integers(0, W * 2)), int(rng.integers(0, H))
        if rng.random() < 0.5:
            cv2.circle(img, (x, y), int(rng.integers(3, 18)), c, -1)
        else:
            cv2.rectangle(img, (x, y), (x + int(rng.integers(5, 30)), y + int(rng.integers(5, 30))), c, -1)
    return cv2.GaussianBlur(img, (3, 3), 0)


def crop(big, dx, angle=0.0):
    img = big[:, dx:dx + W]
    if angle:
        m = cv2.getRotationMatrix2D((W / 2, H / 2), angle, 1.0)
        img = cv2.warpAffine(big[:, dx:dx + W + 200], m, (W, H))
    return img


def test_overlap_khop_cong_thuc_pdf_khi_dich_ngang():
    big = scene_image()
    a = ov.Features(crop(big, 0))
    for dx in (64, 128, 192, 320):
        r = ov.overlap_fraction(a, ov.Features(crop(big, dx)))
        expect = overlap_percent(W, dx) / 100.0                                   # (W − Δ)/W, ĐC §6.1 (1)
        assert r["n_inliers"] >= 15 and r["overlap"] == pytest.approx(expect, abs=0.05), (dx, r, expect)
    assert overlap_percent(2.0, 0.6) == pytest.approx(70.0)                       # vector của đề cương
    r0 = ov.overlap_fraction(a, ov.Features(crop(big, 0)))
    assert r0["overlap"] > 0.97                                                    # cùng một khung


def test_overlap_bang_0_khi_khong_lien_quan_hoac_khong_co_dac_trung():
    a = ov.Features(scene_image(0)[:, :W])
    b = ov.Features(scene_image(99)[:, :W])
    assert ov.overlap_fraction(a, b)["overlap"] == 0.0
    flat = ov.Features(np.full((H, W), 100, np.uint8))                            # tường trơn: không có điểm
    assert flat.des is None and ov.overlap_fraction(a, flat)["overlap"] == 0.0 and ov.overlap_fraction(flat, a)["overlap"] == 0.0


def test_overlap_giam_khi_xoay_them():
    big = scene_image(3)
    a = ov.Features(crop(big, 0))
    o = [ov.overlap_fraction(a, ov.Features(crop(big, 0, ang)))["overlap"] for ang in (0.0, 8.0)]
    assert o[0] > 0.9 and 0.5 < o[1] < o[0] + 0.05


def line_overlap(xs, width=1.0):
    return lambda i, j: max(0.0, 1.0 - abs(xs[j] - xs[i]) / width)


def test_select_by_overlap_bo_trung_va_noi_lien_tuc():
    xs = [0.0, 0.05, 0.1, 0.15, 0.3, 0.35, 0.5, 0.55, 0.9, 1.2]
    kept, breaks = ov.select_by_overlap(len(xs), line_overlap(xs), o_max=0.8, o_min=0.6)
    # từ 0: ứng viên 1 (overlap 0,95), 2 (0,9), 3 (0,85) trùng; ứng viên 4 (0,7) là khung đầu tiên không trùng
    assert kept[:2] == [0, 4] and breaks == 0
    assert all(line_overlap(xs)(a, b) >= 0.6 - 1e-9 for a, b in zip(kept, kept[1:]))      # liên tiếp luôn còn nối
    kept2, _ = ov.select_by_overlap(len(xs), line_overlap(xs), o_max=0.9, o_min=0.6)
    assert len(kept2) > len(kept)                                                  # ngưỡng trùng cao hơn thì giữ nhiều khung hơn


def test_select_by_overlap_lui_mot_khung_khi_mat_ket_noi_va_dem_dut():
    xs = [0.0, 0.1, 0.45, 0.5]                                                      # khung 2 cách 0 tới 0,55 (overlap 0,45 < 0,6)
    kept, breaks = ov.select_by_overlap(len(xs), line_overlap(xs), o_max=0.85, o_min=0.6)
    assert kept[:2] == [0, 1] and breaks == 0                                      # lùi về khung 1 (đang trùng) để còn nối
    xs2 = [0.0, 0.7]                                                                # nhảy thẳng, không có khung nào để lùi
    kept2, breaks2 = ov.select_by_overlap(len(xs2), line_overlap(xs2), o_max=0.85, o_min=0.6)
    assert kept2 == [0, 1] and breaks2 == 1
    with pytest.raises(ValueError):
        ov.select_by_overlap(3, lambda i, j: 1.0, o_max=0.5, o_min=0.6)
    assert ov.select_by_overlap(0, lambda i, j: 1.0, 0.8, 0.6) == ([], 0)


def test_make_overlap_fn_dung_dem_va_ghi_thong_ke():
    big = scene_image(5)
    feats = ov.features_cache([crop(big, 0), crop(big, 100)])
    st = []
    fn = ov.make_overlap_fn(feats, st)
    v1, v2 = fn(0, 1), fn(0, 1)
    assert v1 == v2 and len(st) == 1 and st[0]["n_inliers"] >= 15
