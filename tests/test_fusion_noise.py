"""Test bộ lọc nhiễu sau fuse (pipeline/fusion/noise.py): điểm ngoại lai bị bỏ, điểm đủ view được giữ."""

import numpy as np
import pytest

from pipeline.fusion.noise import min_views_mask, noise_keep_mask, statistical_outlier_mask


def _cloud():
    rng = np.random.default_rng(0)
    plane = np.c_[rng.uniform(0, 1, 2000), rng.uniform(0, 1, 2000), rng.normal(0, 0.002, 2000)]     # mặt phẳng dày đặc
    flyers = np.array([[0.5, 0.5, 0.8], [0.2, 0.9, -0.7], [5.0, 5.0, 5.0]])                          # điểm bay xa mặt phẳng
    return np.vstack([plane, flyers])


def test_statistical_outlier_bo_diem_bay_giu_mat_phang():
    xyz = _cloud()
    keep = statistical_outlier_mask(xyz, k=20, std_ratio=2.0)
    assert not keep[-3:].any() and keep[:2000].mean() > 0.95
    assert statistical_outlier_mask(xyz[:10], k=20, std_ratio=1.0).all()                     # ≤ k điểm: giữ hết
    with pytest.raises(ValueError):
        statistical_outlier_mask(xyz, k=0, std_ratio=1.0)


def test_min_views_giu_diem_du_view():
    nv = np.array([1, 2, 3, 4, 6])
    assert min_views_mask(nv, 3).tolist() == [False, False, True, True, True]
    with pytest.raises(ValueError):
        min_views_mask(nv, 0)


def test_noise_keep_mask_ket_hop_va_tat_khi_none():
    xyz = _cloud()
    nv = np.full(len(xyz), 4)
    nv[:100] = 1                                                                             # 100 điểm mặt phẳng chỉ 1 view
    assert noise_keep_mask(xyz, nv).all()                                                    # cả hai bộ tắt: giữ hết
    k1 = noise_keep_mask(xyz, nv, min_views=2)
    assert not k1[:100].any() and k1[100:].all()
    k2 = noise_keep_mask(xyz, nv, min_views=2, sor_std_ratio=2.0, sor_k=20)
    assert not k2[:100].any() and not k2[-3:].any() and k2[100:2000].mean() > 0.95
