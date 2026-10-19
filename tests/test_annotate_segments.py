"""Test scripts/annotate_segments.py: luật kiểm, ghi measurements.csv / scale_anchor.json, nạp JSON, vòng chấm (bản giả), bảo vệ held-out.

Không mở cửa sổ Open3D: `pick` và `ask` được thay bằng bản giả.
"""

import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name + "_under_test", REPO / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


an = _load("annotate_segments")
SNAP = 0.02


def seg(i, role="test", a=(0, 0, 0), b=(1, 0, 0), typ="main_dimension", **kw):
    if role == "anchor":
        kw.setdefault("confirmed_not_glass", True)
    return an.make_segment(f"S{i:02d}", role, typ, a, b, label=f"đoạn {i}", **kw)


def good_segments(n_tests=12):
    """1 mốc 1,5 m và n đoạn test, mọi đầu mút cách nhau > 2 cm."""
    segs = [seg(1, "anchor", (0, 0, 0), (1.5, 0, 0))]
    for k in range(n_tests):
        y = 0.5 + k * 0.3
        segs.append(seg(2 + k, "test", (0, y, 0), (0.8 + 0.1 * k, y, 0)))
    return segs


# ---------------------------------------------------------------------------
# Luật kiểm
# ---------------------------------------------------------------------------


def test_bo_doan_hop_le_khong_loi():
    errors, warns = an.validate_segments(good_segments(12), SNAP)
    assert errors == [] and warns == []


def test_chieu_dai_theo_cong_thuc_30():
    assert an.segment_length((0.52, 0.75, 1.20), (1.90, 0.75, 1.20)) == pytest.approx(1.38)
    assert an.make_segment("S01", "test", "x", (0, 0, 0), (3, 4, 0))["length_m"] == 5.0


@pytest.mark.parametrize("mutate,expected", [
    (lambda s: s[1:], "cần đúng 1 đoạn mốc"),                                          # không có mốc
    (lambda s: s + [seg(90, "anchor", (5, 5, 0), (6.5, 5, 0))], "cần đúng 1 đoạn mốc"),   # hai mốc
    (lambda s: [seg(1, "anchor", (0, 0, 0), (0.8, 0, 0))] + s[1:], "ngoài 1.0–2.0 m"),
    (lambda s: [seg(1, "anchor", (0, 0, 0), (2.5, 0, 0))] + s[1:], "ngoài 1.0–2.0 m"),
    (lambda s: [seg(1, "anchor", (0, 0, 0), (1.5, 0, 0), confirmed_not_glass=False)] + s[1:], "chưa xác nhận mốc"),
    (lambda s: s[:-1], "cần ≥ 12 đoạn test"),                                          # chỉ 11 test
    (lambda s: s + [seg(2, "test", (9, 9, 0), (9, 10, 0))], "id trùng"),
    (lambda s: s + [seg(91, "test", (7, 7, 0), (7, 7, 0))], "hai đầu mút trùng nhau"),
    (lambda s: s + [seg(92, "test", (0, 0, 0), (7, 8, 0))], "trùng đầu mút"),          # trùng điểm của mốc
    (lambda s: s + [seg(93, "test", (0.01, 0, 0), (7, 9, 0))], "bán kính snap"),       # cách đầu mút mốc 1 cm
    (lambda s: s + [seg(94, "other", (7, 7, 0), (8, 7, 0))], "role"),
])
def test_moi_luat_mot_ca_loi(mutate, expected):
    errors, _ = an.validate_segments(mutate(good_segments(12)), SNAP)
    assert any(expected in e for e in errors), errors


def test_loi_thieu_type_va_length_khong_khop():
    s = good_segments(12)
    s[3]["type"] = " "
    s[4]["length_m"] = 9.9999
    errors, _ = an.validate_segments(s, SNAP)
    assert any("thiếu type" in e for e in errors) and any("không khớp toạ độ" in e for e in errors)


def test_canh_bao_khong_chan():
    s = good_segments(21)                                                 # 21 test > 20
    s.append(seg(95, "test", (0.0, 0.5, 0.015), (7, 7, 1)))               # đầu mút gần đầu mút test (S02.a), test-test: chỉ cảnh báo
    s.append(seg(96, "test", (3, 3, 3), (3.05, 3, 3)))                    # đoạn 5 cm
    errors, warns = an.validate_segments(s, SNAP)
    assert not any("S95" in e for e in errors)
    assert any("nhiều hơn 20" in w for w in warns)
    assert any("S95" in w and "bán kính snap" in w for w in warns)
    assert any("S96" in w and "chỉ dài" in w for w in warns)


