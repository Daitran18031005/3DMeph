"""Test scripts/gate_variants.py: quy tắc nhận đặt trước (check) và ghi đè cấu hình."""

import importlib.util
import sys
from pathlib import Path

import pytest

from pipeline.common import config as cfgmod

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
spec = importlib.util.spec_from_file_location("gate_variants_under_test", REPO / "scripts" / "gate_variants.py")
gv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gv)

SC = gv.SCENES


def _row(**kw):
    r = {"n_floor": 3.0, "n_wall": 0.0, "n_ceiling": 0.0, "n_horizontal_other": 0.0, "n_other": 0.0, "n_floor_far": 2.0, "pass_frac": 0.02, "theta_cond_frac": 0.2, "n_passed": 100.0,
         "acc_passed": 0.9, "acc_all": 0.7, "med_before_cm": 2.0, "med_after_cm": 1.5, "frac_improved": 0.7, "chamfer_cm": 16.0, "f_score": 0.5}
    r.update(kw)
    return r


def _tab(**variant_kw):
    return {"gate_base": {s: _row() for s in SC}, "v": {s: _row(**variant_kw) for s in SC}}


def test_check_nhan_dat_khi_du_tuong_san_va_khong_hai():
    r = gv.check(_tab(n_floor=1.0, n_wall=1.0, n_floor_far=0.0), "v")
    assert r["A1_tuong_va_san"] and r["A2"] and r["A3"] and r["A4"] and r["label_fix_ok"]
    assert not gv.check(_tab(n_floor=1.0, n_wall=0.0, n_floor_far=0.0), "v")["label_fix_ok"]            # thiếu tường
    assert not gv.check(_tab(n_wall=1.0, n_floor_far=1.0), "v")["label_fix_ok"]                          # còn sàn ở độ cao khác


def test_check_chan_khi_hai_ket_qua_hoac_do_chinh_xac():
    assert not gv.check(_tab(n_wall=1.0, n_floor_far=0.0, acc_passed=0.85), "v")["A2"]                  # tụt 0,05 > 0,02
    assert not gv.check(_tab(n_wall=1.0, n_floor_far=0.0, f_score=0.49), "v")["A4"]                      # ΔF −0,01 < −0,005
    assert not gv.check(_tab(n_wall=1.0, n_floor_far=0.0, chamfer_cm=16.4), "v")["A4"]                   # Chamfer +2,5% > +2%
    t = _tab(n_wall=1.0, n_floor_far=0.0)
    t["v"]["42445022"]["f_score"] = 0.48                                                                # một scene mất 0,02 (> 0,010) dù trung bình còn ổn
    assert not gv.check(t, "v")["A4"]
    assert not gv.check(_tab(n_wall=1.0, n_floor_far=0.0, med_after_cm=2.5), "v")["A3"]                  # sai số điểm bị kéo tăng ở mọi scene


def test_check_phap_tuyen_can_theta_gap_1_5():
    assert not gv.check(_tab(theta_cond_frac=0.28), "v")["knn_ok"]                                       # ×1,4
    assert gv.check(_tab(theta_cond_frac=0.31), "v")["knn_ok"]                                           # ×1,55


def test_apply_overrides_khong_doi_cfg_goc_va_bao_khoa_la():
    cfg = cfgmod.load_config()
    c = gv.apply_overrides(cfg, {"plane.floor_rule": "any", "plane.gate_normal_knn": 100})
    assert c["plane"]["floor_rule"] == "any" and cfg["plane"]["floor_rule"] == "lowest" and c["plane"]["gate_normal_knn"] == 100          # cfg gốc không đổi
    with pytest.raises(KeyError):
        gv.apply_overrides(cfg, {"plane.khong_co": 1})
