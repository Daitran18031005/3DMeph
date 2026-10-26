"""Test chia tập theo venue, khoá held-out và hàm chặn tham số (kế hoạch §4.0b, quyết định Q15, Q17)."""

import importlib.util
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from pipeline.common import splits as sp
from pipeline.common.quality import compute_g_ref, compute_v_ref

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "data" / "raw" / "arkitscenes"
needs_data = pytest.mark.skipif(not (ROOT / "metadata.csv").is_file(), reason="chưa có data/raw/arkitscenes")


def _load_script():
    spec = importlib.util.spec_from_file_location("select_scenes_under_test", REPO / "scripts" / "select_scenes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _synthetic():
    scenes = []
    n = 0
    for visit in range(100, 112):             # 12 venue Training; 103 và 107 có 2 scene
        for _ in range(2 if visit in (103, 107) else 1):
            n += 1
            scenes.append({"video_id": str(1000 + n), "visit_id": str(visit), "fold": "Training"})
    for visit in (200, 201, 202):
        n += 1
        scenes.append({"video_id": str(1000 + n), "visit_id": str(visit), "fold": "Validation"})
    return scenes


def _venues(scenes, split_of):
    by = defaultdict(set)
    for s in scenes:
        by[s["visit_id"]].add(split_of[s["video_id"]])
    return by


# ---------------------------------------------------------------- logic chọn (dữ liệu tổng hợp)

def test_synthetic_invariants_and_determinism():
    scenes = _synthetic()
    a = sp.select_splits(scenes, seed=42, n_heldout=5, dev_scene="1001")
    b = sp.select_splits(scenes, seed=42, n_heldout=5, dev_scene="1001")
    assert a == b                                              # chạy hai lần cho cùng kết quả
    c = Counter(a.values())
    assert c["heldout"] == 5 and c["val"] == 3 and c["train"] == len(scenes) - 8
    assert all(len(v) == 1 for v in _venues(scenes, a).values())  # không venue nào ở hai tập
    assert a["1001"] == "train"                                # scene dev luôn ở train
    assert all(a[s["video_id"]] == "val" for s in scenes if s["fold"] == "Validation")


def test_seed_changes_heldout_but_not_val():
    scenes = _synthetic()
    held = {seed: {v for v, s in sp.select_splits(scenes, seed=seed, dev_scene="1001").items() if s == "heldout"}
            for seed in range(8)}
    assert len({frozenset(h) for h in held.values()}) > 1      # seed khác cho held-out khác


def test_dev_venue_never_in_heldout_for_any_seed():
    scenes = _synthetic()
    dev_venue_ids = {s["video_id"] for s in scenes if s["visit_id"] == "100"}
    for seed in range(30):
        out = sp.select_splits(scenes, seed=seed, dev_scene="1001")
        assert all(out[v] == "train" for v in dev_venue_ids)


def test_two_scene_venues_stay_whole_for_any_seed():
    scenes = _synthetic()
    for seed in range(30):
        out = sp.select_splits(scenes, seed=seed, dev_scene="1001")
        for venue in ("103", "107"):
            assert len({out[s["video_id"]] for s in scenes if s["visit_id"] == venue}) == 1


def test_impossible_heldout_count_raises():
    scenes = [{"video_id": str(i), "visit_id": str(10 + i // 2), "fold": "Training"} for i in range(8)]  # toàn venue 2 scene
    with pytest.raises(ValueError):
        sp.select_splits(scenes, seed=1, n_heldout=5)          # 2+2 = 4, thiếu 1 mà venue nào cũng có 2 scene


def test_venue_spanning_two_folds_raises():
    scenes = [{"video_id": "1", "visit_id": "5", "fold": "Training"}, {"video_id": "2", "visit_id": "5", "fold": "Validation"}]
    with pytest.raises(ValueError):
        sp.select_splits(scenes, n_heldout=1)


def test_dev_scene_must_exist_and_be_training():
    scenes = _synthetic()
    with pytest.raises(ValueError):
        sp.select_splits(scenes, dev_scene="9999")
    with pytest.raises(ValueError):
        sp.select_splits(scenes, dev_scene="1015")             # scene Validation (id 1015–1017)


# ---------------------------------------------------------------- dữ liệu thật

@needs_data
def test_real_data_split_is_29_6_5_and_clean():
    ss = _load_script()
    scenes, rejected = ss.scan(ROOT)
    assert len(scenes) == 40 and rejected == []                # 34 Training + 6 Validation, không scene nào bị loại
    out = sp.select_splits(scenes, seed=42, n_heldout=5, dev_scene="42444738")
    assert Counter(out.values()) == {"train": 29, "val": 6, "heldout": 5}
    visit_of = {s["video_id"]: s["visit_id"] for s in scenes}
    assert all(len(v) == 1 for v in _venues(scenes, out).values())            # 0 venue ở 2 tập
    assert out["42444738"] == "train"
    for pair in (("47204780", "47204786"), ("47331625", "47331627")):         # venue 472473 và 466899
        assert visit_of[pair[0]] == visit_of[pair[1]] and len({out[p] for p in pair}) == 1
    validation_ids = {v for v, f in ss.list_scene_dirs(ROOT) if f == "Validation"}
    assert {v for v, s in out.items() if s == "val"} == validation_ids
    assert out == sp.select_splits(scenes, seed=42, n_heldout=5, dev_scene="42444738")  # chạy hai lần: cùng held-out


@needs_data
def test_real_data_scan_matches_known_facts():
    ss = _load_script()
    scenes, _ = ss.scan(ROOT)
    assert len({s["visit_id"] for s in scenes}) == 38
    assert Counter(s["sky_direction"] for s in scenes) == {"Left": 27, "Up": 8, "Down": 5}


@needs_data
def test_script_is_idempotent_and_refuses_to_change_locked_split(tmp_path):
    ss = _load_script()
    out = tmp_path / "splits.csv"
    base = ["--arkitscenes_root", str(ROOT), "--out", str(out), "--rejected", str(tmp_path / "rejected.csv"),
            "--selected_csv", str(tmp_path / "khong_co.csv")]
    assert ss.main(base) == 0
    first = out.read_bytes()
    assert sp.lock_path_for(out).is_file() and (tmp_path / "rejected.csv").is_file()
    assert ss.main(base) == 0 and out.read_bytes() == first       # chạy lại: trùng, không ghi đè
    assert ss.main(base + ["--seed", "7"]) == 1                   # held-out khác bản đã khoá: từ chối
    assert out.read_bytes() == first
    # Sửa tay splits.csv sau khi khoá: bị phát hiện
    text = out.read_text(encoding="utf-8").replace(",train,", ",heldout,", 1)
    out.write_text(text, encoding="utf-8", newline="\n")
    assert ss.main(base) == 1


@needs_data
def test_script_dry_run_writes_nothing(tmp_path):
    ss = _load_script()
    out = tmp_path / "splits.csv"
    assert ss.main(["--arkitscenes_root", str(ROOT), "--out", str(out), "--dry-run"]) == 0
    assert not out.exists()


# ---------------------------------------------------------------- khoá và hash

def _rows():
    return [{"video_id": "1", "visit_id": "10", "split": "train", "sky_direction": "Left", "source_dir": "x", "seed": 42},
            {"video_id": "2", "visit_id": "11", "split": "val", "sky_direction": "Up", "source_dir": "y", "seed": 42},
            {"video_id": "3", "visit_id": "12", "split": "heldout", "sky_direction": "Down", "source_dir": "z", "seed": 42}]


def test_lock_detects_edit_and_ignores_line_endings(tmp_path):
    f = tmp_path / "splits.csv"
    sp.write_splits(_rows(), f)
    sp.write_lock(f, 42)
    assert sp.load_splits(f) == {"1": "train", "2": "val", "3": "heldout"}
    f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))         # git autocrlf trên Windows
    assert sp.load_splits(f)["3"] == "heldout"
    f.write_text(f.read_text(encoding="utf-8").replace("heldout", "train"), encoding="utf-8", newline="\n")
    with pytest.raises(sp.LockError):
        sp.load_splits(f)
    assert sp.load_splits(f, verify=False)["3"] == "train"       # verify=False chỉ để gỡ lỗi


def test_missing_lock_is_an_error(tmp_path):
    f = tmp_path / "splits.csv"
    sp.write_splits(_rows(), f)
    with pytest.raises(sp.LockError):
        sp.load_splits(f)


# ---------------------------------------------------------------- hàm V_ref, G_ref chặn held-out

SPLITS = {"11": "val", "12": "val", "13": "val", "20": "train", "30": "heldout"}


def test_v_ref_and_g_ref_use_validation_scenes_only():
    assert compute_v_ref({"11": 400.0, "12": 600.0, "13": 800.0}, SPLITS) == pytest.approx(600.0)
    assert compute_g_ref({"11": 10.0, "12": 20.0}, SPLITS) == pytest.approx(15.0)   # trung vị 2 số = trung bình


def test_v_ref_and_g_ref_raise_on_heldout():
    for fn in (compute_v_ref, compute_g_ref):
        with pytest.raises(sp.HeldoutError):
            fn({"11": 1.0, "30": 2.0}, SPLITS)                    # lẫn một scene held-out
        with pytest.raises(sp.HeldoutError):
            fn({"30": 2.0}, SPLITS)


def test_v_ref_rejects_train_unknown_and_empty():
    with pytest.raises(ValueError):
        compute_v_ref({"20": 1.0}, SPLITS)                        # train: chỉ val được phép
    with pytest.raises(ValueError):
        compute_v_ref({"999": 1.0}, SPLITS)                       # không có trong splits.csv
    with pytest.raises(ValueError):
        compute_g_ref({}, SPLITS)


def test_heldout_error_is_a_value_error_and_listing():
    assert issubclass(sp.HeldoutError, ValueError)
    assert sp.heldout_ids(SPLITS) == ["30"]


@needs_data
def test_guard_on_real_locked_split(tmp_path):
    ss = _load_script()
    f = tmp_path / "splits.csv"
    ss.main(["--arkitscenes_root", str(ROOT), "--out", str(f), "--rejected", str(tmp_path / "r.csv"),
             "--selected_csv", str(tmp_path / "none.csv")])
    splits = sp.load_splits(f)
    held = sp.heldout_ids(splits)
    assert len(held) == 5
    with pytest.raises(sp.HeldoutError):
        compute_v_ref({held[0]: 500.0}, splits)
    val_ids = sorted(v for v, s in splits.items() if s == "val")
    assert compute_v_ref({v: 500.0 + i for i, v in enumerate(val_ids)}, splits) == pytest.approx(502.5)
    shutil.rmtree(tmp_path, ignore_errors=True)
