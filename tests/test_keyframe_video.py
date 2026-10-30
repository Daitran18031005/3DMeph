"""Test nguồn video của stage keyframe (adapters.VideoSource, keyframe.extract.extract_video_keyframes, run.resolve_video_scene).

Video tổng hợp (cảnh trượt ngang ghi bằng mp4v), nên mọi test là [chưa kiểm chứng trên video điện thoại thật]: tag rotation
không ghi được bằng OpenCV nên hướng xoay được tiêm bằng monkeypatch, timestamp VFR và tiêu cự thật chưa thử."""

import copy
import json
import math

import cv2
import numpy as np
import pytest

from pipeline import run as prun
from pipeline.common import adapters
from pipeline.common import config as cfgmod
from pipeline.common import io as pio
from pipeline.common.errors import E_MISSING_INPUT, E_TOO_FEW_KEYFRAMES, StageError
from pipeline.common.schema import read_keyframes_csv
from pipeline.keyframe import extract as kf
from pipeline.keyframe.orientation import rotation_for_video

W, H, HZ, SECONDS = 320, 240, 30.0, 6


def make_video(path, w=W, h=H, hz=HZ, seconds=SECONDS, px_per_frame=2.0):
    """Camera trượt ngang qua cảnh nhiều hình tương phản (ORB khớp được), như `make_moving_raw` ở test_keyframe_extract."""
    n = int(hz * seconds)
    rng = np.random.default_rng(0)
    big = np.full((h, w + int(px_per_frame * n) + 10), 128, np.uint8)
    for _ in range(900):
        x, y = int(rng.integers(0, big.shape[1])), int(rng.integers(0, h))
        c = int(rng.integers(0, 256))
        if rng.random() < 0.5:
            cv2.circle(big, (x, y), int(rng.integers(3, 14)), c, -1)
        else:
            cv2.rectangle(big, (x, y), (x + int(rng.integers(5, 25)), y + int(rng.integers(5, 25))), c, -1)
    big = cv2.GaussianBlur(big, (3, 3), 0)
    wr = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), hz, (w, h))
    assert wr.isOpened(), "OpenCV không ghi được mp4v"
    for i in range(n):
        x0 = int(i * px_per_frame)
        wr.write(cv2.cvtColor(big[:, x0:x0 + w], cv2.COLOR_GRAY2BGR))
    wr.release()
    return path


def cfg_with(**video):
    cfg = copy.deepcopy(cfgmod.load_config())
    cfg["keyframe"]["target_min"] = 3
    cfg["keyframe"]["blur"]["q_drop"] = 0.0          # nén mp4v làm V đổi: tách riêng khỏi phép thử hình học
    cfg["video"].update(video)
    return cfg


def layout_for(tmp_path):
    return pio.scene_layout(tmp_path / "scenes", "self_collected", "clip")


def test_rotation_va_intrinsics_khoi_tao():
    assert [rotation_for_video(d) for d in (0, 90, 180, 270, 360)] == ["none", "cw90", "rot180", "ccw90", "none"]
    with pytest.raises(ValueError):
        rotation_for_video(45)
    p = adapters.estimate_intrinsics(1920, 1080, 26.0)
    assert p["fx"] == p["fy"] == pytest.approx(26.0 * math.hypot(1920, 1080) / 43.27)
    assert p["fx"] == pytest.approx(1323.7, abs=0.5) and (p["cx"], p["cy"]) == (960.0, 540.0)
    with pytest.raises(ValueError):
        adapters.estimate_intrinsics(640, 480, 0)


def test_video_source_timestamp_va_doc_khung(tmp_path):
    path = make_video(tmp_path / "clip.mp4")
    with adapters.VideoSource(path) as v:
        ts = v.timestamps()
        assert len(ts) == int(HZ * SECONDS) and np.all(np.diff(ts) > 0) and not v.ts_from_meta
        assert np.diff(ts).mean() == pytest.approx(1 / HZ, rel=0.05) and v.fps_meta == pytest.approx(HZ) and v.rotation_deg == 0
        got = v.read_frames([0, 50, 50, 100])
    assert sorted(got) == [0, 50, 100] and got[0].shape == (H, W, 3)
    with pytest.raises(FileNotFoundError):
        adapters.VideoSource(tmp_path / "khong_co.mp4")


