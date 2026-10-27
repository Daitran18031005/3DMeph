"""Test pipeline/run.py: chọn scene theo splits (chặn held-out), run_meta.json, mã lỗi, khoảng stage. Không chạy COLMAP thật."""

import json
from pathlib import Path

import pytest

from pipeline import run as pr
from pipeline.common import config as cfgmod
from pipeline.common import splits as sp
from pipeline.common.errors import E_NOT_IMPLEMENTED, E_TOO_FEW_KEYFRAMES, StageError

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def root(tmp_path):
    rows = [{"video_id": "111", "visit_id": "1", "split": "train", "sky_direction": "Left", "source_dir": "data/raw/arkitscenes/Training/111", "seed": "42"},
            {"video_id": "222", "visit_id": "2", "split": "val", "sky_direction": "Up", "source_dir": "data/raw/arkitscenes/Validation/222", "seed": "42"},
            {"video_id": "333", "visit_id": "3", "split": "heldout", "sky_direction": "Down", "source_dir": "data/raw/arkitscenes/Training/333", "seed": "42"}]
    csv_path = tmp_path / "data" / "splits.csv"
    csv_path.parent.mkdir(parents=True)
    sp.write_splits(rows, csv_path)
    sp.write_lock(csv_path, 42)
    return tmp_path


@pytest.fixture()
def cfg():
    return cfgmod.load_config()


def test_resolve_scene_train_val_va_chan_heldout(root, cfg):
    a = pr.resolve_scene(root, "arkitscenes/111", cfg)
    assert a["split"] == "train" and a["sky_direction"] == "Left" and a["visit_id"] == "1"
    assert a["raw_dir"] == root / "data/raw/arkitscenes/Training/111"
    assert a["layout"].root == root / "data" / "scenes" / "arkitscenes" / "111"
    assert pr.resolve_scene(root, "arkitscenes/222", cfg)["split"] == "val"
    with pytest.raises(sp.HeldoutError):
        pr.resolve_scene(root, "arkitscenes/333", cfg)
    assert pr.resolve_scene(root, "arkitscenes/333", cfg, allow_heldout=True)["split"] == "heldout"
    with pytest.raises(ValueError):
        pr.resolve_scene(root, "arkitscenes/999", cfg)
    with pytest.raises(ValueError):
        pr.resolve_scene(root, "replica/room0", cfg)
    with pytest.raises(ValueError):
        pr.resolve_scene(root, "khong-co-gach-cheo", cfg)


def test_resolve_scene_tu_choi_khi_splits_bi_sua(root, cfg):
    (root / "data" / "splits.csv").write_text((root / "data" / "splits.csv").read_text(encoding="utf-8").replace("train", "val", 1), encoding="utf-8")
    with pytest.raises(sp.LockError):
        pr.resolve_scene(root, "arkitscenes/111", cfg)


def test_run_stage_ghi_run_meta_thanh_cong_va_that_bai(root, cfg, monkeypatch):
    info = pr.resolve_scene(root, "arkitscenes/111", cfg)
    ctx = {"info": info, "cfg": cfg}
    monkeypatch.setitem(pr.IMPLEMENTED, "keyframe", lambda c, log: {"n_keyframes": 7, "peak_vram_mib": 123.0})
    stats = pr.run_stage("keyframe", ctx, log=lambda m: None)
    assert stats["n_keyframes"] == 7
    meta_path = info["layout"].logs / "run_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["scene"] == "arkitscenes/111" and meta["config_hash"] == cfgmod.config_hash(cfg) and "git_head" in meta
    ent = meta["stages"]["keyframe"]
    assert ent["status"] == "ok" and ent["error_code"] is None and ent["peak_vram_mib"] == 123.0 and ent["seconds"] >= 0

    def boom(c, log):
        raise StageError(E_TOO_FEW_KEYFRAMES, "chỉ 3 khung")
    monkeypatch.setitem(pr.IMPLEMENTED, "sfm", boom)
    with pytest.raises(StageError):
        pr.run_stage("sfm", ctx, log=lambda m: None)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["stages"]["sfm"]["status"] == "failed" and meta["stages"]["sfm"]["error_code"] == E_TOO_FEW_KEYFRAMES
    assert meta["stages"]["keyframe"]["status"] == "ok"                     # mục stage trước giữ nguyên

    with pytest.raises(StageError) as e:
        pr.run_stage("fuse", ctx, log=lambda m: None)
    assert e.value.code == E_NOT_IMPLEMENTED and "M1d" in str(e.value)
    assert json.loads(meta_path.read_text(encoding="utf-8"))["stages"]["fuse"]["error_code"] == E_NOT_IMPLEMENTED


def test_main_ma_thoat(root, monkeypatch, capsys):
    base = ["--root", str(root), "--scene"]
    assert pr.main(base + ["arkitscenes/333"]) == 1                          # held-out
    assert "held-out" in capsys.readouterr().out
    assert pr.main(base + ["arkitscenes/999"]) == 1                          # không có trong splits
    assert pr.main(base + ["arkitscenes/111", "--from-stage", "mvs", "--to-stage", "sfm"]) == 1
    calls = []
    monkeypatch.setitem(pr.IMPLEMENTED, "keyframe", lambda c, log: calls.append("keyframe") or {})
    monkeypatch.setitem(pr.IMPLEMENTED, "sfm", lambda c, log: calls.append("sfm") or {})
    monkeypatch.setitem(pr.IMPLEMENTED, "mvs", lambda c, log: calls.append("mvs") or {})
    assert pr.main(base + ["arkitscenes/111", "--to-stage", "sfm"]) == 0 and calls == ["keyframe", "sfm"]
    monkeypatch.setitem(pr.IMPLEMENTED, "vggt", lambda c, log: calls.append("vggt") or {})
    monkeypatch.setitem(pr.IMPLEMENTED, "align", lambda c, log: calls.append("align") or {})
    assert pr.main(base + ["arkitscenes/111", "--from-stage", "sfm", "--to-stage", "gate"]) == 2        # fuse chưa cài
    assert "E_NOT_IMPLEMENTED" in capsys.readouterr().out
    assert calls == ["keyframe", "sfm", "sfm", "mvs", "vggt", "align"]       # dừng ở fuse, không chạy các stage sau


def test_stages_va_not_implemented_nhat_quan():
    assert pr.STAGES == ["keyframe", "sfm", "mvs", "vggt", "align", "fuse", "gate", "export", "eval"]
    assert set(pr.NOT_IMPLEMENTED) | set(pr.IMPLEMENTED) == set(pr.STAGES)
