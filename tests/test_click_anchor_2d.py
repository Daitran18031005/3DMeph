"""Test mốc scale 2D: tam giác hoá DLT (pipeline/alignment/anchor.py) và phần không GUI của scripts/click_anchor_2d.py."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from pipeline.alignment import anchor as an
from pipeline.common import io as pio
from pipeline.common.geometry import camera_center, project, rodrigues

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
K = np.array([[500.0, 0, 240], [0, 500.0, 320], [0, 0, 1]])
A, B = np.array([0.1, -0.5, 4.0]), np.array([0.12, 0.5, 4.1])
L_TRUE = float(np.linalg.norm(B - A))


def cam(angle, cx):
    r = rodrigues(np.array([0.0, angle, 0.0]))
    t = -r @ np.array([cx, 0.0, 0.0])
    return {"K": K, "R": r, "t": t, "center": camera_center(r, t)}


def cams3():
    return {0: cam(0.0, 0.0), 1: cam(0.2, 1.0), 2: cam(-0.15, -0.8)}


def clicks(cams, views, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    return [{"view": v, "a": project(K, cams[v]["R"], cams[v]["t"], A[None])[0] + rng.normal(0, noise, 2),
             "b": project(K, cams[v]["R"], cams[v]["t"], B[None])[0] + rng.normal(0, noise, 2)} for v in views]


def test_triangulate_dlt_chinh_xac_khi_khong_nhieu():
    c = cams3()
    ps = [an.projection_matrix(c[v]["K"], c[v]["R"], c[v]["t"]) for v in (0, 1)]
    uvs = [project(K, c[v]["R"], c[v]["t"], A[None])[0] for v in (0, 1)]
    assert np.allclose(an.triangulate_dlt(ps, uvs), A, atol=1e-8)
    with pytest.raises(ValueError):
        an.triangulate_dlt(ps[:1], uvs[:1])


def test_anchor_from_clicks_L_model_va_sai_so():
    c = cams3()
    res = an.anchor_from_clicks(c, clicks(c, (0, 1)))
    assert res["L_model"] == pytest.approx(L_TRUE, rel=1e-8) and max(res["a"]["reproj_px"]) < 1e-6
    assert res["a"]["max_ray_angle_deg"] > 5
    noisy = an.anchor_from_clicks(c, clicks(c, (0, 1, 2), noise=1.0, seed=3))
    assert abs(noisy["L_model"] - L_TRUE) / L_TRUE < 0.05 and 0 < np.mean(noisy["a"]["reproj_px"]) < 3
    with pytest.raises(ValueError, match="2 keyframe"):
        an.anchor_from_clicks(c, clicks(c, (0,)))
    with pytest.raises(ValueError, match="hai lần"):
        an.normalize_obs([{"view": 1, "endpoint": "a", "uv": [1, 1]}, {"view": 1, "endpoint": "a", "uv": [2, 2]}])
    with pytest.raises(ValueError, match="endpoint"):
        an.normalize_obs([{"view": 1, "endpoint": "c", "uv": [1, 1]}])
    with pytest.raises(ValueError, match="chưa đăng ký"):
        an.anchor_from_clicks(c, clicks(c, (0, 1)) + [{"view": 9, "a": [1, 1], "b": [2, 2]}])


def per_endpoint(cams, a_views, b_views, noise=0.0):
    out = []
    for key, vs in (("a", a_views), ("b", b_views)):
        out += [{"view": o["view"], "endpoint": key, "uv": list(o[key])} for o in clicks(cams, vs, noise=noise)]
    return out


def test_tam_giac_hoa_doc_lap_tung_dau_mut_o_anh_rieng():
    """Đúng tình huống S05: A thấy ở vài ảnh, B thấy ở ảnh khác, không ảnh nào thấy cả hai."""
    c = cams3()
    obs = per_endpoint(c, (0, 1, 2), (1, 2))
    res = an.anchor_from_clicks(c, obs)
    assert res["L_model"] == pytest.approx(L_TRUE, rel=1e-8)
    assert res["a"]["views"] == [0, 1, 2] and res["b"]["views"] == [1, 2] and max(res["b"]["reproj_px"]) < 1e-6
    assert an.anchor_from_clicks(c, clicks(c, (0, 1)))["L_model"] == pytest.approx(res["L_model"], rel=1e-8)   # dạng cũ {view, a, b} vẫn dùng được
    with pytest.raises(ValueError, match="đầu mút B"):
        an.anchor_from_clicks(c, per_endpoint(c, (0, 1, 2), (1,)))
    noisy = an.anchor_from_clicks(c, per_endpoint(c, (0, 1, 2), (1, 2), noise=1.0))
    assert abs(noisy["L_model"] - L_TRUE) / L_TRUE < 0.1


def test_script_from_json_ghi_L_model_va_chong_ghi_de(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, str(SCRIPTS))
    try:
        import click_anchor_2d as ca
    finally:
        sys.path.remove(str(SCRIPTS))
    layout = pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777")
    anchor_path = layout.ground_truth / "scale_anchor.json"
    pio.write_json(anchor_path, {"id": "S05", "label": "cao cánh cửa", "L_real": 1.92, "endpoints_scene_xyz": {"a": [0, 0, 0], "b": [0, 0, 1.92]}})
    c = cams3()
    obs_file = tmp_path / "obs.json"
    obs_file.write_text(json.dumps([{"view": o["view"], "a": list(o["a"]), "b": list(o["b"])} for o in clicks(c, (0, 1))]), encoding="utf-8")
    monkeypatch.setattr(ca.pr, "resolve_scene", lambda root, scene, cfg: {"layout": layout})
    monkeypatch.setattr(ca, "load_colmap_cameras", lambda lay: c)
    monkeypatch.setattr(ca, "model_fingerprint", lambda lay: "abc123")
    argv = ["--scene", "arkitscenes/777", "--from-json", str(obs_file)]
    assert ca.main(argv) == 0
    saved = pio.read_json(anchor_path)
    assert saved["L_model"] == pytest.approx(L_TRUE, rel=1e-6) and saved["L_real"] == 1.92 and saved["endpoints_scene_xyz"]["b"] == [0, 0, 1.92]
    assert len(saved["observations_2d"]) == 4 and "L_model = " in capsys.readouterr().out and saved["colmap_model_sha256"] == "abc123"
    assert ca.main(argv) == 1                                              # có L_model rồi: cần --overwrite
    assert ca.main(argv + ["--overwrite"]) == 0
    assert ca.main(["--scene", "arkitscenes/777", "--check"]) == 0
    obs_file.write_text(json.dumps(per_endpoint(c, (0, 1, 2), (1, 2))), encoding="utf-8")
    assert ca.main(argv + ["--overwrite"]) == 0
    saved = pio.read_json(anchor_path)
    assert saved["L_model"] == pytest.approx(L_TRUE, rel=1e-6) and saved["views_per_endpoint"] == {"a": [0, 1, 2], "b": [1, 2]}
    assert len(saved["observations_2d"]) == 5 and "A: 3 ảnh [0, 1, 2]" in capsys.readouterr().out
    assert ca.main(["--scene", "arkitscenes/777", "--overwrite", "--views", "55"]) == 1        # view chưa đăng ký: báo lỗi trước khi mở GUI
    assert "chưa đăng ký" in capsys.readouterr().out


def test_validate_obs_view_trung():
    sys.path.insert(0, str(SCRIPTS))
    try:
        import click_anchor_2d as ca
    finally:
        sys.path.remove(str(SCRIPTS))
    with pytest.raises(ValueError, match="hai lần"):
        ca.validate_obs([{"view": 1, "a": [0, 0], "b": [1, 1]}, {"view": 1, "a": [0, 0], "b": [1, 1]}])


def test_fit_zoom_vua_man_hinh():
    sys.path.insert(0, str(SCRIPTS))
    try:
        import click_anchor_2d as ca
    finally:
        sys.path.remove(str(SCRIPTS))
    assert ca.fit_zoom(None) == 1.0
    assert ca.fit_zoom(1080) == 1.42 and ca.fit_zoom(2160) == 1.5            # trần 1,5
    assert ca.fit_zoom(720) == 0.86 and ca.fit_zoom(300) == 0.5              # sàn 0,5
    assert 640 * ca.fit_zoom(768) + 170 <= 768                               # luôn vừa chiều cao màn hình (+ dải trạng thái và tiêu đề)


def test_run_gui_gia_lap_cv2_diem_click_khong_bi_dai_trang_thai_che(tmp_path, monkeypatch):
    """Chạy vòng lặp GUI với cv2 giả: A ở 2 ảnh, B ở 2 ảnh khác; click trong dải trạng thái bị bỏ qua; toạ độ trừ đúng dải."""
    import cv2

    sys.path.insert(0, str(SCRIPTS))
    try:
        import click_anchor_2d as ca
    finally:
        sys.path.remove(str(SCRIPTS))
    layout = pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777")
    pio.ensure_dir(layout.keyframes)
    for v in (12, 13, 15, 16):
        cv2.imwrite(str(layout.keyframes / f"{v:04d}.jpg"), np.zeros((640, 480, 3), dtype=np.uint8))
    cb, shown = {}, []
    monkeypatch.setattr(cv2, "namedWindow", lambda *a, **k: None)
    monkeypatch.setattr(cv2, "moveWindow", lambda *a, **k: None)
    monkeypatch.setattr(cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(cv2, "setMouseCallback", lambda win, f: cb.update(f=f))
    monkeypatch.setattr(cv2, "imshow", lambda win, img: shown.append(img.shape))
    steps = iter([("click", 100, 5), ("click", 100, ca.BAR_H + 200), 13, ord("d"), ("click", 50, ca.BAR_H + 10), 13, ord("d"), ord("2"),
                  ("click", 300, ca.BAR_H + 600), 13, ord("d"), ("click", 301, ca.BAR_H + 590), 13, ord("s")])

    def fake_wait(ms):
        step = next(steps)
        if isinstance(step, tuple):
            cb["f"](cv2.EVENT_LBUTTONDOWN, step[1], step[2], 0, None)
            return -1
        return step

    monkeypatch.setattr(cv2, "waitKeyEx", fake_wait)
    obs = ca.run_gui(layout, {}, {"id": "S05", "label": "cao cánh cửa"}, 1.0, [12, 13, 15, 16])
    got = {(o["view"], o["endpoint"]): o["uv"] for o in obs}
    assert got == {(12, "a"): [100.5, 200.5], (13, "a"): [50.5, 10.5], (15, "b"): [300.5, 600.5], (16, "b"): [301.5, 590.5]}
    assert all(sh == (ca.BAR_H + 640, 480, 3) for sh in shown)