def test_extract_video_ghi_hop_dong_dau_ra(tmp_path):
    path = make_video(tmp_path / "clip.mp4")
    layout, logs = layout_for(tmp_path), []
    st = kf.extract_video_keyframes(path, layout, cfg_with(), source_info={"video_id": "clip"}, log=logs.append)
    rows = read_keyframes_csv(layout.metadata / "candidates.csv")
    assert st["n_candidates"] in (12, 13) and st["n_dense"] == len(rows) >= 3
    assert all(r["sky_direction"] == "video" and r["rot_applied"] == "none" and r["w"] == str(W) and r["h"] == str(H) for r in rows)
    assert cv2.imread(str(layout.candidates / "0000.jpg")).shape[:2] == (H, W) and (layout.candidates / f"{len(rows) - 1:04d}.jpg").is_file()
    cam = json.loads((layout.metadata / "camera.json").read_text(encoding="utf-8"))
    f = 26.0 * math.hypot(W, H) / 43.27
    assert cam["camera_model"] == "PINHOLE" and (cam["w"], cam["h"]) == (W, H) and cam["intrinsics_source"] == "estimated_from_focal35"
    assert cam["fx"] == pytest.approx(f) and cam["fy"] == pytest.approx(f) and (cam["cx"], cam["cy"]) == (W / 2, H / 2)
    src = json.loads((layout.raw / "source.json").read_text(encoding="utf-8"))
    assert src["video_id"] == "clip" and src["rotation_deg"] == 0 and src["video_size"] == [W, H] and src["stats"]["n_dense"] == len(rows)
    assert any("rotation 0°" in m for m in logs)


def test_extract_video_ha_do_phan_giai_va_nhan_intrinsics(tmp_path):
    path = make_video(tmp_path / "clip.mp4")
    layout = layout_for(tmp_path)
    kf.extract_video_keyframes(path, layout, cfg_with(long_edge=160), log=lambda m: None)
    assert cv2.imread(str(layout.candidates / "0000.jpg")).shape[:2] == (H // 2, W // 2)
    cam = json.loads((layout.metadata / "camera.json").read_text(encoding="utf-8"))
    f = 26.0 * math.hypot(W, H) / 43.27 / 2
    assert (cam["w"], cam["h"]) == (W // 2, H // 2) and cam["fx"] == pytest.approx(f) and (cam["cx"], cam["cy"]) == (W / 4, H / 4)


def test_extract_video_xoay_theo_tag_rotation(tmp_path, monkeypatch):
    class Rotated(adapters.VideoSource):             # OpenCV không ghi được tag rotation: tiêm 90° CW
        def __init__(self, p):
            super().__init__(p)
            self.rotation_deg = 90

    monkeypatch.setattr(adapters, "VideoSource", Rotated)
    path = make_video(tmp_path / "clip.mp4")
    layout = layout_for(tmp_path)
    kf.extract_video_keyframes(path, layout, cfg_with(), log=lambda m: None)
    row = read_keyframes_csv(layout.metadata / "candidates.csv")[0]
    assert row["rot_applied"] == "cw90" and (row["w"], row["h"]) == (str(H), str(W))        # 320×240 → 240×320
    assert cv2.imread(str(layout.candidates / "0000.jpg")).shape[:2] == (W, H)
    assert (float(row["cx"]), float(row["cy"])) == (H - H / 2, W / 2)                          # cx' = h − cy, cy' = cx


def test_extract_video_video_json_ghi_de_tieu_cu(tmp_path):
    path = make_video(tmp_path / "clip.mp4")
    (tmp_path / "video.json").write_text(json.dumps({"focal35_mm": 13.0}), encoding="utf-8")
    layout = layout_for(tmp_path)
    kf.extract_video_keyframes(path, layout, cfg_with(), log=lambda m: None)
    cam = json.loads((layout.metadata / "camera.json").read_text(encoding="utf-8"))
    assert cam["focal35_mm"] == 13.0 and cam["fx"] == pytest.approx(13.0 * math.hypot(W, H) / 43.27)


def test_extract_video_loi(tmp_path):
    layout = layout_for(tmp_path)
    with pytest.raises(StageError) as e:
        kf.extract_video_keyframes(tmp_path / "khong_co.mp4", layout, cfg_with(), log=lambda m: None)
    assert e.value.code == E_MISSING_INPUT
    bad = tmp_path / "hong.mp4"
    bad.write_bytes(b"khong phai video")
    with pytest.raises(StageError) as e2:
        kf.extract_video_keyframes(bad, layout, cfg_with(), log=lambda m: None)
    assert e2.value.code == E_MISSING_INPUT
    cfg = cfg_with()
    cfg["keyframe"]["target_min"] = 100
    with pytest.raises(StageError) as e3:
        kf.extract_video_keyframes(make_video(tmp_path / "clip.mp4"), layout, cfg, log=lambda m: None)
    assert e3.value.code == E_TOO_FEW_KEYFRAMES


def test_resolve_video_scene(tmp_path):
    cfg = cfgmod.load_config()
    d = tmp_path / cfg["video"]["source_dir"] / "abc"
    d.mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        prun.resolve_scene(tmp_path, "self_collected/abc", cfg)                    # chưa có video
    (d / "a.MOV").write_bytes(b"x")
    info = prun.resolve_scene(tmp_path, "self_collected/abc", cfg)                 # đuôi viết hoa vẫn nhận
    assert info["video_path"] == d / "a.MOV" and info["dataset"] == "self_collected" and info["layout"].root.name == "abc"
    (d / "b.mp4").write_bytes(b"x")
    with pytest.raises(FileNotFoundError):
        prun.resolve_video_scene(tmp_path, "self_collected/abc", cfg)              # hai video: không đoán
