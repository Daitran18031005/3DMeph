"""Test stage keyframe (pipeline/keyframe/extract.py) bằng scene tổng hợp: chọn ứng viên, lọc blur, thưa đều, xoay đứng, file đầu ra, mã lỗi."""

import copy
import json
import zipfile

import cv2
import numpy as np
import pytest

from pipeline.common import config as cfgmod
from pipeline.common import io as pio
from pipeline.common.errors import E_MISSING_INPUT, E_TOO_FEW_KEYFRAMES, StageError
from pipeline.common.schema import read_keyframes_csv
from pipeline.keyframe import extract as kf

W, H = 64, 48
N_FRAMES, HZ = 300, 30.0        # 10 s ở 30 khung/giây ⇒ 20 hoặc 21 ứng viên ở 2 fps


def _png(img):
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def make_raw(tmp_path, blurred=(), drop_intrinsics=()):
    """vga_wide.zip (ảnh nhiễu sắc nét, một số khung bị làm mờ mạnh) + vga_wide_intrinsics.zip (fx đổi dần)."""
    raw = tmp_path / "raw"
    raw.mkdir(parents=True)
    rng = np.random.default_rng(0)
    with zipfile.ZipFile(raw / "vga_wide.zip", "w") as zr, zipfile.ZipFile(raw / "vga_wide_intrinsics.zip", "w") as zi:
        zr.writestr("vga_wide/", b"")
        zi.writestr("vga_wide_intrinsics/", b"")
        for i in range(N_FRAMES):
            ts = 1000.0 + i / HZ
            img = rng.integers(0, 256, (H, W), dtype=np.uint8)
            if i in blurred:
                img = cv2.GaussianBlur(img, (0, 0), 8)
            zr.writestr(f"vga_wide/777_{ts:.3f}.png", _png(img))
            if i not in drop_intrinsics:
                zi.writestr(f"vga_wide_intrinsics/777_{ts:.3f}.pincam", f"{W} {H} {500 + i * 0.1:.3f} {500 + i * 0.1:.3f} 32.0 24.0")
    return raw


def cfg_with(**over):
    cfg = copy.deepcopy(cfgmod.load_config())
    cfg["keyframe"]["target_min"] = 5
    for k, v in over.items():
        sect, key = k.split("__")
        cfg[sect][key] = v
    return cfg


def test_select_candidates_va_thin_even():
    ts = [1000.0 + i / 30 for i in range(300)]
    idx = kf.select_candidates(ts, 2.0)
    assert idx[0] == 0 and len(idx) in (20, 21) and set(np.diff(idx)) <= {14, 15, 16}
    assert kf.select_candidates([], 2.0) == []
    with pytest.raises(ValueError):
        kf.select_candidates(ts, 0)
    items = list(range(112))
    out = kf.thin_even(items, 80)
    assert len(out) == 80 and out[0] == 0 and out[-1] == 111 and out == sorted(set(out))
    assert kf.thin_even([1, 2, 3], 80) == [1, 2, 3]
    with pytest.raises(ValueError):
        kf.thin_even([1], 0)


def test_extract_bo_khung_mo_xoay_dung_va_ghi_file(tmp_path):
    blurred = {30, 60}                                          # cả hai là ứng viên (cách đúng 15 khung)
    raw = make_raw(tmp_path, blurred=blurred)
    layout = pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777")
    cfg = cfg_with()
    logs = []
    st = kf.extract_keyframes(raw, layout, cfg, "Left", source_info={"video_id": "777"}, log=logs.append)
    assert st["n_candidates"] in (20, 21) and st["n_after_blur"] == st["n_candidates"] - 2
    assert st["n_keyframes"] == st["n_after_blur"] and st["q_blur_min"] >= 0.35
    rows = read_keyframes_csv(layout.metadata / "keyframes.csv")
    assert len(rows) == st["n_keyframes"]
    assert {r["src_name"].split("_")[1][:-4] for r in rows}.isdisjoint({f"{1000 + 30 / 30:.3f}", f"{1000 + 60 / 30:.3f}"})
    assert rows[0]["rot_applied"] == "cw90" and rows[0]["w"] == str(H) and rows[0]["h"] == str(W)      # 64×48 → 48×64 sau xoay
    img = cv2.imread(str(layout.keyframes / "0000.jpg"))
    assert img.shape[:2] == (W, H) and (layout.keyframes / f"{len(rows) - 1:04d}.jpg").is_file()
    cam = json.loads((layout.metadata / "camera.json").read_text(encoding="utf-8"))
    assert cam["camera_model"] == "PINHOLE" and cam["w"] == H and cam["h"] == W
    assert cam["fx_min"] < cam["fx"] < cam["fx_max"]                      # intrinsics đổi theo khung: trung vị nằm giữa
    src = json.loads((layout.raw / "source.json").read_text(encoding="utf-8"))
    assert src["video_id"] == "777" and src["sky_direction"] == "Left" and src["stats"]["n_keyframes"] == len(rows)
    assert any("bỏ 2 khung" in m for m in logs)


def test_extract_thua_deu_khi_qua_nhieu(tmp_path):
    raw = make_raw(tmp_path)
    layout = pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777")
    st = kf.extract_keyframes(raw, layout, cfg_with(keyframe__target_max=10), "Up", log=lambda m: None)
    assert st["n_after_blur"] > 10 and st["n_keyframes"] == 10
    rows = read_keyframes_csv(layout.metadata / "keyframes.csv")
    assert rows[0]["rot_applied"] == "none" and rows[0]["w"] == str(W)
    ts = [float(r["frame_ts"]) for r in rows]
    assert ts == sorted(ts)


def test_extract_loi_it_keyframe_va_thieu_intrinsics(tmp_path):
    raw = make_raw(tmp_path)
    layout = pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777")
    with pytest.raises(StageError) as e:
        kf.extract_keyframes(raw, layout, cfg_with(keyframe__target_min=100), "Left", log=lambda m: None)
    assert e.value.code == E_TOO_FEW_KEYFRAMES
    raw2 = make_raw(tmp_path / "b", drop_intrinsics={0})                 # khung 0 là ứng viên đầu tiên
    with pytest.raises(StageError) as e2:
        kf.extract_keyframes(raw2, pio.scene_layout(tmp_path / "b" / "scenes", "arkitscenes", "777"), cfg_with(), "Left",
                             log=lambda m: None)
    assert e2.value.code == E_MISSING_INPUT


def test_extract_thieu_asset(tmp_path):
    (tmp_path / "raw").mkdir()
    with pytest.raises(StageError) as e:
        kf.extract_keyframes(tmp_path / "raw", pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777"), cfg_with(), "Left",
                             log=lambda m: None)
    assert e.value.code == E_MISSING_INPUT


def test_extract_khong_xoay_khi_tat_rotate_from_sky(tmp_path):
    raw = make_raw(tmp_path)
    layout = pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777")
    kf.extract_keyframes(raw, layout, cfg_with(keyframe__rotate_from_sky=False), "Left", log=lambda m: None)
    rows = read_keyframes_csv(layout.metadata / "keyframes.csv")
    assert rows[0]["rot_applied"] == "none" and rows[0]["w"] == str(W)
