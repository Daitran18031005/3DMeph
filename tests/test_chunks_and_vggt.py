"""Test chia chunk VGGT (ĐC §7.1) và đổi confidence VGGT sang c_model."""

import numpy as np
import pytest

from pipeline.vggt.chunks import chunk_ranges, n_chunks
from pipeline.vggt.outputs import conf_to_c_model


def test_n_chunks_pdf_example():
    # N_kf = 72, c = 12, o = 2 → ⌈(72−2)/10⌉ = 7
    assert n_chunks(72, 12, 2) == 7


def test_chunk_ranges_pdf_example_figure7():
    ranges = chunk_ranges(72, 12, 2)
    assert len(ranges) == 7
    one_based = [(a + 1, b) for a, b in ranges]
    assert one_based[0] == (1, 12) and one_based[1] == (11, 22) and one_based[2] == (21, 32)
    assert one_based[-1] == (61, 72)
    for (a1, b1), (a2, _b2) in zip(ranges, ranges[1:]):
        assert b1 - a2 == 2  # hai chunk liền kề gối nhau o = 2 ảnh
    covered = sorted({i for a, b in ranges for i in range(a, b)})
    assert covered == list(range(72))  # không sót ảnh nào


@pytest.mark.parametrize("n_kf", [5, 12, 40, 63, 80])
def test_chunk_ranges_cover_every_frame_and_match_formula(n_kf):
    ranges = chunk_ranges(n_kf, 12, 2)
    assert len(ranges) == n_chunks(n_kf, 12, 2)
    assert {i for a, b in ranges for i in range(a, b)} == set(range(n_kf))
    assert all(b - a <= 12 for a, b in ranges)


def test_n_chunks_rejects_bad_parameters():
    for args in ((72, 12, 12), (72, 12, 0), (0, 12, 2)):
        with pytest.raises(ValueError):
            n_chunks(*args)


def test_conf_to_c_model_examples():
    # conf = 1 + exp(x) ∈ [1, ∞): conf=1 → 0; 2,2 → 0,55; 50 → 0,98
    assert conf_to_c_model(1.0) == pytest.approx(0.0)
    assert conf_to_c_model(2.2) == pytest.approx(0.55, abs=5e-3)
    assert conf_to_c_model(50.0) == pytest.approx(0.98)
    out = conf_to_c_model(np.array([[1.0, 2.0], [10.0, 100.0]]))
    assert ((out >= 0) & (out < 1)).all()
    assert np.all(np.diff(conf_to_c_model(np.linspace(1, 100, 50))) > 0)  # đơn điệu tăng


def test_conf_to_c_model_rejects_values_below_one():
    with pytest.raises(ValueError):
        conf_to_c_model(np.array([0.5]))
