"""Test stage `eval` trên scene tổng hợp: tường phẳng, hai biến thể (B0 đúng, B3 kéo giãn 5% theo y), mốc bị loại, nhãn auto, tập chung, hình học."""

import csv

import numpy as np
import pytest

from pipeline import run as pr
from pipeline.common import config as cfgmod
from pipeline.common.errors import E_MISSING_INPUT, StageError
from pipeline.common.io import SceneLayout, write_json
from pipeline.common.ply import write_ply
from pipeline.common.schema import write_keyframes_csv
from pipeline.eval import stage as es
from pipeline.export import measure as ms

R_M = np.array([[np.cos(0.5), -np.sin(0.5), 0], [np.sin(0.5), np.cos(0.5), 0], [0, 0, 1.0]])
T_M = np.array([1.0, 2.0, 3.0])
S_M = 0.5
MEAS = """id,type,ground_truth_m,used_as_anchor,endpoints/notes
S00,door_window,1.0,1,"A=(0.0, 0.5, 0.5) B=(0.0, 1.5, 0.5); mốc"
S01,local_distance,1.0,0,"A=(0.0, 0.5, 0.5) B=(0.0, 1.5, 0.5); ngang"
S02,local_distance,1.2,0,"A=(0.0, 1.0, 0.2) B=(0.0, 1.0, 1.4); đứng"
S03,local_distance,0.8,0,"A=(0.5, 0.5, 0.5) B=(0.5, 1.3, 0.5); lơ lửng ngoài tường"
"""


def _wall(step=0.01):
    y, z = np.meshgrid(np.arange(0, 2.0001, step), np.arange(0, 2.0001, step))
    return np.stack([np.zeros(y.size), y.ravel(), z.ravel()], axis=1)


def _ply(path, pts):
    write_ply(path, {"x": pts[:, 0].astype(np.float32), "y": pts[:, 1].astype(np.float32), "z": pts[:, 2].astype(np.float32)})


@pytest.fixture()
def scene(tmp_path):
    layout = SceneLayout(tmp_path / "scene")
    cams_gt = {v: np.array([1.5 + 0.2 * v, 0.5 + 0.1 * v, 1.0]) for v in range(8)}
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "lowres_wide.traj").write_text("".join(f"{100.0 + 0.1 * v:.1f} 0 0 0 {-c[0]} {-c[1]} {-c[2]}\n" for v, c in cams_gt.items()), encoding="utf-8")
    write_json(layout.raw / "source.json", {"raw_dir": str(raw)})
    write_keyframes_csv([{"view_id": v, "frame_ts": round(100.0 + 0.1 * v, 1)} for v in cams_gt], layout.metadata / "keyframes.csv")
    layout.ground_truth.mkdir(parents=True, exist_ok=True)
    (layout.ground_truth / "measurements.csv").write_text(MEAS, encoding="utf-8")
    write_json(layout.alignment / "scale.json", {"s_m": S_M})
    wall = _wall()
    to_model = lambda p: p @ R_M.T + T_M   # noqa: E731
    _ply(layout.colmap_metric / "fused_metric.ply", to_model(wall))                                     # B0: đúng
    _ply(layout.fusion / "fused_points.ply", to_model(wall * np.array([1.0, 1.05, 1.0])))              # B3: kéo giãn 5% theo y
    _ply(layout.faro / "faro_scene_frame.ply", wall)
    cams_colmap = {v: {"center": to_model(c[None])[0] / S_M} for v, c in cams_gt.items()}               # đv COLMAP = mét / s_m
    return layout, cams_colmap


@pytest.fixture()
def cfg():
    c = cfgmod.load_config()
    c["eval"].update(crop_margin_m=2.0, voxel_m=0.02, mode="auto")
    return c


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return {r["variant"]: r for r in csv.DictReader(f)}


def test_eval_hai_bien_the_tong_hop(scene, cfg):
    layout, cams = scene
    stats = es.run_eval(layout, cfg, log=lambda m: None, variants=["B0", "B3"], load_cameras=lambda lay: cams)
    assert stats["n_segments"] == 3 and stats["variants"] == ["B0", "B3"]            # mốc S00 bị loại khỏi chỉ số test
    rows = _read(layout.evaluation / "metrics.csv")
    b0, b3 = rows["B0"], rows["B3"]
    assert b0["length_mode"] == "auto" and float(b0["ate_rigid_cm"]) < 1e-3 and int(b0["n_cameras"]) == 8
    assert int(b0["n_valid"]) == 2 and float(b0["mae_cm"]) < 0.5                       # S03 lơ lửng cách tường 0,5 m: không snap, không hợp lệ
    assert int(b0["n_unsnapped_endpoints"]) == 2 and float(b0["nn_median_cm"]) > 0
    assert stats["common_ids"] == ["S01", "S02"] and int(b3["n_common"]) == 2
    # Giới hạn của protocol auto: phép cứng scale=1 giữ nguyên chiều dài GT nên lỗi chiều dài chỉ còn là nhiễu snap (≤ 2 × bán kính);
    # B3 kéo giãn 5% KHÔNG làm lỗi chiều dài tăng, nhưng lộ ra ở Chamfer/F-score (bên dưới).
    assert float(b3["mae_cm"]) <= 4.0 and float(b3["delta_pct_mae_vs_B0"]) == float(b3["delta_pct_mae_vs_B0"])
    assert float(b0["chamfer_cm"]) < 1.5 and float(b0["f_score"]) > 0.99
    assert float(b3["chamfer_cm_kabsch"]) > float(b0["chamfer_cm_kabsch"])
    assert (layout.logs / "lengths_B0_auto.csv").is_file() and (layout.logs / "align_B3.json").is_file() and (layout.logs / "eval_result.json").is_file()


