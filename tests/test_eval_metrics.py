"""Test chỉ số đánh giá với số của phòng R02 và ví dụ Replica (ĐC §11.1, §20.1, §20.2)."""

import numpy as np
import pytest

from pipeline.common.geometry import apply_sim3, rodrigues
from pipeline.eval.metrics import (
    accuracy_completeness,
    ate_after_sim3,
    ate_rmse,
    chamfer,
    delta_percent,
    f_score,
    length_errors,
    mae_cm,
    mape_percent,
    median_cm,
    p2plane,
    percent_under_cm,
    plane_recall,
    precision_recall,
    replica_space_of,
    space_average,
)

TRUE = [3.30, 2.85, 2.40, 0.90, 1.20, 1.40]   # §20.2 (mốc 1,50 m KHÔNG nằm trong bảng)
PRED = [3.24, 2.88, 2.43, 0.93, 1.27, 1.38]


def test_length_metrics_r02():
    assert length_errors(PRED, TRUE) * 100 == pytest.approx([6, 3, 3, 3, 7, 2])
    assert mae_cm(PRED, TRUE) == pytest.approx(4.0)
    assert median_cm(PRED, TRUE) == pytest.approx(3.0)
    assert mape_percent(PRED, TRUE) == pytest.approx(2.5, abs=0.06)  # PDF cộng các % đã làm tròn: 2,45 ≈ 2,5
    assert percent_under_cm(PRED, TRUE) == pytest.approx(66.67, abs=0.01)  # 4/6 ≈ 67%


def test_replica_space_average_vs_flat_mean():
    # §11.1: Chamfer 2,0 cm ở 6 scene frl_apartment, 4,0 cm ở 12 scene còn lại
    scenes = [f"frl_apartment_{i}" for i in range(6)] + \
             ["office_0", "office_1", "office_2", "office_3", "office_4",
              "apartment_0", "apartment_1", "apartment_2", "room_0", "room_1", "room_2", "hotel_0"]
    values = {s: (2.0 if s.startswith("frl_apartment") else 4.0) for s in scenes}
    assert len(scenes) == 18
    spaces = {replica_space_of(s) for s in scenes}
    assert len(spaces) == 13  # 18 scene = 13 không gian độc lập
    flat = np.mean(list(values.values()))
    by_space = space_average(values, {s: replica_space_of(s) for s in scenes})
    assert flat == pytest.approx(3.33, abs=5e-3)
    assert by_space == pytest.approx(3.85, abs=5e-3)


def test_chamfer_and_fscore_pdf_example():
    assert chamfer(2.0, 3.0) == pytest.approx(2.5)
    assert f_score(0.90, 0.80) == pytest.approx(0.847, abs=1e-3)
    assert f_score(0.0, 0.0) == 0.0
    d_pg = np.array([0.01] * 9 + [0.20])         # 90% điểm mô hình trong 5 cm
    d_gp = np.array([0.01] * 8 + [0.20, 0.20])   # 80% điểm chuẩn có điểm mô hình gần
    prec, rec = precision_recall(d_pg, d_gp, delta=0.05)
    assert (prec, rec) == (pytest.approx(0.9), pytest.approx(0.8))


def test_accuracy_completeness_identical_clouds_and_offset():
    rng = np.random.default_rng(0)
    g = rng.uniform(size=(500, 3))
    acc, comp, *_ = accuracy_completeness(g, g)
    assert acc == pytest.approx(0.0) and comp == pytest.approx(0.0)
    acc2, comp2, *_ = accuracy_completeness(g + [0.0, 0.0, 1.0], g[:1] + [0.0, 0.0, 1.0])
    assert acc2 > 0 and comp2 == pytest.approx(0.0)  # mô hình dư điểm: Acc xấu đi nhưng Comp vẫn 0


def test_plane_metrics_pdf_example():
    # P1, P2, P6 trước/sau (§20.2): (1,2+2,0+0,8)/3 = 1,33 cm → (0,6+1,0+0,4)/3 = 0,67 cm
    n, d = np.array([1.0, 0.0, 0.0]), 0.0
    before = np.array([[0.012, 0, 0], [0.020, 0, 0], [0.008, 0, 0]])
    after = np.array([[0.006, 0, 0], [0.010, 0, 0], [0.004, 0, 0]])
    assert p2plane(before, n, d) * 100 == pytest.approx(1.33, abs=5e-3)
    assert p2plane(after, n, d) * 100 == pytest.approx(0.67, abs=5e-3)
    assert plane_recall(18, 20) == pytest.approx(0.9)
    with pytest.raises(ValueError):
        plane_recall(1, 0)


def test_ate_pdf_example():
    est = np.array([[0.02, 0, 0], [0.03, 0, 0], [0.01, 0, 0], [0.04, 0, 0]])  # sai 2, 3, 1, 4 cm
    gt = np.zeros((4, 3))
    assert ate_rmse(est, gt) * 100 == pytest.approx(2.74, abs=5e-3)


def test_ate_after_sim3_removes_global_transform():
    rng = np.random.default_rng(2)
    gt = rng.normal(size=(30, 3))
    est = apply_sim3(0.4, rodrigues([0.2, 0.1, -0.7]), np.array([1.0, 2.0, 3.0]), gt)
    assert ate_after_sim3(est, gt) == pytest.approx(0.0, abs=1e-9)
    assert ate_rmse(est, gt) > 0.1  # chưa căn thì sai lớn


def test_delta_percent_pdf_examples():
    assert delta_percent(6.1, 4.4) == pytest.approx(28.0, abs=0.2)  # §20.1
    assert delta_percent(2.0, 1.6) == pytest.approx(20.0)           # point-to-plane 2,0 → 1,6 cm
