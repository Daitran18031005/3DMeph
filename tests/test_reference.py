"""Test đo V_ref, G_ref (kế hoạch §4.1): lấy mẫu mỗi 10 khung, trung vị qua scene, chặn held-out trước khi đọc ảnh."""

import importlib.util
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from pipeline.common import config as cfgmod
from pipeline.common import reference as ref
from pipeline.common import splits as sp
from pipeline.common.quality import laplacian_variance, mean_window_gradient

REPO = Path(__file__).resolve().parents[1]


def _png(img):
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def _noise(seed, size=(48, 64)):
    return (np.random.default_rng(seed).uniform(size=size) * 255).astype(np.uint8)


def _flat(size=(48, 64), value=120):
    return np.full(size, value, dtype=np.uint8)


def make_zip(path, images, prefix="vga_wide"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(prefix + "/", b"")                                      # mục thư mục như zip ARKitScenes
        for i, img in enumerate(images):
            zf.writestr(f"{prefix}/1_{1000 + i:05d}.000.png", _png(img))


# ---------------------------------------------------------------- lấy mẫu và thống kê

def test_scene_stats_samples_every_tenth_frame(tmp_path):
    # 25 khung: các khung 0, 10, 20 là nhiễu (chi tiết nhiều), còn lại phẳng. Mẫu mỗi 10 khung chỉ thấy 3 khung nhiễu.
    imgs = [_noise(i) if i in (0, 10, 20) else _flat() for i in range(25)]
    make_zip(tmp_path / "a.zip", imgs)
    s = ref.scene_stats(tmp_path / "a.zip", stride=10)
    assert s["n_frames"] == 25 and s["n_sampled"] == 3
    expected = np.mean([laplacian_variance(imgs[i]) for i in (0, 10, 20)])
    assert s["blur_mean"] == pytest.approx(expected)
    assert s["grad_mean"] == pytest.approx(np.mean([mean_window_gradient(imgs[i]) for i in (0, 10, 20)]))
    # stride 1 đọc mọi khung → trung bình thấp hơn nhiều vì 22/25 khung phẳng
    assert ref.scene_stats(tmp_path / "a.zip", stride=1)["blur_mean"] < s["blur_mean"] / 3


def test_scene_stats_flat_scene_has_zero_blur_and_gradient(tmp_path):
    make_zip(tmp_path / "f.zip", [_flat() for _ in range(12)])
    s = ref.scene_stats(tmp_path / "f.zip")
    assert s["blur_mean"] == 0.0 and s["grad_mean"] == 0.0 and s["n_sampled"] == 2


def test_scene_stats_errors(tmp_path):
    with pytest.raises(ValueError):
        ref.scene_stats(tmp_path / "x.zip", stride=0)
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("vga_wide/readme.txt", b"khong co anh")
    with pytest.raises(ValueError):
        ref.scene_stats(empty)
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("vga_wide/1_00001.000.png", b"khong phai png")
    with pytest.raises(ValueError):
        ref.scene_stats(bad)


def test_mean_window_gradient_flat_zero_and_texture_positive():
    assert mean_window_gradient(_flat()) == 0.0
    assert mean_window_gradient(_noise(1)) > 100
    ramp = np.tile(np.arange(64, dtype=np.uint8) * 4, (48, 1))             # dốc đều theo x: gradient hằng
    assert mean_window_gradient(ramp) > 0


# ---------------------------------------------------------------- đo qua splits.csv

@pytest.fixture()
def world(tmp_path):
    rows = [
        {"video_id": "10", "visit_id": "1", "split": "train", "sky_direction": "Left", "source_dir": "data/raw/a/Training/10", "seed": 42},
        {"video_id": "20", "visit_id": "2", "split": "val", "sky_direction": "Left", "source_dir": "data/raw/a/Validation/20", "seed": 42},
        {"video_id": "21", "visit_id": "3", "split": "val", "sky_direction": "Up", "source_dir": "data/raw/a/Validation/21", "seed": 42},
        {"video_id": "22", "visit_id": "4", "split": "val", "sky_direction": "Down", "source_dir": "data/raw/a/Validation/22", "seed": 42},
        {"video_id": "30", "visit_id": "5", "split": "heldout", "sky_direction": "Up", "source_dir": "data/raw/a/Training/30", "seed": 42},
    ]
    splits_csv = tmp_path / "data" / "splits.csv"
    sp.write_splits(rows, splits_csv)
    sp.write_lock(splits_csv, 42)
    for vid, seeds in (("20", [1, 2]), ("21", [3, 4]), ("22", [5, 6])):
        make_zip(tmp_path / f"data/raw/a/Validation/{vid}/vga_wide.zip", [_noise(s) for s in seeds] + [_flat()] * 9)
    make_zip(tmp_path / "data/raw/a/Training/10/vga_wide.zip", [_noise(9)])
    return tmp_path, splits_csv


def test_measure_reference_is_median_of_scene_means(world):
    root, splits_csv = world
    res = ref.measure_reference(root, splits_csv, stride=10)
    assert res["n_scenes"] == 3 and sorted(res["per_scene"]) == ["20", "21", "22"] and res["stride"] == 10
    means = [res["per_scene"][v]["blur_mean"] for v in ("20", "21", "22")]
    assert res["v_ref"] == pytest.approx(float(np.median(means)))
    gm = [res["per_scene"][v]["grad_mean"] for v in ("20", "21", "22")]
    assert res["g_ref"] == pytest.approx(float(np.median(gm)))
    assert res["per_scene"]["20"]["visit_id"] == "2"


def test_heldout_is_refused_before_any_image_is_read(world):
    root, splits_csv = world            # scene held-out 30 KHÔNG có zip nào: nếu đọc ảnh sẽ báo FileNotFoundError
    with pytest.raises(sp.HeldoutError):
        ref.measure_reference(root, splits_csv, scene_ids=["20", "30"])
    with pytest.raises(sp.HeldoutError):
        ref.measure_reference(root, splits_csv, scene_ids=["30"])


def test_train_and_unknown_scenes_are_refused(world):
    root, splits_csv = world
    with pytest.raises(ValueError):
        ref.measure_reference(root, splits_csv, scene_ids=["10"])      # train: chỉ val được phép
    with pytest.raises(ValueError):
        ref.measure_reference(root, splits_csv, scene_ids=["999"])


def test_tampered_splits_is_refused(world):
    root, splits_csv = world
    splits_csv.write_text(splits_csv.read_text(encoding="utf-8").replace(",heldout,", ",val,"), encoding="utf-8", newline="\n")
    with pytest.raises(sp.LockError):
        ref.measure_reference(root, splits_csv)


# ---------------------------------------------------------------- script: ghi config

def _script():
    spec = importlib.util.spec_from_file_location("measure_reference_under_test", REPO / "scripts" / "measure_reference.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_script_dry_run_does_not_write_config_and_write_config_fills_null_once(world, tmp_path, capsys):
    mod = _script()
    root, splits_csv = world
    cfg = tmp_path / "default.yaml"
    cfg.write_text((REPO / "configs" / "default.yaml").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    # Ghi đè khối đã đo (nếu repo đã đo) về dạng null để test độc lập với trạng thái repo
    text = cfg.read_text(encoding="utf-8")
    import re
    text = re.sub(r"  v_ref:.*?(?=\nvggt:|\ncolmap:|\nalign:)", "  v_ref:\n    vga: null\n  g_ref:\n    vga: null\n", text, flags=re.S) \
        if not mod.UNMEASURED.search(text) else text
    cfg.write_text(text, encoding="utf-8", newline="\n")
    base = ["--root", str(root), "--splits", str(splits_csv), "--config", str(cfg), "--eda_csv", str(tmp_path / "none.csv"),
            "--date", "2026-10-18"]
    assert mod.main(base) == 0
    assert cfgmod.get(cfgmod.load_config(cfg), "quality.v_ref.vga") is None          # chỉ đo, chưa ghi
    assert mod.main(base + ["--write-config"]) == 0
    c = cfgmod.load_config(cfg)
    assert cfgmod.get(c, "quality.v_ref.vga") > 0 and cfgmod.get(c, "quality.g_ref.vga") > 0
    for k in ("v_ref", "g_ref"):
        assert cfgmod.get(c, f"quality.{k}.measured_on") == "validation"
        assert cfgmod.get(c, f"quality.{k}.n_scenes") == 3
        assert cfgmod.get(c, f"quality.{k}.date") == "2026-10-18"
        assert cfgmod.get(c, f"quality.{k}.stride") == 10
    assert mod.main(base + ["--write-config"]) == 1                                  # không ghi đè số đã khoá
    assert "không còn ở dạng" in capsys.readouterr().out


def test_script_refuses_heldout_via_locked_splits(world, tmp_path):
    mod = _script()
    root, splits_csv = world
    splits_csv.write_text(splits_csv.read_text(encoding="utf-8").replace(",heldout,", ",val,"), encoding="utf-8", newline="\n")
    assert mod.main(["--root", str(root), "--splits", str(splits_csv), "--eda_csv", str(tmp_path / "x.csv")]) == 1


# ---------------------------------------------------------------- cấu hình thật của repo

def test_repo_config_reference_values_if_measured():
    cfg = cfgmod.load_config()
    v = cfgmod.get(cfg, "quality.v_ref.vga")
    if v is None:
        pytest.skip("V_ref chưa đo")
    for k in ("v_ref", "g_ref"):
        assert cfgmod.get(cfg, f"quality.{k}.vga") > 0
        assert cfgmod.get(cfg, f"quality.{k}.measured_on") == "validation"
        assert cfgmod.get(cfg, f"quality.{k}.stride") == 10
    assert v != 581.0 and v != 635.3                                          # không phải số cũ của đề cương hay số tạm
    splits_csv = REPO / "data" / "splits.csv"
    if splits_csv.is_file():
        n_val = sum(1 for s in sp.load_splits(splits_csv).values() if s == "val")
        assert cfgmod.get(cfg, "quality.v_ref.n_scenes") == n_val == 6