def test_eval_manual_dung_file_endpoints_va_roi_ve_auto(scene, cfg):
    layout, cams = scene
    cfg["eval"]["mode"] = "manual"
    write_json(layout.logs / "endpoints_B0.json", {"scene": "x", "variant": "B0", "unit": "m", "frame": "variant_cloud",
                                                   "endpoints": {"S01": {"a": [0, 0, 0], "b": [1.03, 0, 0]}}})
    es.run_eval(layout, cfg, log=lambda m: None, variants=["B0", "B3"], load_cameras=lambda lay: cams)
    rows = _read(layout.evaluation / "metrics.csv")
    assert rows["B0"]["length_mode"] == "manual" and int(rows["B0"]["n_valid"]) == 1 and float(rows["B0"]["mae_cm"]) == pytest.approx(3.0)
    assert rows["B3"]["length_mode"] == "auto"                                         # B3 chưa có file → auto, nhãn ghi rõ


def test_eval_mac_dinh_bo_qua_bien_the_thieu_va_loi_khi_chi_dinh(scene, cfg):
    layout, cams = scene
    stats = es.run_eval(layout, cfg, log=lambda m: None, load_cameras=lambda lay: cams)
    assert stats["variants"] == ["B0", "B3"] and set(stats["skipped"]) == {"B1", "proposed", "abl_quality"}
    with pytest.raises(StageError) as e:
        es.run_eval(layout, cfg, log=lambda m: None, variants=["proposed"], load_cameras=lambda lay: cams)
    assert e.value.code == E_MISSING_INPUT
    with pytest.raises(ValueError, match="M5"):
        es.run_eval(layout, cfg, log=lambda m: None, variants=["abl_gate"], load_cameras=lambda lay: cams)


def test_variant_layout_khong_ghi_de_proposed(scene):
    from pipeline.eval.variants import VariantLayout, base_layout
    layout, _ = scene
    v = VariantLayout(layout.root, "abl_quality")
    assert v.fusion != layout.fusion and v.fusion == layout.proposed / "variants" / "abl_quality" / "fusion"
    assert v.alignment == layout.alignment and v.logs != layout.logs and base_layout(v) == layout


def test_run_main_variant(tmp_path, monkeypatch, capsys):
    """pipeline.run: --variant B0 chỉ cho eval; abl_quality đổi layout + use_quality=false và chỉ cho fuse/gate hoặc eval."""
    from pipeline.common import splits as sp
    rows = [{"video_id": "111", "visit_id": "1", "split": "train", "sky_direction": "Left", "source_dir": "data/raw/arkitscenes/Training/111", "seed": "42"}]
    p = tmp_path / "data" / "splits.csv"
    p.parent.mkdir(parents=True)
    sp.write_splits(rows, p)
    sp.write_lock(p, 42)
    seen = []
    monkeypatch.setitem(pr.IMPLEMENTED, "fuse", lambda c, log: seen.append((type(c["info"]["layout"]).__name__, c["cfg"]["fusion"]["use_quality"])) or {})
    monkeypatch.setitem(pr.IMPLEMENTED, "gate", lambda c, log: {})
    monkeypatch.setitem(pr.IMPLEMENTED, "eval", lambda c, log: seen.append(("eval", c["variant"])) or {})
    base = ["--root", str(tmp_path), "--scene", "arkitscenes/111"]
    assert pr.main(base + ["--variant", "B0", "--from-stage", "fuse", "--to-stage", "gate"]) == 1
    assert pr.main(base + ["--variant", "abl_quality", "--from-stage", "fuse", "--to-stage", "export"]) == 1
    assert pr.main(base + ["--variant", "abl_quality", "--from-stage", "fuse", "--to-stage", "gate"]) == 0
    assert seen == [("VariantLayout", False)]
    assert pr.main(base + ["--variant", "B1", "--from-stage", "eval", "--to-stage", "eval"]) == 0 and seen[-1] == ("eval", "B1")
    assert pr.main(base + ["--from-stage", "eval", "--to-stage", "eval"]) == 0 and seen[-1] == ("eval", None)
    assert "[LỖI]" in capsys.readouterr().out


