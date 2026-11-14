"""Test hàm phụ của scripts/length_error_v2.py: mẫu số (hợp lệ/đạt), khớp mặt phẳng và khoảng cách giữa hai mặt phẳng."""

import importlib.util
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
spec = importlib.util.spec_from_file_location("length_error_v2_under_test", REPO / "scripts" / "length_error_v2.py")
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)


def _seg(nn, err, gt=1.0):
    return {"nn": nn, "err": err, "gt": gt}


def test_summarize_dem_hop_le_theo_ban_kinh_va_dat_tren_ca_mau_so():
    rows = [_seg(1.0, 0.5), _seg(2.5, 1.0), _seg(4.0, 6.0), _seg(9.0, None)]            # đoạn cuối không có độ dài (không hợp lệ)
    s5 = v2.summarize(rows, 5.0)
    assert s5["N"] == 4 and s5["valid"] == 3 and s5["pass"] == 2 and abs(s5["frac_pass_all"] - 0.5) < 1e-12        # 6 cm không đạt
    assert s5["median_valid"] == 1.0 and s5["median_all_invalid_inf"] is not None                                    # 3/4 hợp lệ → median xác định
    s2 = v2.summarize(rows, 2.0)
    assert s2["valid"] == 1 and s2["pass"] == 1 and s2["median_all_invalid_inf"] is None                            # 1/4 hợp lệ → "không xác định"
    assert v2.summarize([], 5.0)["N"] == 0


def test_fit_plane_bo_ngoai_lai_va_plane_dist_hai_mat_song_song():
    rng = np.random.default_rng(0)
    a = np.c_[rng.uniform(0, 3, 2000), rng.uniform(0, 3, 2000), rng.normal(0, 0.002, 2000)]               # mặt z = 0
    a[:50, 2] += 1.0                                                                                       # 50 điểm ngoại lai
    na, ca, _ = v2.fit_plane(a)
    assert abs(abs(na[2]) - 1) < 1e-2 and abs(ca[2]) < 0.05
    b = a.copy()
    b[:, 2] += 5.9                                                                                         # mặt song song cách 5,9 m
    nb, cb, _ = v2.fit_plane(b)
    assert abs(v2.plane_dist(na, ca, nb, cb) - 5.9) < 0.05
    assert abs(v2.plane_dist(na, ca, -nb, cb) - 5.9) < 0.05                                                # không phụ thuộc chiều pháp tuyến
