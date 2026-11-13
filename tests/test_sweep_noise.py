"""Test scripts/sweep_noise.py: quy tắc chọn đặt trước (nhẹ nhất thoả cả ba nhóm điều kiện) và leave-one-scene-out."""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
spec = importlib.util.spec_from_file_location("sweep_noise_under_test", REPO / "scripts" / "sweep_noise.py")
sn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sn)

SC = sn.SCENES


def _tab(deltas):
    """deltas: {config: (dP_targets, dRecall, dF, kept)} áp đều cho mọi scene; Chamfer đứng yên."""
    tab = {s: {"none": {"acc_cm": 5, "comp_cm": 20, "chamfer_cm": 15, "precision": 0.6, "recall": 0.5, "f_score": 0.5, "frac_kept": 1.0}} for s in SC}
    for cid, (dp, dr, df, kept) in deltas.items():
        for s in SC:
            tab[s][cid] = {"acc_cm": 5, "comp_cm": 20, "chamfer_cm": 15, "precision": 0.6 + dp, "recall": 0.5 + dr, "f_score": 0.5 + df, "frac_kept": kept}
    return tab


def test_chon_cau_hinh_nhe_nhat_thoa_ca_ba_nhom():
    tab = _tab({"f1_mv2": (0.02, 0.0, 0.0, 0.95),          # chưa đủ precision (+0,02 < +0,05)
                "f1_mv3": (0.06, -0.01, 0.0, 0.85),         # đạt, nhẹ hơn mv4
                "f1_mv4": (0.10, -0.015, 0.0, 0.70),        # đạt nhưng xoá nhiều hơn
                "f1_mv6": (0.20, -0.05, -0.02, 0.40)})      # recall mất quá 0,02
    assert sn.choose(tab, "f1", SC) == "f1_mv3"
    assert not sn.passes(tab, "f1_mv6", SC)["ok"] and not sn.passes(tab, "f1_mv2", SC)["ok"]
    assert sn.choose(tab, "f2", SC) is None                 # không có dữ liệu f2: không chọn


def test_dieu_kien_doi_chung_va_chamfer():
    tab = _tab({"f1_mv3": (0.06, 0.0, 0.0, 0.85)})
    tab["42445022"]["f1_mv3"]["f_score"] -= 0.02            # scene đối chứng mất 0,02 > 0,010 → loại
    assert sn.choose(tab, "f1", SC) is None
    tab = _tab({"f1_mv3": (0.06, 0.0, 0.0, 0.85)})
    for s in SC:
        tab[s]["f1_mv3"]["chamfer_cm"] = 15.9               # +6% > 5% → loại
    assert sn.choose(tab, "f1", SC) is None


def test_leave_one_out_chon_tren_cac_scene_con_lai():
    tab = _tab({"f1_mv3": (0.06, 0.0, 0.0, 0.85)})
    tab["42897599"]["f1_mv3"]["precision"] = 0.6 + 0.0     # chỉ còn 42898849 (+0,06) là scene mục tiêu khi bỏ 42897599
    rest = [s for s in SC if s != "42897599"]
    assert sn.choose(tab, "f1", rest) == "f1_mv3"
    assert sn.choose(tab, "f1", SC) is None                 # trung bình hai scene mục tiêu chỉ +0,03