def _proposed_endpoints(layout):
    """Ghi `endpoints_proposed.json` đúng cách của `scripts/pick_endpoints.py` (hệ model) + `export/measurements.json` có `frame`; trả về mô hình: cm → model."""
    c, sn = np.cos(0.7), np.sin(0.7)
    r_e, t_e = np.array([[c, 0, sn], [0, 1.0, 0], [-sn, 0, c]]), np.array([0.5, -1.0, 0.25])
    write_json(layout.export / "measurements.json", {"frame": {"rotation_from_colmap_metric": r_e.tolist(), "translation": t_e.tolist()}})
    to_cm = lambda p: np.asarray(p) @ R_M.T + T_M                         # noqa: E731  hệ tường → hệ COLMAP mét của fixture
    doc = ms.new_endpoints("arkitscenes/1", "proposed", "proposed/export/model_points.ply", "0" * 64)
    for sid, a, b in (("S01", [0.0, 0.5, 0.5], [0.0, 1.5, 0.5]), ("S02", [0.0, 1.0, 0.2], [0.0, 1.0, 1.4])):
        ms.add_segment(doc, sid, (r_e @ to_cm(a) + t_e).tolist(), (r_e @ to_cm(b) + t_e).tolist())
    ms.save_endpoints(layout.logs / "endpoints_proposed.json", doc)


def test_eval_truyen_dau_mut_tu_proposed_sang_b0_b3(scene, cfg):
    layout, cams = scene
    cfg["eval"]["mode"] = "manual"
    _proposed_endpoints(layout)
    es.run_eval(layout, cfg, log=lambda m: None, variants=["B0", "B3"], load_cameras=lambda lay: cams)
    rows = _read(layout.evaluation / "metrics.csv")
    assert rows["B0"]["length_mode"] == "manual_transfer" and int(rows["B0"]["n_valid"]) == 2 and float(rows["B0"]["mae_cm"]) < 0.1
    assert rows["B3"]["length_mode"] == "manual_transfer" and int(rows["B3"]["n_valid"]) == 2     # S03 chưa chấm ở nguồn → không hợp lệ
    assert (layout.logs / "lengths_B0_manual_transfer.csv").is_file()


def test_eval_truyen_dau_mut_sang_b1_qua_phep_cung_tam_camera(scene, cfg):
    layout, cams = scene
    cfg["eval"]["mode"] = "manual"
    _proposed_endpoints(layout)
    c, sn = np.cos(0.3), np.sin(0.3)
    r1, t1 = np.array([[c, -sn, 0], [sn, c, 0], [0, 0, 1.0]]), np.array([5.0, -2.0, 1.0])    # hệ chuỗi VGGT = cứng từ hệ COLMAP mét
    to_cm = lambda p: np.asarray(p) @ R_M.T + T_M                         # noqa: E731
    _ply(layout.vggt_metric / "points_metric.ply", to_cm(_wall()) @ r1.T + t1)
    write_json(layout.vggt_metric / "cameras_metric.json", {"centers": {str(v): (cm["center"] * S_M @ r1.T + t1).tolist() for v, cm in cams.items()}})
    es.run_eval(layout, cfg, log=lambda m: None, variants=["B1"], load_cameras=lambda lay: cams)
    row = _read(layout.evaluation / "metrics.csv")["B1"]
    assert row["length_mode"] == "manual_transfer" and int(row["n_valid"]) == 2 and float(row["mae_cm"]) < 0.1


def test_eval_manual_doc_file_segments_he_model_cho_b0(scene, cfg):
    """File do measure ghi cho chính B0 (chọn trên cloud B0 ⇒ frame variant_cloud) đọc được và nhãn là manual, không phải transfer."""
    layout, cams = scene
    cfg["eval"]["mode"] = "manual"
    doc = ms.new_endpoints("arkitscenes/1", "B0", "baselines/colmap/metric/fused_metric.ply", "0" * 64, ms.frame_of_points_file("fused_metric.ply"))
    ms.add_segment(doc, "S01", [0, 0, 0], [1.03, 0, 0])
    ms.save_endpoints(layout.logs / "endpoints_B0.json", doc)
    es.run_eval(layout, cfg, log=lambda m: None, variants=["B0"], load_cameras=lambda lay: cams)
    row = _read(layout.evaluation / "metrics.csv")["B0"]
    assert row["length_mode"] == "manual" and int(row["n_valid"]) == 1 and float(row["mae_cm"]) == pytest.approx(3.0)
