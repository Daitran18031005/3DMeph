"""Test scripts/sweep_keyframe.py: tóm tắt, quy tắc chọn cấu hình, CSV, run_one với stage giả (không cần dữ liệu hay GPU)."""

import sys
from pathlib import Path

import pytest

from pipeline.common import config as cfgmod
from pipeline.common import io as pio
from pipeline.common.errors import E_SFM_FAILED, StageError

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture(scope="module")
def sw():
    sys.path.insert(0, str(SCRIPTS))
    try:
        import sweep_keyframe as mod
    finally:
        sys.path.remove(str(SCRIPTS))
    return mod


def row(cid, scene, n_kf, ratio, q=0.35, om=0.8, err="", rep=0):
    return {"scene": scene, "cfg_id": cid, "q_drop": q, "overlap_max": om, "overlap_min": 0.6, "exposure_q_drop": 0.5, "rep": rep, "n_kf": n_kf, "ratio": ratio, "error": err}


def test_summarize_va_choose_config_theo_quy_tac(sw):
    rows = []
    # A: mọi scene trong [40, 80], tỉ lệ trung vị 0,92; B: tỉ lệ cao hơn (0,95) nhưng một scene có 85 keyframe ⇒ loại; C: có lỗi ⇒ loại; D: ngang A nhưng nhiều keyframe hơn
    for s, n, r in (("s1", 50, 0.90), ("s2", 60, 0.92), ("s3", 55, 0.95)):
        rows.append(row("A", s, n, r, q=0.35, om=0.8))
        rows.append(row("D", s, n + 10, r, q=0.2, om=0.9))
    for s, n, r in (("s1", 50, 0.95), ("s2", 85, 0.96), ("s3", 55, 0.95)):
        rows.append(row("B", s, n, r, q=0.5))
    for s in ("s1", "s2", "s3"):
        rows.append(row("C", s, 60, 0.99, q=0.5, err="E_SFM_FAILED" if s == "s2" else ""))
    summ = sw.summarize(rows)
    by = {s["cfg_id"]: s for s in summ}
    assert by["A"]["all_in_range"] and not by["B"]["all_in_range"] and not by["C"]["all_in_range"] and by["A"]["ratio_median"] == pytest.approx(0.92)
    assert by["A"]["n_kf_min"] == 50 and by["A"]["n_kf_max"] == 60 and by["A"]["ratio_min"] == pytest.approx(0.90)
    best = sw.choose_config(summ)
    assert best["cfg_id"] == "A"                                                  # D hoà tỉ lệ nhưng nhiều keyframe hơn
    assert sw.choose_config(summ, n_scenes=4) is None                              # chưa chạy đủ số scene yêu cầu
    assert sw.choose_config([s for s in summ if s["cfg_id"] in ("B", "C")]) is None


def test_lap_lai_lay_trung_binh_trong_scene(sw):
    rows = [row("A", "s1", 50, 0.90, rep=0), row("A", "s1", 52, 0.94, rep=1), row("A", "s2", 60, 0.92)]
    a = sw.summarize(rows)[0]
    assert a["n_scenes"] == 2 and a["per_scene"][0]["ratio"] == pytest.approx(0.92) and a["per_scene"][0]["n_kf"] == pytest.approx(51)


def test_csv_ghi_doc_va_make_cfg(sw, tmp_path):
    p = tmp_path / "o" / "sweep.csv"
    assert sw.read_rows(p) == []
    sw.append_row(p, row("A", "s1", 50, 0.9))
    sw.append_row(p, row("A", "s2", 60, 0.92))
    rs = sw.read_rows(p)
    assert len(rs) == 2 and rs[1]["scene"] == "s2" and list(rs[0].keys()) == sw.COLUMNS
    cfg = sw.make_cfg(cfgmod.load_config(), tmp_path, 0.2, 0.7, 0.6, 0.5)
    assert cfg["keyframe"]["blur"]["q_drop"] == 0.2 and cfg["keyframe"]["overlap"] == {"max": 0.7, "min": 0.6}
    assert cfg["paths"]["data_root"].endswith("q0.2_omax0.7_omin0.6_e0.5") and cfgmod.load_config()["keyframe"]["blur"]["q_drop"] != 0.2


def test_run_one_ghi_loi_stage_va_don_thu_muc(sw, tmp_path, monkeypatch):
    layout = pio.scene_layout(tmp_path / "x", "arkitscenes", "777")
    monkeypatch.setattr(sw.pr, "resolve_scene", lambda root, scene, cfg: {"layout": layout, "raw_dir": tmp_path, "sky_direction": "Up"})

    def fake_extract(raw_dir, lay, cfg, sky, log=print, **k):
        pio.ensure_dir(lay.keyframes)
        return {"n_frames": 100, "n_candidates": 50, "n_after_blur": 45, "n_after_exposure": 44, "n_after_overlap": 30, "n_overlap_breaks": 1,
                "n_dense": 30}

    def fake_sfm(lay, cfg, exe, log=print):
        raise StageError(E_SFM_FAILED, "giả lập")

    monkeypatch.setattr(sw, "extract_keyframes", fake_extract)
    monkeypatch.setattr(sw, "run_sfm", fake_sfm)
    monkeypatch.setattr(sw.cfgmod, "resolve_colmap_exe", lambda cfg=None: "colmap")
    r = sw.run_one(tmp_path, cfgmod.load_config(), tmp_path / "out", "arkitscenes/777", 0.35, 0.8, 0.6, 0.5, 0)
    assert r["error"] == E_SFM_FAILED and r["n_kf"] == 30 and r["n_overlap_breaks"] == 1
    assert not layout.root.exists()                                                # đã dọn
    monkeypatch.setattr(sw, "run_sfm", lambda lay, cfg, exe, log=print: {"n_keyframes": 25, "n_registered": 27, "registered_ratio": 0.9, "n_models": 1, "n_points3D": 999,
                                                                      "mean_reproj_error_px": 0.6, "seconds": 40.0, "peak_vram_mib": 380.0})
    r2 = sw.run_one(tmp_path, cfgmod.load_config(), tmp_path / "out", "arkitscenes/777", 0.35, 0.8, 0.6, 0.5, 1, keep=True)
    assert not r2.get("error") and r2["ratio"] == 0.9 and r2["sfm_peak_vram_mib"] == 380.0 and layout.root.exists()
    assert r2["n_kf"] == 25                                                         # sau SfM: số keyframe đã chọn, không phải tập dày


def test_cau_hinh_phai_thua_deu_khong_hop_le(sw):
    """Thưa đều (thinned = 1) ở bất kỳ scene nào thì loại, dù N_kf nằm trong [40, 80] và tỉ lệ đăng ký cao."""
    rows = []
    for s, th in (("s1", 0), ("s2", 1), ("s3", 0)):
        r = row("T", s, 80 if th else 60, 0.99)
        r["thinned"] = th
        rows.append(r)
        r2 = row("U", s, 60, 0.9)
        r2["thinned"] = 0
        rows.append(r2)
    by = {s["cfg_id"]: s for s in sw.summarize(rows)}
    assert not by["T"]["all_in_range"] and by["U"]["all_in_range"] and sw.choose_config(list(by.values()))["cfg_id"] == "U"
