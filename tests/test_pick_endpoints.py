"""Test pipeline/export/measure.py (đầu mút, thước dây, so sánh) và scripts/pick_endpoints.py. Không mở cửa sổ Open3D: `pick`, `ask` là bản giả."""

import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from pipeline.common import splits as sp
from pipeline.common.ply import write_ply
from pipeline.export import measure as ms

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
spec = importlib.util.spec_from_file_location("pick_endpoints_under_test", REPO / "scripts" / "pick_endpoints.py")
pe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pe)

RANGE = (1.0, 2.0)


def new_doc(sha="h"):
    return ms.new_endpoints("arkitscenes/111", "proposed", "proposed/export/model_points.ply", sha)


# ---------------------------------------------------------------------------
# Đầu mút
# ---------------------------------------------------------------------------


def test_add_segment_do_dai_theo_cong_thuc_30_va_ghi_doc_lai(tmp_path):
    doc = new_doc()
    seg = ms.add_segment(doc, "S01", (0.52, 0.75, 1.20), (1.90, 0.75, 1.20))
    assert seg["length_m"] == pytest.approx(1.38) and seg["source"] == "manual" and seg["variant"] == "proposed"
    p = ms.endpoints_path(tmp_path, "proposed")
    ms.save_endpoints(p, doc)
    assert p == tmp_path / "evaluation" / "logs" / "endpoints_proposed.json"
    got = ms.load_endpoints(p)
    assert got["segments"][0]["a"] == [0.52, 0.75, 1.2] and got["version"] == 1


def test_add_segment_tu_choi_id_trung_hai_dau_mut_trung_va_toa_do_hong():
    doc = new_doc()
    ms.add_segment(doc, "S01", (0, 0, 0), (1, 0, 0))
    with pytest.raises(ms.MeasureError, match="đã có"):
        ms.add_segment(doc, "S01", (0, 0, 0), (2, 0, 0))
    assert ms.add_segment(doc, "S01", (0, 0, 0), (2, 0, 0), replace=True)["length_m"] == 2.0 and len(doc["segments"]) == 1
    with pytest.raises(ms.MeasureError, match="trùng"):
        ms.add_segment(doc, "S02", (1, 1, 1), (1, 1, 1))
    with pytest.raises(ms.MeasureError):
        ms.add_segment(doc, "S03", (0, 0), (1, 0, 0))
    with pytest.raises(ms.MeasureError):
        ms.add_segment(doc, "S03", (0, 0, float("nan")), (1, 0, 0))


def test_hash_file_diem_lech_bi_tu_choi():
    ms.check_points_hash(new_doc("abc"), "abc")
    with pytest.raises(ms.MeasureError, match="đã đổi"):
        ms.check_points_hash(new_doc("abc"), "xyz")


# ---------------------------------------------------------------------------
# Thước dây
# ---------------------------------------------------------------------------


def test_tape_median_ba_lan_do():
    assert ms.tape_median([1.234, 1.250, 1.236], 3) == pytest.approx(1.236)
    with pytest.raises(ms.MeasureError, match="đúng 3"):
        ms.tape_median([1.2, 1.3], 3)
    with pytest.raises(ms.MeasureError):
        ms.tape_median([1.2, 1.3, -1.0], 3)


def test_tape_moc_scale_1_den_2_m_va_chi_mot_moc():
    doc = ms.new_tape("arkitscenes/111")
    seg = ms.add_tape(doc, "S01", [1.5, 1.51, 1.49], 3, RANGE, anchor=True)
    assert seg["used_as_anchor"] == 1 and seg["median_m"] == 1.5
    with pytest.raises(ms.MeasureError, match="ngoài"):
        ms.add_tape(doc, "S02", [2.4, 2.4, 2.4], 3, RANGE, anchor=True)
    with pytest.raises(ms.MeasureError, match="một mốc"):
        ms.add_tape(doc, "S03", [1.2, 1.2, 1.2], 3, RANGE, anchor=True)
    ms.add_tape(doc, "S01", [1.6, 1.6, 1.6], 3, RANGE, anchor=True)   # ghi đè chính mốc đó được
    assert len(doc["segments"]) == 1 and doc["segments"][0]["median_m"] == 1.6