# ---------------------------------------------------------------------------
# Ghi file
# ---------------------------------------------------------------------------


def make_paths(tmp_path):
    gt = tmp_path / "ground_truth"
    paths = an.Paths(gt)
    paths.faro.mkdir(parents=True)
    return paths


def make_session(segments, sha="abc"):
    sess = an.new_session("arkitscenes/42444738", sha, 0.01)
    sess["segments"] = segments
    return sess


def test_finalize_ghi_csv_va_anchor(tmp_path):
    paths = make_paths(tmp_path)
    sess = make_session(good_segments(12))
    res = an.finalize(paths, sess, SNAP)
    with open(paths.csv, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        assert rd.fieldnames == ["id", "type", "ground_truth_m", "used_as_anchor", "endpoints/notes"]
        rows = list(rd)
    assert len(rows) == 13
    assert [r["used_as_anchor"] for r in rows].count("1") == 1 and rows[0]["used_as_anchor"] == "1"
    assert rows[0]["ground_truth_m"] == "1.5000" and "A=(0.000, 0.000, 0.000)" in rows[0]["endpoints/notes"]
    aj = json.loads(paths.anchor.read_text(encoding="utf-8"))
    assert aj["id"] == "S01" and aj["L_real"] == 1.5 and aj["used_as_anchor"] == 1 and aj["source"] == "faro"
    assert aj["endpoints_scene_xyz"]["b"] == [1.5, 0.0, 0.0] and aj["faro_to_scene_sha256"] == "abc"
    assert res["anchor"]["confirmed_not_on_glass_or_moving"] is True
    assert an.check_outputs_match_session(paths, sess) == []


def test_finalize_tu_choi_khi_loi_hoac_ghi_de(tmp_path):
    paths = make_paths(tmp_path)
    with pytest.raises(an.AnnotationError, match="không đạt luật kiểm"):
        an.finalize(paths, make_session(good_segments(5)), SNAP)
    assert not paths.csv.exists() and not paths.anchor.exists()
    sess = make_session(good_segments(12))
    an.finalize(paths, sess, SNAP)
    with pytest.raises(an.AnnotationError, match="--overwrite"):
        an.finalize(paths, sess, SNAP)
    an.finalize(paths, sess, SNAP, overwrite=True)


def test_phat_hien_csv_bi_sua_tay(tmp_path):
    paths = make_paths(tmp_path)
    sess = make_session(good_segments(12))
    an.finalize(paths, sess, SNAP)
    text = paths.csv.read_text(encoding="utf-8").replace("1.5000", "1.6000", 1)
    paths.csv.write_text(text, encoding="utf-8")
    assert any("S01 khác phiên" in m for m in an.check_outputs_match_session(paths, sess))


# ---------------------------------------------------------------------------
# Phiên, nạp JSON
# ---------------------------------------------------------------------------


def test_phien_ghi_nguyen_tu_va_doc_lai(tmp_path):
    paths = make_paths(tmp_path)
    assert an.load_session(paths) is None
    sess = make_session(good_segments(2))
    an.save_session(paths, sess)
    assert not paths.session.with_suffix(".json.tmp").exists()
    assert an.load_session(paths)["segments"][0]["id"] == "S01"
    with pytest.raises(an.AnnotationError, match="hash khác"):
        an.check_session_alignment(sess, "khac")
    an.check_session_alignment(sess, "abc")


def test_next_id():
    assert an.next_id([]) == "S01"
    assert an.next_id([{"id": "S01"}, {"id": "S09"}, {"id": "khac"}]) == "S10"


def test_nap_tu_json_va_cac_loi(tmp_path):
    f = tmp_path / "doan.json"
    f.write_text(json.dumps({"segments": [
        {"a": [0, 0, 0], "b": [1.2, 0, 0], "role": "anchor", "type": "door_window", "confirmed_not_on_glass": True},
        {"a": [0, 1, 0], "b": [2, 1, 0], "role": "test", "type": "main_dimension", "label": "dài phòng", "id": "X1"},
        {"a": [0, 2, 0], "b": [2, 2, 1], "role": "test", "type": "diagonal"}]}), encoding="utf-8")
    new = an.segments_from_json(f, [], 0.01)
    assert [s["id"] for s in new] == ["S01", "X1", "S02"]
    assert new[0]["confirmed_not_on_glass_or_moving"] is True and new[0]["length_m"] == 1.2
    with pytest.raises(an.AnnotationError, match="đã có"):
        an.segments_from_json(f, [new[1]], 0.01)
    for bad, msg in (([{"a": [0, 0, 0], "role": "test", "type": "x"}], "thiếu khoá"),
                     ([{"a": [0, 0], "b": [1, 1, 1], "role": "test", "type": "x"}], "phải là"),
                     ({"x": 1}, "danh sách")):
        f.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(an.AnnotationError, match=msg):
            an.segments_from_json(f, [], 0.01)


# ---------------------------------------------------------------------------
# Vòng chấm tương tác (bản giả)
# ---------------------------------------------------------------------------


class Script:
    """Trả lời lần lượt các câu hỏi của annotate_loop."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.answers.pop(0)


def test_vong_cham_luu_tung_doan_xoa_va_resume(tmp_path):
    paths = make_paths(tmp_path)
    sess = make_session([])
    pts = np.array([[0, 0, 0], [1.5, 0, 0], [0, 1, 0], [2, 1, 0.5], [3, 3, 3]], dtype=np.float64)
    picks = iter([(0, 1), (2, 3), None, (0, 4)])
    ask = Script([
        "",           # đoạn 1: chấm
        "a", "door_window", "rộng cửa", "", "y", "y",      # mốc, xác nhận không kính, lưu
        "",           # đoạn 2
        "t", "main_dimension", "dài phòng", "ghi chú", "y",
        "",           # lần chọn None (không đủ 2 điểm): không lưu
        "",           # đoạn 3: vai trò sai
        "x",
        "l", "u", "q"])
    logs = []
    an.annotate_loop(paths, sess, pts, SNAP, pick=lambda p, t: next(picks), ask=ask, out=logs.append)
    saved = an.load_session(paths)
    assert [s["id"] for s in saved["segments"]] == ["S01"]                  # S02 đã bị 'u' xoá
    s1 = saved["segments"][0]
    assert s1["role"] == "anchor" and s1["length_m"] == 1.5 and s1["confirmed_not_on_glass_or_moving"] is True
    assert s1["a_index"] == 0 and s1["b_index"] == 1 and s1["label"] == "rộng cửa"
    joined = "\n".join(logs)
    assert "cần đúng 2 điểm" in joined and "chỉ nhận t hoặc a" in joined and "đã xoá S02" in joined
    # resume: nạp lại phiên và chấm tiếp, id tiếp theo là S02
    picks2 = iter([(2, 3)])
    ask2 = Script(["", "t", "", "", "", "y", "q"])
    an.annotate_loop(paths, saved, pts, SNAP, pick=lambda p, t: next(picks2), ask=ask2, out=logs.append)
    again = an.load_session(paths)
    assert [s["id"] for s in again["segments"]] == ["S01", "S02"] and again["segments"][1]["type"] == "other"


def test_vong_cham_tu_choi_mốc_thứ_hai_va_khong_luu_khi_n(tmp_path):
    paths = make_paths(tmp_path)
    sess = make_session([seg(1, "anchor", (0, 0, 0), (1.5, 0, 0))])
    pts = np.array([[0, 5, 0], [1.4, 5, 0]], dtype=np.float64)
    picks = iter([(0, 1), (0, 1)])
    ask = Script(["", "a",                    # mốc thứ hai bị từ chối ngay sau khi nhập vai trò
                  "", "t", "other", "x", "", "n",   # test nhưng trả lời n ⇒ không lưu
                  "q"])
    logs = []
    an.annotate_loop(paths, sess, pts, SNAP, pick=lambda p, t: next(picks), ask=ask, out=logs.append)
    assert len(sess["segments"]) == 1
    assert any("đã có mốc" in m for m in logs) and any("bỏ qua" in m for m in logs)


# ---------------------------------------------------------------------------
# Hiển thị, hệ thống
# ---------------------------------------------------------------------------


def test_height_colors_trong_0_1_va_khong_chia_khong():
    c = an.height_colors(np.linspace(0, 2.5, 50))
    assert c.shape == (50, 3) and c.min() >= 0 and c.max() <= 1
    assert an.height_colors(np.zeros(4)).shape == (4, 3)


def test_load_display_points_cat_hop_va_voxel(tmp_path):
    rng = np.random.default_rng(0)
    xyz = np.concatenate([rng.uniform(0, 2, (3000, 3)), rng.uniform(20, 22, (1000, 3))]).astype(np.float32)
    ply = tmp_path / "x.ply"
    an.faro_align.write_ply_xyz(ply, xyz)
    box = (np.array([-1.0, -1.0, -1.0]), np.array([3.0, 3.0, 3.0]))
    pts = an.load_display_points(ply, box, 0.01)
    assert len(pts) == 3000 and pts.max() <= 3.0
    coarse = an.load_display_points(ply, box, 0.5)
    assert 0 < len(coarse) < 3000
    assert len(an.load_display_points(ply, None, 0.01)) == 4000
    with pytest.raises(an.AnnotationError, match="không còn điểm"):
        an.load_display_points(ply, (np.array([100.0] * 3), np.array([101.0] * 3)), 0.01)


def _faro_like_ply(path, xyz, rgb):
    """PLY kiểu Faro (double xyz + uchar rgba + double quality, radius) có màu."""
    dt = np.dtype([("x", "<f8"), ("y", "<f8"), ("z", "<f8"), ("red", "u1"), ("green", "u1"), ("blue", "u1"), ("alpha", "u1"),
                   ("quality", "<f8"), ("radius", "<f8")])
    arr = np.zeros(len(xyz), dtype=dt)
    arr["x"], arr["y"], arr["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    arr["red"], arr["green"], arr["blue"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    header = "\n".join(["ply", "format binary_little_endian 1.0", f"element vertex {len(xyz)}", "property double x",
                        "property double y", "property double z", "property uchar red", "property uchar green",
                        "property uchar blue", "property uchar alpha", "property double quality", "property double radius",
                        "element face 0", "property list uchar int vertex_indices", "end_header", ""]).encode("ascii")
    path.write_bytes(header + arr.tobytes())


def test_default_box_theo_mesh(tmp_path):
    assert an.default_box(tmp_path, "nomesh") is None                      # thiếu mesh ⇒ không cắt
    import open3d as o3d
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(np.array([[-1.67, -2.4, -0.81], [4.53, 3.9, 1.8], [0.0, 0.0, 0.0]]))
    mesh.triangles = o3d.utility.Vector3iVector(np.array([[0, 1, 2]]))
    assert o3d.io.write_triangle_mesh(str(tmp_path / "42444738_3dod_mesh.ply"), mesh)
    lo, hi = an.default_box(tmp_path, "42444738")
    assert np.allclose(lo, [-1.97, -2.7, -1.11], atol=1e-4) and np.allclose(hi, [4.83, 4.2, 2.1], atol=1e-4)


def test_ghi_doc_ply_xyz_rgb(tmp_path):
    rng = np.random.default_rng(0)
    xyz = rng.uniform(-2, 2, (300, 3))
    rgb = rng.integers(0, 256, (300, 3)).astype(np.uint8)
    an.write_ply_xyz_rgb(tmp_path / "d.ply", xyz, rgb)
    got_xyz, got_rgb = an.read_ply_xyz_rgb(tmp_path / "d.ply")
    assert np.allclose(got_xyz, xyz.astype(np.float32)) and np.allclose(got_rgb, rgb / 255.0)
    with pytest.raises(ValueError):
        an.write_ply_xyz_rgb(tmp_path / "e.ply", xyz, rgb[:10])


def make_rgb_world(tmp_path):
    """Một visit Faro giả: 2 scan duy nhất (+ 1 bản trùng không dùng), faro_to_scene = xoay 90° quanh z + dời."""
    paths = make_paths(tmp_path)
    visit = tmp_path / "visit"
    visit.mkdir()
    rng = np.random.default_rng(1)
    pose = "1,0,0,0\n0,1,0,0\n0,0,1,0\n0,0,215,1\n"
    inside = rng.uniform(0, 1, (400, 3)) * 0.8 + np.array([0.1, 0.1, 215.1])
    outside = rng.uniform(0, 1, (100, 3)) + np.array([50.0, 50.0, 215.0])
    xyz = np.concatenate([inside, outside])
    for sid, color in (("100", (200, 10, 10)), ("200", (10, 200, 10)), ("300", (0, 0, 255))):
        _faro_like_ply(visit / f"{sid}.ply", xyz, np.tile(np.array(color, dtype=np.uint8), (len(xyz), 1)))
        (visit / f"{sid}_pose.txt").write_text(pose, encoding="utf-8")
    t = np.eye(4)
    t[:3, :3] = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    t[:3, 3] = [1.0, 2.0, -215.0]
    f2s = {"status": "committed", "T_faro_to_scene": t.tolist(), "unique_scans_used": ["100", "200"]}
    paths.f2s.write_text(json.dumps(f2s), encoding="utf-8")
    return paths, visit, f2s, t, inside


def test_make_rgb_display_cat_hop_trung_binh_mau_va_khong_dung_gt(tmp_path):
    paths, visit, f2s, t, inside = make_rgb_world(tmp_path)
    gt = paths.ply
    gt.write_bytes(b"GT-khong-duoc-sua")
    box = (np.array([-2.0, -2.0, -2.0]), np.array([4.0, 4.0, 4.0]))
    logs = []
    meta = an.make_rgb_display(paths, visit, f2s, "sha-x", box, 0.05, out=logs.append)
    assert gt.read_bytes() == b"GT-khong-duoc-sua"                            # không đụng GT
    xyz, rgb = an.read_ply_xyz_rgb(paths.rgb_ply)
    assert len(xyz) == meta["n_points"] and 0 < len(xyz) <= 400              # điểm ngoài hộp bị bỏ
    assert xyz.min() >= -2.0 and xyz.max() <= 4.0
    expect = an.frs.apply_T(t, inside)
    assert np.all(np.abs(xyz[:, 2] - expect[:, 2].mean()) < 1.0)
    # hai scan chồng khít nhau ⇒ màu trung bình (200,10,10) và (10,200,10) = (105,105,10); scan "300" không dùng (không có màu xanh dương)
    assert np.allclose(rgb * 255, [105, 105, 10], atol=1.0)
    m = json.loads(paths.rgb_meta.read_text(encoding="utf-8"))
    assert m["scans"] == ["100", "200"] and m["faro_to_scene_sha256"] == "sha-x" and m["box"] is not None
    assert len(logs) == 2
    # nạp lại: đúng hash thì được, sai hash thì từ chối
    pts, cols = an.load_rgb_display(paths, "sha-x")
    assert len(pts) == len(xyz) and cols.shape == (len(xyz), 3)
    with pytest.raises(an.AnnotationError, match="khác"):
        an.load_rgb_display(paths, "sha-khac")


def test_make_rgb_display_loi(tmp_path):
    paths, visit, f2s, t, inside = make_rgb_world(tmp_path)
    with pytest.raises(an.AnnotationError, match="unique_scans_used"):
        an.make_rgb_display(paths, visit, {"T_faro_to_scene": t.tolist()}, "x", None, 0.05, out=lambda m: None)
    f2s_bad = dict(f2s, unique_scans_used=["999"])
    with pytest.raises(an.AnnotationError, match="thiếu scan"):
        an.make_rgb_display(paths, visit, f2s_bad, "x", None, 0.05, out=lambda m: None)
    far = (np.array([900.0] * 3), np.array([901.0] * 3))
    with pytest.raises(an.AnnotationError, match="không còn điểm"):
        an.make_rgb_display(paths, visit, f2s, "x", far, 0.05, out=lambda m: None)
    with pytest.raises(an.AnnotationError, match="--make-rgb"):
        an.load_rgb_display(make_paths(tmp_path / "other"), "x")


def test_doan_ghi_nhan_file_hien_thi(tmp_path):
    paths = make_paths(tmp_path)
    sess = make_session([])
    pts = np.array([[0, 0, 0], [1.5, 0, 0]], dtype=np.float64)
    ask = Script(["", "t", "", "", "", "y", "q"])
    an.annotate_loop(paths, sess, pts, SNAP, pick=lambda p, t: (0, 1), ask=ask, out=lambda m: None, display_name="faro_display_rgb.ply")
    assert an.load_session(paths)["segments"][0]["display_file"] == "faro_display_rgb.ply"
    assert good_segments(1)[0]["display_file"] == "faro_scene_frame.ply"


def test_require_alignment(tmp_path):
    paths = make_paths(tmp_path)
    with pytest.raises(an.AnnotationError, match="faro_align.py"):
        an.require_alignment(paths)
    paths.f2s.write_text(json.dumps({"status": "candidate"}), encoding="utf-8")
    paths.ply.write_bytes(b"x")
    with pytest.raises(an.AnnotationError, match="status"):
        an.require_alignment(paths)
    paths.f2s.write_text(json.dumps({"status": "committed"}), encoding="utf-8")
    assert an.require_alignment(paths)["status"] == "committed"


def test_main_chan_heldout_va_thieu_can_faro(tmp_path, capsys):
    assert an.main(["--scene", "arkitscenes/43828368", "--check"]) == 1
    assert "held-out" in capsys.readouterr().out
    # scene train hợp lệ nhưng root không có data/splits.csv ⇒ lỗi đầu vào, không crash
    assert an.main(["--scene", "arkitscenes/42444738", "--check", "--root", str(tmp_path)]) == 1
