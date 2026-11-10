"""Test scripts/sweep_thresholds.py: danh sách cấu hình, quy tắc chọn cố định, chặn held-out."""

import importlib.util
import sys
from pathlib import Path

import pytest

from pipeline.common import config as cfgmod

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
spec = importlib.util.spec_from_file_location("sweep_thresholds_under_test", REPO / "scripts" / "sweep_thresholds.py")
st = importlib.util.module_from_spec(spec)
spec.loader.exec_module(st)

SCENES = [f"arkitscenes/s{i}" for i in range(6)]


def _rows(param, value, f_by_scene, chamfer=20.0, default_f=0.50, default_chamfer=20.0):
    out = [{"scene": s, "param": "default", "value": "", "f_score": default_f, "chamfer_cm": default_chamfer, "error": ""} for s in SCENES]
    out += [{"scene": s, "param": param, "value": value, "f_score": f, "chamfer_cm": chamfer, "error": ""} for s, f in zip(SCENES, f_by_scene)]
    return out


def _chosen(rows, param):
    return {d["param"]: d["chosen"] for d in st.decide(rows)}[param]


def test_config_list_co_13_cau_hinh_mac_dinh_dau_tien_fusion_sau_cung():
    lst = st.config_list(cfgmod.load_config())
    assert len(lst) == 13 and lst[0] == ("default", None)
    assert {p for p, _ in lst[1:]} == set(st.GRID)
    assert all(p in st.FUSION_KEYS for p, _ in lst[-4:]) and not any(p in st.FUSION_KEYS for p, _ in lst[:9])      # fuse một lần cho các cấu hình chỉ đổi gate


def test_quy_tac_chon_chi_chon_khi_du_ba_dieu_kien():
    ok = _rows("plane.tau_w", "0.2", [0.52] * 6)
    assert _chosen(ok, "plane.tau_w") == "0.2"                                                                    # +0,02 ở 6/6 scene, Chamfer giữ nguyên
    assert _chosen(_rows("plane.tau_w", "0.2", [0.505] * 6), "plane.tau_w") is None                               # (i) tăng chưa tới 0,010
    assert _chosen(_rows("plane.tau_w", "0.2", [0.60, 0.60, 0.60, 0.49, 0.49, 0.49]), "plane.tau_w") is None      # (ii) trung bình +0,04 nhưng chỉ 3/6 scene tăng
    assert _chosen(_rows("plane.tau_w", "0.2", [0.52] * 6, chamfer=21.5), "plane.tau_w") is None                  # (iii) Chamfer tệ hơn 7,5% > 5%
    assert _chosen(_rows("plane.tau_w", "0.2", [0.52] * 6, chamfer=20.9), "plane.tau_w") == "0.2"                 # Chamfer tệ hơn 4,5% vẫn trong ngưỡng


def test_quy_tac_chon_gia_tri_f_cao_nhat_va_bo_qua_dong_loi():
    rows = _rows("plane.alpha", "0.25", [0.52] * 6) + [{**r, "value": "1"} for r in _rows("plane.alpha", "1", [0.54] * 6) if r["param"] == "plane.alpha"]
    assert _chosen(rows, "plane.alpha") == "1"
    bad = [{**r, "error": "ValueError: x"} for r in rows if r["param"] == "plane.alpha" and r["value"] == "1"]
    assert _chosen([r for r in rows if not (r["param"] == "plane.alpha" and r["value"] == "1")] + bad, "plane.alpha") == "0.25"   # dòng lỗi không được tính


def test_chan_held_out_khong_co_scene_nao_khop(capsys):
    if not (REPO / "data" / "splits.csv").is_file():
        pytest.skip("không có data/splits.csv (worktree)")
    assert st.main(["--split", "val", "--scenes", "43828368"]) == 1                                              # 43828368 là held-out
    assert "held-out bị chặn" in capsys.readouterr().out
