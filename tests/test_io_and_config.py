"""Test đọc/ghi, định dạng ARKitScenes và nạp cấu hình."""

import numpy as np
import pytest

from pipeline.common import config as cfgmod
from pipeline.common.io import (
    frame_id_from_name,
    parse_pincam,
    parse_traj_line,
    read_traj,
    scene_layout,
)
from pipeline.common.schema import (
    KEYFRAME_COLUMNS,
    ScaleInfo,
    Sim3Result,
    read_keyframes_csv,
    write_keyframes_csv,
)


def test_frame_id_from_name_pdf_example():
    # ĐC §10.2: 47333462_5201.456.png → 5201.456
    assert frame_id_from_name("47333462_5201.456.png") == "5201.456"
    assert frame_id_from_name("lowres_wide/42444738_77949.751.png") == "77949.751"
    assert frame_id_from_name("42444738_77936.756.pincam") == "77936.756"
    with pytest.raises(ValueError):
        frame_id_from_name("khong_co_gach.png".replace("_", ""))


def test_parse_pincam_real_sample():
    # Dòng thật của scene 42444738 (lowres_wide_intrinsics): w h fx fy cx cy
    k = parse_pincam("256 192 213.293 213.293 128.371 95.7593")
    assert (k["w"], k["h"]) == (256, 192)
    assert k["fx"] == pytest.approx(213.293) and k["cy"] == pytest.approx(95.7593)
    with pytest.raises(ValueError):
        parse_pincam("256 192 213.293")


def test_parse_traj_line_validation():
    with pytest.raises(ValueError):
        parse_traj_line("1 2 3")


def test_read_traj_file(tmp_path):
    f = tmp_path / "lowres_wide.traj"
    f.write_text("5201.456 0 0 -1.5708 -1.20 1.65 -1.40\n\n77933.82 0 0 0 0 0 0\n", encoding="utf-8")
    rows = read_traj(f)
    assert len(rows) == 2 and rows[0][0] == pytest.approx(5201.456)
    assert np.allclose(rows[1][1], np.eye(3))


def test_scene_layout_follows_section_9(tmp_path):
    lay = scene_layout(tmp_path, "arkitscenes", "42444738")
    lay.make_dirs()
    for rel in ("raw", "frames/candidates", "frames/keyframes", "metadata", "ground_truth/faro",
                "baselines/colmap/sfm", "baselines/colmap/mvs", "baselines/vggt",
                "proposed/alignment", "proposed/fusion", "proposed/plane_refinement", "proposed/export",
                "evaluation/logs", "evaluation/figures"):
        assert (lay.root / rel).is_dir(), rel
    assert lay.root == tmp_path / "arkitscenes" / "42444738"


def test_schema_roundtrip(tmp_path):
    sim = Sim3Result(s=3.2, R=[[0, -1, 0], [1, 0, 0], [0, 0, 1]], t=[1, 2, 0], n_pairs=12, n_inliers=10, rmse=0.0)
    sim.to_json(tmp_path / "chunk_00_sim3.json")
    s, r, t = Sim3Result.from_json(tmp_path / "chunk_00_sim3.json").matrices()
    assert s == 3.2 and r.shape == (3, 3) and t.tolist() == [1, 2, 0]

    sc = ScaleInfo(s_m=2.0, L_real=1.5, L_model=0.75, anchor_id="A1")
    sc.to_json(tmp_path / "scale.json")
    assert ScaleInfo.from_json(tmp_path / "scale.json") == sc

    rows = [{"view_id": 0, "frame_ts": 77936.756, "src_name": "x.png", "V": 575.0, "q_blur": 0.99,
             "q_exposure": 0.98, "sky_direction": "Left", "rot_applied": "cw90",
             "w": 192, "h": 256, "fx": 213.293, "fy": 213.293, "cx": 96.2407, "cy": 128.371}]
    write_keyframes_csv(rows, tmp_path / "keyframes.csv")
    back = read_keyframes_csv(tmp_path / "keyframes.csv")
    assert list(back[0].keys()) == KEYFRAME_COLUMNS and back[0]["rot_applied"] == "cw90"


def test_default_config_loads_and_exposes_expected_keys():
    cfg = cfgmod.load_config()
    keys = cfgmod.flatten_keys(cfg)
    for k in ("fusion.tau_e", "fusion.tau_sigma", "plane.tau_r", "plane.alpha", "vggt.chunk",
              "quality.v_ref.vga", "eval.snap_radius_m", "loss.alpha_r"):
        assert k in keys, k
    assert cfgmod.get(cfg, "fusion.tau_e") == 2.0
    assert cfgmod.get(cfg, "fusion.tau_sigma") == 0.20
    assert cfgmod.get(cfg, "eval.snap_radius_m") == 0.02  # 2 cm (Q4)
    assert cfgmod.get(cfg, "vggt.chunk") - cfgmod.get(cfg, "vggt.overlap") == 10
    assert cfgmod.get(cfg, "plane.alpha") == 0.5


def test_v_ref_g_ref_are_measured_on_validation_not_581():
    cfg = cfgmod.load_config()
    for k in ("v_ref", "g_ref"):
        assert cfgmod.require(cfg, f"quality.{k}.vga") > 0
        assert cfgmod.get(cfg, f"quality.{k}.measured_on") == "validation"
        assert cfgmod.get(cfg, f"quality.{k}.n_scenes") == 6
        assert cfgmod.get(cfg, f"quality.{k}.date")
    assert cfgmod.get(cfg, "quality.v_ref.vga") not in (581.0, 635.3)       # không dùng số cũ của đề cương hay số lowres


def test_unmeasured_parameters_are_null_and_require_fails():
    cfg = cfgmod.load_config()
    assert cfgmod.get(cfg, "keyframe.blur.q_drop") is None                  # chưa có căn cứ, khoá ở M2
    with pytest.raises(ValueError):
        cfgmod.require(cfg, "keyframe.blur.q_drop")                         # không có số mặc định
    with pytest.raises(KeyError):
        cfgmod.get(cfg, "khong.ton.tai")


def test_no_legacy_lambda_keys_in_config():
    keys = " ".join(cfgmod.flatten_keys(cfgmod.load_config()))
    assert "lambda" not in keys  # PDF dùng τ_e, τ_σ (không phải λ)


def test_colmap_exe_resolution(monkeypatch):
    monkeypatch.delenv("COLMAP_EXE", raising=False)
    assert cfgmod.resolve_colmap_exe({"paths": {"colmap_exe": None}}) == cfgmod.DEFAULT_COLMAP_EXE
    monkeypatch.setenv("COLMAP_EXE", "X:/colmap.exe")
    assert str(cfgmod.resolve_colmap_exe({"paths": {"colmap_exe": None}})).replace("\\", "/") == "X:/colmap.exe"
    assert str(cfgmod.resolve_colmap_exe({"paths": {"colmap_exe": "Y:/c.exe"}})).replace("\\", "/") == "Y:/c.exe"


def test_env_expansion_and_hash(monkeypatch, tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("paths:\n  colmap_exe: ${MY_COLMAP}\n  other: abc\n", encoding="utf-8")
    monkeypatch.delenv("MY_COLMAP", raising=False)
    assert cfgmod.load_config(p)["paths"]["colmap_exe"] is None  # biến không có → None, không đoán
    monkeypatch.setenv("MY_COLMAP", "Z:/x.exe")
    cfg = cfgmod.load_config(p)
    assert cfg["paths"]["colmap_exe"] == "Z:/x.exe"
    assert cfgmod.config_hash(cfg) == cfgmod.config_hash(dict(reversed(list(cfg.items()))))  # độc lập thứ tự khoá
