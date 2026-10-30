"""Test stage keyframe (pipeline/keyframe/extract.py) bằng scene tổng hợp: chọn ứng viên dày, lọc blur, xoay đứng, file đầu ra, mã lỗi."""

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
    assert st["n_dense"] == st["n_after_blur"] and st["q_blur_min"] >= 0.35
    rows = read_keyframes_csv(layout.metadata / "candidates.csv")
    assert len(rows) == st["n_dense"]
    assert {r["src_name"].split("_")[1][:-4] for r in rows}.isdisjoint({f"{1000 + 30 / 30:.3f}", f"{1000 + 60 / 30:.3f}"})
    assert rows[0]["rot_applied"] == "cw90" and rows[0]["w"] == str(H) and rows[0]["h"] == str(W)      # 64×48 → 48×64 sau xoay
    img = cv2.imread(str(layout.candidates / "0000.jpg"))
    assert img.shape[:2] == (W, H) and (layout.candidates / f"{len(rows) - 1:04d}.jpg").is_file()
    cam = json.loads((layout.metadata / "camera.json").read_text(encoding="utf-8"))
    assert cam["camera_model"] == "PINHOLE" and cam["w"] == H and cam["h"] == W
    assert cam["fx_min"] < cam["fx"] < cam["fx_max"]                      # intrinsics đổi theo khung: trung vị nằm giữa
    src = json.loads((layout.raw / "source.json").read_text(encoding="utf-8"))
    assert src["video_id"] == "777" and src["sky_direction"] == "Left" and src["stats"]["n_dense"] == len(rows)
    assert any("bỏ 2 khung" in m for m in logs)


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
    rows = read_keyframes_csv(layout.metadata / "candidates.csv")
    assert rows[0]["rot_applied"] == "none" and rows[0]["w"] == str(W)


def make_moving_raw(tmp_path, px_per_frame=2.0, saturated=()):
    """Camera trượt ngang qua một cảnh nhiều hình tương phản (ORB khớp được): 10 s ở 30 khung/giây, 320×240; `saturated`: khung bị cháy sáng 60% diện tích."""
    raw = tmp_path / "raw"
    raw.mkdir(parents=True)
    rng = np.random.default_rng(0)
    wf, hf = 320, 240
    big = np.full((hf, wf + int(px_per_frame * N_FRAMES) + 10), 128, np.uint8)
    for _ in range(900):
        x, y = int(rng.integers(0, big.shape[1])), int(rng.integers(0, hf))
        c = int(rng.integers(0, 256))
        if rng.random() < 0.5:
            cv2.circle(big, (x, y), int(rng.integers(3, 14)), c, -1)
        else:
            cv2.rectangle(big, (x, y), (x + int(rng.integers(5, 25)), y + int(rng.integers(5, 25))), c, -1)
    big = cv2.GaussianBlur(big, (3, 3), 0)
    with zipfile.ZipFile(raw / "vga_wide.zip", "w") as zr, zipfile.ZipFile(raw / "vga_wide_intrinsics.zip", "w") as zi:
        zr.writestr("vga_wide/", b"")
        zi.writestr("vga_wide_intrinsics/", b"")
        for i in range(N_FRAMES):
            ts = 1000.0 + i / HZ
            x0 = int(i * px_per_frame)
            img = big[:, x0:x0 + wf].copy()
            if i in saturated:
                img[:, : int(wf * 0.6)] = 255
            zr.writestr(f"vga_wide/777_{ts:.3f}.png", _png(img))
            zi.writestr(f"vga_wide_intrinsics/777_{ts:.3f}.pincam", f"{wf} {hf} 300.0 300.0 160.0 120.0")
    return raw


def test_extract_loc_overlap_bo_khung_trung_va_giu_noi_tiep(tmp_path):
    """2 px/khung ⇒ 30 px giữa hai ứng viên liền kề (overlap ~ 90%): khung trùng bị bỏ, hai keyframe liền kề còn overlap trong [min, max]."""
    from pipeline.keyframe import overlap as ov
    raw = make_moving_raw(tmp_path)
    layout = pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777")
    st = kf.extract_keyframes(raw, layout, cfg_with(keyframe__overlap={"max": 0.8, "min": 0.6}), "Up", log=lambda m: None)
    assert st["n_after_exposure"] in (20, 21) and 3 <= st["n_after_overlap"] < st["n_after_exposure"] and st["n_dense"] == st["n_after_overlap"]
    assert st["n_overlap_breaks"] == 0
    feats = [ov.Features(cv2.imread(str(layout.candidates / f"{i:04d}.jpg"), cv2.IMREAD_GRAYSCALE)) for i in range(st["n_dense"])]
    o = [ov.overlap_fraction(feats[i], feats[i + 1])["overlap"] for i in range(len(feats) - 1)]
    assert min(o) >= 0.6 - 0.05 and max(o) <= 0.9                                    # theo `overlap.min` 0,6 và `overlap.max` 0,8 (dung sai đo)
    dense = kf.extract_keyframes(raw, layout, cfg_with(keyframe__overlap={"max": 0.98, "min": 0.6}), "Up", log=lambda m: None)
    assert dense["n_dense"] > st["n_dense"]                                    # ngưỡng trùng cao hơn thì giữ nhiều khung hơn


def test_extract_loc_exposure_va_thong_ke(tmp_path):
    raw = make_moving_raw(tmp_path, saturated={45, 75})                              # cả hai là ứng viên (45 = 3·15, 75 = 5·15)
    layout = pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777")
    cfg = cfg_with(keyframe__target_min=3)
    cfg["keyframe"]["blur"]["q_drop"] = 0.0                                           # tách riêng bộ lọc exposure
    cfg["keyframe"]["exposure"]["q_drop"] = 0.5
    st = kf.extract_keyframes(raw, layout, cfg, "Up", log=lambda m: None)
    assert st["n_after_blur"] - st["n_after_exposure"] == 2 and st["exposure_q_drop"] == 0.5
    assert st["q_exposure_min"] >= 0.5
    cfg["keyframe"]["exposure"]["q_drop"] = 0.0
    st0 = kf.extract_keyframes(raw, layout, cfg, "Up", log=lambda m: None)
    assert st0["n_after_blur"] == st0["n_after_exposure"]

