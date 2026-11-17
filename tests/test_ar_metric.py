"""Test pipeline/alignment/ar_metric.py: scale từ quỹ đạo AR và mốc thước dây định vị bằng AR (app M6)."""

import numpy as np
import pytest

from pipeline.alignment import ar_metric
from pipeline.alignment.anchor import anchor_from_clicks


def _look_at(center, target):
    """R (world→camera, OpenCV: z tới, y xuống) nhìn từ center về target."""
    z = target - center
    z /= np.linalg.norm(z)
    x = np.cross([0.0, -1.0, 0.0], z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return np.stack([x, y, z])


def _cams(scale=1.0, n=12):
    """Camera trên vòng tròn bán kính 2 m quanh gốc, nhìn vào gốc; `scale` chia toạ độ (giả lập đơn vị COLMAP)."""
    k = np.array([[500.0, 0, 320], [0, 500.0, 240], [0, 0, 1]])
    out = {}
    for i in range(n):
        a = 2 * np.pi * i / n
        c = np.array([2 * np.cos(a), 0.3 * np.sin(3 * a), 2 * np.sin(a)])
        r = _look_at(c, np.zeros(3))
        cs = c / scale
        out[i] = {"K": k, "R": r, "t": -r @ cs, "center": cs, "w": 640, "h": 480}
    return out


def test_robust_trajectory_scale_dung_scale_va_bo_camera_lech():
    rng = np.random.default_rng(0)
    src = rng.uniform(-1, 1, (20, 3))
    dst = 0.37 * src + np.array([1.0, 2.0, 3.0])
    dst[3] += 5.0                                                     # một camera AR lệch nặng
    s, n, res = ar_metric.robust_trajectory_scale(src, dst)
    assert abs(s - 0.37) < 1e-6 and n == 19 and res < 1e-6


def test_robust_trajectory_scale_qua_it_camera():
    with pytest.raises(ValueError):
        ar_metric.robust_trajectory_scale(np.zeros((3, 3)), np.zeros((3, 3)))


def test_mot_thuoc_day_qua_chieu_ar_roi_tam_giac_hoa_colmap():
    ar = _cams(1.0)
    colmap = _cams(0.25)                                              # 1 đv COLMAP = 0,25 m
    a, b = [0.4, 0.1, -0.2], [-0.5, 0.05, 0.6]
    obs = ar_metric.project_anchor(ar, set(colmap), a, b)
    assert {o["endpoint"] for o in obs} == {"a", "b"}
    res = anchor_from_clicks(colmap, obs)
    l_real = float(np.linalg.norm(np.subtract(b, a)))
    assert abs(l_real / res["L_model"] - 0.25) < 1e-6                 # s_m = L_real / L_model theo (4)


def test_project_anchor_bo_diem_sau_camera_va_ngoai_anh():
    ar = _cams(1.0, n=4)
    obs = ar_metric.project_anchor(ar, set(ar), [0, 0, 0], [0, 50.0, 0])      # B ở ngay trên đầu: ngoài khung mọi camera
    assert all(o["endpoint"] == "a" for o in obs) and len(obs) == 4
