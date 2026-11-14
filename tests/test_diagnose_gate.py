"""Test hàm phụ của scripts/diagnose_gate.py: pháp tuyến cục bộ và phần trăm."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
spec = importlib.util.spec_from_file_location("diagnose_gate_under_test", REPO / "scripts" / "diagnose_gate.py")
dg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dg)


def test_local_normals_mat_phang_nam_ngang_cho_phap_tuyen_doc_truc_z():
    rng = np.random.default_rng(0)
    xyz = np.c_[rng.uniform(0, 1, 3000), rng.uniform(0, 1, 3000), rng.normal(0, 0.001, 3000)]
    n = dg.local_normals(cKDTree(xyz), xyz[:200], xyz, 30)
    assert np.abs(n[:, 2]).min() > 0.99                     # góc lệch so với trục z dưới ~8°


def test_pct_va_frac_le():
    assert dg.pct([0, 1, 2, 3, 4], (50,)) == {"50": 2.0}
    assert dg.frac_le([0.01, 0.04, 0.06, 0.2]) == 0.5       # 2/4 điểm cách ≤ 5 cm
