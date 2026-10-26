"""Test wrapper tải ARKitScenes: phần không cần mạng (dựng đường dẫn, chặn thiếu --yes, chặn ổ thấp, resume, kiểm dung lượng).

Mọi hàm mạng (`head_size`, `fetch_mapping`, `run_curl`) được thay bằng bản giả; test không tải gì.
"""

import csv
import importlib.util
import threading
from pathlib import Path

import pytest

from pipeline.common import splits as sp

REPO = Path(__file__).resolve().parents[1]
GiB = 1024 ** 3


def _load():
    spec = importlib.util.spec_from_file_location("download_arkitscenes_under_test", REPO / "scripts" / "download_arkitscenes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def env(tmp_path, monkeypatch):
    mod = _load()
    root = tmp_path / "repo"
    raw = "data/raw/arkitscenes"
    rows = [
        {"video_id": "100", "visit_id": "10", "split": "train", "sky_direction": "Left", "source_dir": f"{raw}/Training/100", "seed": 42},
        {"video_id": "101", "visit_id": "11", "split": "train", "sky_direction": "Up", "source_dir": f"{raw}/Training/101", "seed": 42},
        {"video_id": "200", "visit_id": "20", "split": "val", "sky_direction": "Left", "source_dir": f"{raw}/Validation/200", "seed": 42},
        {"video_id": "201", "visit_id": "21", "split": "val", "sky_direction": "Down", "source_dir": f"{raw}/Validation/201", "seed": 42},
        {"video_id": "300", "visit_id": "30", "split": "heldout", "sky_direction": "Up", "source_dir": f"{raw}/Training/300", "seed": 42},
    ]
    splits_csv = root / "data" / "splits.csv"
    sp.write_splits(rows, splits_csv)
    sp.write_lock(splits_csv, 42)

    state = {"curl_calls": [], "active": 0, "max_active": 0, "mode": "ok", "flaky_fail_n": 2, "sleeps": []}
    monkeypatch.setattr(mod.time, "sleep", lambda s: state["sleeps"].append(s))   # không đợi thật giữa các lần thử
    sizes = {}

    def fake_head(url):
        return sizes.setdefault(url, 1000 + (sum(map(ord, url)) % 4000))

    def fake_mapping():
        return {"10": ["a1", "a2"], "20": ["b1"], "21": ["c1", "c2"], "30": ["h1"]}

    lock = threading.Lock()

    def fake_curl(url, part, expected):
        with lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
        try:
            existed = part.stat().st_size if part.exists() else 0
            state["curl_calls"].append((url, part.name, existed))
            if state["mode"] == "short":      # curl báo thành công nhưng thiếu byte
                part.write_bytes(b"x" * (expected - 7))
            elif state["mode"] == "fail":     # curl lỗi giữa chừng, để lại .part dở
                part.write_bytes(b"x" * (expected // 2))
                return 56
            elif state["mode"] == "flaky" and len(state["curl_calls"]) <= state["flaky_fail_n"]:
                with open(part, "ab") as f:   # lỗi mạng tạm thời: thêm 1/4 dung lượng rồi báo mã 56
                    f.write(b"x" * (expected // 4))
                return 56
            else:
                with open(part, "ab") as f:
                    f.write(b"x" * (expected - existed))
            return 0
        finally:
            with lock:
                state["active"] -= 1

    monkeypatch.setattr(mod, "head_size", fake_head)
    monkeypatch.setattr(mod, "fetch_mapping", fake_mapping)
    monkeypatch.setattr(mod, "run_curl", fake_curl)
    monkeypatch.setattr(mod, "free_bytes", lambda path: 500 * GiB)
    return mod, root, rows, state, sizes


def args(root, *extra):
    return ["--root", str(root), "--dev_scene", "100", "--log", str(root / "log.csv"), "--retry_wait", "0", *extra]


# ---------------------------------------------------------------- dựng đường dẫn

def test_build_items_paths_have_no_raw_level_and_no_extraction(env):
    mod, root, rows, _s, _z = env
    a = mod.build_items("A", rows, mod.fetch_mapping(), root, "100")
    assert [i.dst.relative_to(root).as_posix() for i in a] == [
        "data/raw/arkitscenes/Training/100/vga_wide.zip", "data/raw/arkitscenes/Training/100/vga_wide_intrinsics.zip"]
    assert a[0].url == f"{mod.BASE_URL}/raw/Training/100/vga_wide.zip"        # đúng quy ước URL của download_data.py
    assert all(i.dst.suffix == ".zip" for i in a)                               # chỉ zip, không thư mục giải nén


def test_faro_items_go_to_laser_folder_with_pose_for_every_ply(env):
    mod, root, rows, _s, _z = env
    b = mod.build_items("B", rows, mod.fetch_mapping(), root, "100")
    assert {i.dst.parent.relative_to(root).as_posix() for i in b} == {"data/raw/arkitscenes/laser_scanner_point_clouds/10"}
    plys = {i.dst.stem for i in b if i.kind == "ply"}
    poses = {i.dst.name[: -len("_pose.txt")] for i in b if i.kind == "pose"}
    assert plys == poses == {"a1", "a2"}
    assert b[0].url == f"{mod.BASE_URL}/raw/laser_scanner_point_clouds/10/a1.ply"


def test_batches_c_and_d_cover_validation_only_and_never_heldout(env):
    mod, root, rows, _s, _z = env
    c = mod.build_items("C", rows, mod.fetch_mapping(), root, "100")
    d = mod.build_items("D", rows, mod.fetch_mapping(), root, "100")
    assert {i.dst.parent.name for i in c} == {"200", "201"} and len(c) == 4
    assert {i.dst.parent.name for i in d} == {"20", "21"} and len(d) == 6
    everything = {p for i in c + d for p in i.dst.parts}
    assert not ({"300", "30", "h1.ply"} & everything)


def test_heldout_guard_raises(env):
    mod, root, rows, _s, _z = env
    forged = mod.Item("D", "u", root / "data/raw/arkitscenes/laser_scanner_point_clouds/30/h1.ply", "ply")
    with pytest.raises(sp.HeldoutError):
        mod.assert_no_heldout_items([forged], rows)
    forged2 = mod.Item("C", "u", root / "data/raw/arkitscenes/Training/300/vga_wide.zip", "zip")
    with pytest.raises(sp.HeldoutError):
        mod.assert_no_heldout_items([forged2], rows)


def test_dev_scene_must_be_train(env):
    mod, root, rows, _s, _z = env
    with pytest.raises(ValueError):
        mod.build_items("A", rows, {}, root, "200")      # scene val
    with pytest.raises(ValueError):
        mod.build_items("A", rows, {}, root, "9999")     # không có


def test_parse_batches():
    mod = _load()
    assert mod.parse_batches("all") == ["A", "B", "C", "D"]
    assert mod.parse_batches("d, a") == ["A", "D"]
    for bad in ("E", "", "A,Z"):
        with pytest.raises(ValueError):
            mod.parse_batches(bad)


# ---------------------------------------------------------------- an toàn: --yes, ổ trống, khoá

def test_refuses_without_yes_or_dry_run(env, capsys):
    mod, root, _r, state, _z = env
    assert mod.main(args(root, "--batch", "A")) == 2
    assert state["curl_calls"] == [] and not (root / "data" / "raw").exists()
    assert "TỪ CHỐI" in capsys.readouterr().out


def test_dry_run_prints_table_and_creates_nothing(env, capsys):
    mod, root, _r, state, _z = env
    assert mod.main(args(root, "--batch", "all", "--dry-run")) == 0
    out = capsys.readouterr().out
    for b in "ABCD":
        assert f"\n {b} " in out
    assert "khớp" in out or "LỆCH" in out
    assert state["curl_calls"] == [] and not (root / "data" / "raw").exists() and not (root / "log.csv").exists()


def test_dry_run_flags_low_disk_and_returns_2(env, monkeypatch, capsys):
    mod, root, _r, state, _z = env
    monkeypatch.setattr(mod, "free_bytes", lambda path: 5000)               # chỉ vài KB trống
    assert mod.main(args(root, "--batch", "all", "--dry-run")) == 2
    assert "DỪNG" in capsys.readouterr().out and state["curl_calls"] == []


def test_real_run_blocked_when_free_space_too_low(env, monkeypatch, capsys):
    mod, root, _r, state, _z = env
    monkeypatch.setattr(mod, "free_bytes", lambda path: 10 * GiB)           # dư 10 GiB dưới ngưỡng 15 GiB
    assert mod.main(args(root, "--batch", "A", "--yes", "--min_free_gib", "15")) == 3
    assert state["curl_calls"] == []


def test_real_run_stops_when_leftover_below_threshold_even_if_batch_fits(env, monkeypatch):
    mod, root, _r, state, sizes = env
    # trống 15 GiB + 1 KB: đợt A (vài KB) làm dư rơi xuống dưới 15 GiB
    monkeypatch.setattr(mod, "free_bytes", lambda path: 15 * GiB + 1000)
    assert mod.main(args(root, "--batch", "A", "--yes")) == 3 and state["curl_calls"] == []


def test_tampered_splits_is_refused(env):
    mod, root, _r, state, _z = env
    p = root / "data" / "splits.csv"
    p.write_text(p.read_text(encoding="utf-8").replace(",train,", ",val,", 1), encoding="utf-8", newline="\n")
    assert mod.main(args(root, "--batch", "A", "--dry-run")) == 1 and state["curl_calls"] == []


# ---------------------------------------------------------------- tải, resume, kiểm dung lượng

def test_download_ok_verifies_size_renames_and_logs(env):
    mod, root, _r, state, sizes = env
    assert mod.main(args(root, "--batch", "A", "--yes")) == 0
    d = root / "data/raw/arkitscenes/Training/100"
    for name in ("vga_wide.zip", "vga_wide_intrinsics.zip"):
        url = f"{mod.BASE_URL}/raw/Training/100/{name}"
        assert (d / name).stat().st_size == sizes[url]
        assert not (d / (name + ".part")).exists()
    with open(root / "log.csv", encoding="utf-8") as f:
        log = list(csv.DictReader(f))
    assert [r["status"] for r in log] == ["downloaded", "downloaded"]
    assert all(r["actual_bytes"] == r["expected_bytes"] for r in log)


def test_resume_continues_existing_part_and_uses_resume_flag(env):
    mod, root, _r, state, sizes = env
    d = root / "data/raw/arkitscenes/Training/100"
    d.mkdir(parents=True)
    url = f"{mod.BASE_URL}/raw/Training/100/vga_wide.zip"
    size = mod.head_size(url)
    (d / "vga_wide.zip.part").write_bytes(b"x" * (size // 3))
    assert mod.main(args(root, "--batch", "A", "--yes")) == 0
    assert (d / "vga_wide.zip").stat().st_size == size
    assert state["curl_calls"][0][2] == size // 3                           # curl được gọi khi đã có .part dở
    cmd = mod.build_curl_cmd(url, d / "vga_wide.zip.part")
    assert cmd[cmd.index("-C") + 1] == "-"                                   # lệnh curl thật có resume
    with open(root / "log.csv", encoding="utf-8") as f:
        assert next(csv.DictReader(f))["status"] == "resumed"


def test_part_already_complete_skips_curl_and_just_renames(env):
    mod, root, _r, state, _z = env
    d = root / "data/raw/arkitscenes/Training/100"
    d.mkdir(parents=True)
    for name in ("vga_wide.zip", "vga_wide_intrinsics.zip"):
        size = mod.head_size(f"{mod.BASE_URL}/raw/Training/100/{name}")
        (d / (name + ".part")).write_bytes(b"x" * size)
    assert mod.main(args(root, "--batch", "A", "--yes")) == 0
    assert state["curl_calls"] == [] and (d / "vga_wide.zip").exists()


def test_size_mismatch_keeps_part_and_fails(env):
    mod, root, _r, state, _z = env
    state["mode"] = "short"
    assert mod.main(args(root, "--batch", "A", "--yes", "--max_attempts", "3")) == 1
    d = root / "data/raw/arkitscenes/Training/100"
    assert not (d / "vga_wide.zip").exists() and (d / "vga_wide.zip.part").exists()
    with open(root / "log.csv", encoding="utf-8") as f:
        assert next(csv.DictReader(f))["status"] == "failed"
    assert len(state["curl_calls"]) == 3                                     # thử đủ 3 lần rồi dừng; không tải file kế tiếp


def test_curl_failure_keeps_partial_for_resume(env):
    mod, root, _r, state, _z = env
    state["mode"] = "fail"
    assert mod.main(args(root, "--batch", "A", "--yes")) == 1
    assert (root / "data/raw/arkitscenes/Training/100/vga_wide.zip.part").exists()


def test_existing_correct_file_skipped_and_wrong_size_not_overwritten(env):
    mod, root, _r, state, _z = env
    d = root / "data/raw/arkitscenes/Training/100"
    d.mkdir(parents=True)
    good = mod.head_size(f"{mod.BASE_URL}/raw/Training/100/vga_wide.zip")
    (d / "vga_wide.zip").write_bytes(b"y" * good)
    assert mod.main(args(root, "--batch", "A", "--yes")) == 0
    assert [c[1] for c in state["curl_calls"]] == ["vga_wide_intrinsics.zip.part"]   # file đúng dung lượng được bỏ qua

    bad = d / "vga_wide_intrinsics.zip"
    bad.write_bytes(b"z" * 3)
    state["curl_calls"].clear()
    assert mod.main(args(root, "--batch", "A", "--yes")) == 1
    assert bad.read_bytes() == b"zzz" and state["curl_calls"] == []                 # không ghi đè, không xoá


def test_downloads_are_sequential_and_in_order(env):
    mod, root, _r, state, _z = env
    assert mod.main(args(root, "--batch", "B,C", "--yes")) == 0
    assert state["max_active"] == 1                                          # không bao giờ hai curl cùng lúc
    expected_order = [i.url for b in ("B", "C") for i in mod.build_items(b, _r, mod.fetch_mapping(), root, "100")]
    assert [c[0] for c in state["curl_calls"]] == expected_order


def test_matches_reported_tolerance():
    mod = _load()
    assert mod.matches_reported("A", int(0.69 * GiB))
    assert mod.matches_reported("D", int(46.21 * GiB * 1.005))
    assert not mod.matches_reported("D", int(40 * GiB))


# ---------------------------------------------------------------- thử lại sau lỗi mạng (sự cố 18/10: curl mã 56 ở 36%)

def test_curl_cmd_retries_all_errors_and_drops_stalled_connections():
    mod = _load()
    cmd = mod.build_curl_cmd("https://x/y.ply", Path("y.ply.part"))
    assert "--retry-all-errors" in cmd                                       # mã 56 mặc định không được curl thử lại
    assert cmd[cmd.index("--speed-limit") + 1] == str(mod.STALL_SPEED_BYTES)
    assert cmd[cmd.index("--speed-time") + 1] == str(mod.STALL_SECONDS)
    assert cmd[cmd.index("-C") + 1] == "-"                                   # vẫn resume


def test_transient_failures_are_retried_and_resume_from_growing_part(env):
    mod, root, _r, state, _z = env
    state["mode"], state["flaky_fail_n"] = "flaky", 2                        # hai lần đầu lỗi mã 56, lần ba xong
    assert mod.main(args(root, "--batch", "A", "--yes", "--retry_wait", "7")) == 0
    d = root / "data/raw/arkitscenes/Training/100"
    url = f"{mod.BASE_URL}/raw/Training/100/vga_wide.zip"
    size = mod.head_size(url)
    assert (d / "vga_wide.zip").stat().st_size == size and not (d / "vga_wide.zip.part").exists()
    first = [c for c in state["curl_calls"] if c[0] == url]
    assert len(first) == 3 and first[0][2] == 0 and first[1][2] == size // 4 and first[2][2] == 2 * (size // 4)  # offset tăng dần
    assert state["sleeps"][:2] == [7.0, 7.0]                                 # đợi --retry_wait giữa các lần thử
    with open(root / "log.csv", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert row["status"] == "resumed" and "3 lần" in row["note"]


def test_gives_up_after_max_attempts_keeps_part_and_does_not_start_next_file(env):
    mod, root, _r, state, _z = env
    state["mode"] = "fail"
    assert mod.main(args(root, "--batch", "A", "--yes", "--max_attempts", "3")) == 1
    d = root / "data/raw/arkitscenes/Training/100"
    assert len(state["curl_calls"]) == 3 and (d / "vga_wide.zip.part").exists()
    assert not (d / "vga_wide.zip").exists() and not (d / "vga_wide_intrinsics.zip.part").exists()
    with open(root / "log.csv", encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert row["status"] == "failed" and "3 lần" in row["note"] and "56" in row["note"]


def test_single_attempt_means_no_retry(env):
    mod, root, _r, state, _z = env
    state["mode"] = "fail"
    assert mod.main(args(root, "--batch", "A", "--yes", "--max_attempts", "1")) == 1
    assert len(state["curl_calls"]) == 1 and state["sleeps"] == []


def test_oversized_part_is_a_data_error_not_retried(env):
    mod, root, _r, state, _z = env
    d = root / "data/raw/arkitscenes/Training/100"
    d.mkdir(parents=True)
    size = mod.head_size(f"{mod.BASE_URL}/raw/Training/100/vga_wide.zip")
    (d / "vga_wide.zip.part").write_bytes(b"x" * (size + 5))
    assert mod.main(args(root, "--batch", "A", "--yes")) == 1
    assert state["curl_calls"] == []                                         # bị chặn từ bước đo, không chạy curl
    assert (d / "vga_wide.zip.part").stat().st_size == size + 5              # không xoá, không sửa