def test_tape_to_rows_va_write_csv_khong_ghi_de(tmp_path):
    doc = ms.new_tape("x")
    ms.add_tape(doc, "S01", [1.5, 1.5, 1.5], 3, RANGE, anchor=True, notes="cao cửa")
    ms.add_tape(doc, "S02", [3.0, 3.1, 3.2], 3, RANGE, seg_type="main_dimension")
    rows = ms.tape_to_rows(doc)
    assert rows[1] == {"id": "S02", "type": "main_dimension", "ground_truth_m": "3.1000", "used_as_anchor": 0, "endpoints/notes": "tape 3/3.1/3.2"}
    p = tmp_path / "gt" / "measurements.csv"
    ms.write_csv(p, rows)
    with open(p, newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == ms.CSV_COLUMNS
    with pytest.raises(ms.MeasureError, match="overwrite"):
        ms.write_csv(p, rows)
    ms.write_csv(p, rows, overwrite=True)
    assert ms.gt_from_csv(p)["S01"] == {"gt_m": 1.5, "anchor": True}


# ---------------------------------------------------------------------------
# So sánh
# ---------------------------------------------------------------------------


def test_compare_loai_moc_va_chi_so():
    doc = new_doc()
    for i, length in (("S01", 1.5), ("S02", 3.04), ("S03", 2.0), ("S04", 0.5)):
        ms.add_segment(doc, i, (0, 0, 0), (length, 0, 0))
    gt = {"S01": {"gt_m": 1.5, "anchor": True}, "S02": {"gt_m": 3.00, "anchor": False}, "S03": {"gt_m": 2.10, "anchor": False},
          "S05": {"gt_m": 1.0, "anchor": False}}
    res = ms.compare(doc, gt, 5.0)
    assert [r["id"] for r in res["rows"]] == ["S02", "S03"]
    assert res["excluded_anchor"] == ["S01"] and res["missing_gt"] == ["S04"] and res["missing_model"] == ["S05"]
    m = res["metrics"]
    assert m["n"] == 2 and m["mae_cm"] == pytest.approx(7.0) and m["median_cm"] == pytest.approx(7.0)
    assert m["mape_percent"] == pytest.approx((0.04 / 3.0 + 0.10 / 2.1) / 2 * 100) and m["under_pct"] == pytest.approx(50.0)
    assert res["rows"][1]["err_cm"] == pytest.approx(-10.0)


def test_compare_khong_co_doan_test_la_loi():
    doc = new_doc()
    ms.add_segment(doc, "S01", (0, 0, 0), (1.5, 0, 0))
    with pytest.raises(ms.MeasureError, match="không có đoạn test"):
        ms.compare(doc, {"S01": {"gt_m": 1.5, "anchor": True}}, 5.0)


# ---------------------------------------------------------------------------
# Vòng chọn (GUI giả)
# ---------------------------------------------------------------------------


def scripted(answers):
    it = iter(answers)
    return lambda prompt: next(it)


def test_pick_loop_luu_moi_doan_goi_y_id_tu_gt_va_ho_tro_xoa():
    pts = np.array([[0, 0, 0], [1, 0, 0], [0, 2, 0], [0, 0, 3.0]])
    hints = {"S01": {"gt_m": 1.0, "anchor": False, "label": "a"}, "S02": {"gt_m": 2.0, "anchor": False, "label": "b"}}
    doc, saves, picks = new_doc(), [], iter([(0, 1), (2, 3), None, (0, 2)])
    pe.pick_loop(doc, lambda: saves.append(len(doc["segments"])), pts, hints, pick=lambda p, t: next(picks),
                 ask=scripted(["", "", "ghi", "y",          # S01 (id mặc định), ghi chú, lưu
                               "", "", "", "n",             # S02 với (2,3): người dùng chọn n, không lưu
                               "", "S02",                   # pick trả None: không lưu
                               "", "S02", "", "y",          # (0,2) lưu thành S02
                               "u", "q"]), out=lambda s: None)   # u xoá S02
    assert [s["id"] for s in doc["segments"]] == ["S01"] and doc["segments"][0]["note"] == "ghi"
    assert doc["segments"][0]["a_index"] == 0 and doc["segments"][0]["b_index"] == 1 and doc["segments"][0]["length_m"] == 1.0
    assert saves == [1, 2, 1]


# ---------------------------------------------------------------------------
# CLI trên scene giả
# ---------------------------------------------------------------------------


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "repo"
    rows = [{"video_id": "111", "visit_id": "1", "split": "train", "sky_direction": "Up", "source_dir": "x", "seed": "42"},
            {"video_id": "333", "visit_id": "3", "split": "heldout", "sky_direction": "Up", "source_dir": "x", "seed": "42"}]
    sp.write_splits(rows, root / "data" / "splits.csv")
    sp.write_lock(root / "data" / "splits.csv", 42)
    data = tmp_path / "scenes"
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(f"paths:\n  data_root: {data.as_posix()}\nmeasure:\n  tape_readings: 3\n  anchor_min_m: 1.0\n  anchor_max_m: 2.0\n  under_cm: 5.0\n",
                   encoding="utf-8")
    scene = data / "arkitscenes" / "111"
    # điểm mô hình: x = 0…3 m
    write_ply(scene / "proposed" / "export" / "model_points.ply",
              {k: v.astype(np.float32) for k, v in zip("xyz", (np.linspace(0, 3, 31), np.zeros(31), np.zeros(31)))})
    return {"base": ["--scene", "arkitscenes/111", "--root", str(root), "--config", str(cfg)], "scene": scene, "root": root, "cfg": cfg}


def run(env, *args):
    return pe.main([args[0]] + env["base"] + list(args[1:]))


def test_cli_add_tape_compare_dau_cuoi(env, capsys):
    assert run(env, "add", "--id", "S01", "--a", "0", "0", "0", "--b", "1.5", "0", "0") == 0
    assert run(env, "add", "--id", "S02", "--a", "0", "0", "0", "--b", "3.04", "0", "0") == 0
    assert run(env, "tape", "--id", "S01", "--readings", "1.5", "1.5", "1.5", "--anchor") == 0
    assert run(env, "tape", "--id", "S02", "--readings", "3.0", "3.0", "3.0") == 0
    capsys.readouterr()
    assert run(env, "compare") == 0
    out = capsys.readouterr().out
    assert "thước dây" in out and "1 đoạn test" in out and "MAE 4.00 cm" in out and "%<5 cm 100.0%" in out
    assert "mốc scale: S01" in out
    # --write-csv tạo measurements.csv đúng hợp đồng, lần hai bị từ chối
    assert run(env, "tape", "--write-csv") == 0
    assert run(env, "tape", "--write-csv") == 1
    assert ms.gt_from_csv(env["scene"] / "ground_truth" / "measurements.csv")["S01"]["anchor"] is True
    assert run(env, "compare", "--gt", "csv", "--out", str(env["scene"] / "so_sanh.csv")) == 0
    assert (env["scene"] / "so_sanh.csv").read_text(encoding="utf-8").splitlines()[1].startswith("S02,3.0")


def test_cli_chan_heldout_hash_lech_va_so_do_sai(env, capsys):
    assert pe.main(["add", "--scene", "arkitscenes/333", "--root", str(env["root"]), "--config", str(env["cfg"]),
                    "--id", "S01", "--a", "0", "0", "0", "--b", "1", "0", "0"]) == 1
    assert "held-out" in capsys.readouterr().out
    assert run(env, "add", "--id", "S01", "--a", "0", "0", "0", "--b", "1", "0", "0") == 0
    assert run(env, "tape", "--id", "S01", "--readings", "1.5", "1.5") == 1          # chỉ 2 lần đo
    ply = env["scene"] / "proposed" / "export" / "model_points.ply"
    ply.write_bytes(ply.read_bytes() + b"\0")                                         # mô hình bị dựng lại
    capsys.readouterr()
    assert run(env, "add", "--id", "S02", "--a", "0", "0", "0", "--b", "1", "0", "0") == 1
    assert "đã đổi" in capsys.readouterr().out
    assert json.loads(ms.endpoints_path(env["scene"], "proposed").read_text(encoding="utf-8"))["segments"][0]["id"] == "S01"


def test_load_points_ply(env):
    p = pe.load_points(env["scene"] / "proposed" / "export" / "model_points.ply")
    assert p.shape == (31, 3) and p[-1, 0] == pytest.approx(3.0)


def test_gt_hints_bo_toa_do_faro_khoi_nhan(tmp_path):
    gt = tmp_path / "ground_truth"
    gt.mkdir()
    ms.write_csv(gt / "measurements.csv", [{"id": "S01", "type": "local_distance", "ground_truth_m": "0.7389", "used_as_anchor": 0,
                                           "endpoints/notes": "A=(0.455, 3.244, 0.140) B=(1.194, 3.249, 0.135); Rộng tủ"}])
    assert pe.gt_hints(tmp_path) == {"S01": {"gt_m": 0.7389, "anchor": False, "label": "Rộng tủ"}}
    assert pe.next_free_id(new_doc(), pe.gt_hints(tmp_path)) == "S01"
