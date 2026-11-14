"""Test hàm phụ của scripts/length_error.py: tỉ lệ scale bền và nhãn nguyên nhân."""

import importlib.util
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
spec = importlib.util.spec_from_file_location("length_error_under_test", REPO / "scripts" / "length_error.py")
le = importlib.util.module_from_spec(spec)
spec.loader.exec_module(le)


def test_robust_scale_ratio_bo_camera_lech_va_tra_s_m_chia_s():
    rng = np.random.default_rng(0)
    pts = rng.uniform(0, 4, (30, 3))
    cams = {i: {"center": pts[i]} for i in range(30)}                       # đơn vị COLMAP
    gt = {i: 0.5 * pts[i] for i in range(30)}                               # quỹ đạo thật: 0,5 m mỗi đơn vị → s = 0,5
    gt[3] = gt[3] + np.array([5.0, 5.0, 5.0])                               # một camera ARKit nhảy xa (như dev đầu video)
    assert abs(le.robust_scale_ratio(cams, gt, 0.51) - 1.02) < 1e-6         # s_m / s = 0,51 / 0,5
    assert le.robust_scale_ratio({0: {"center": np.zeros(3)}}, {0: np.zeros(3)}, 0.5) is None


def test_cause_text_theo_thu_tu_it_view_depth_hoa_tiet():
    base = {"best_view": 3, "n_views_geometric": 10, "photometric_valid_frac": 0.9, "geometric_valid_frac": 0.9, "gradient_mean": 40.0}
    assert "không có ảnh" in le.cause_text({"best_view": None, "n_views_geometric": 0})
    assert "ít view" in le.cause_text({**base, "n_views_geometric": 2})
    assert "PatchMatch" in le.cause_text({**base, "photometric_valid_frac": 0.1})
    assert "lọc nhất quán" in le.cause_text({**base, "geometric_valid_frac": 0.1})
    assert "trơn" in le.cause_text({**base, "gradient_mean": 5.0})
    assert "mép" in le.cause_text(base)
