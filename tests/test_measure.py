"""Test công cụ đo hai điểm (ĐC §19.1, công thức (30))."""

import pytest

from pipeline.export.measure import distance, main


def test_distance_pdf_example():
    assert distance((0.52, 0.75, 1.20), (1.90, 0.75, 1.20)) == pytest.approx(1.38, abs=1e-9)
    # 1,38² = 1,9044 (đúng như PDF)
    assert distance((0, 0, 0), (1.38, 0, 0)) ** 2 == pytest.approx(1.9044)


def test_cli_prints_distance(capsys):
    rc = main(["--a", "0.52", "0.75", "1.20", "--b", "1.90", "0.75", "1.20"])
    assert rc == 0
    assert "1.380 m" in capsys.readouterr().out
