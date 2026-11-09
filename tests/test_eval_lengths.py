"""Test pipeline/eval/lengths.py: đọc GT, Kabsch cứng, snap 2 cm, chế độ manual, chỉ số chiều dài (không cần dữ liệu thật)."""

import json

import numpy as np
import pytest

from pipeline.eval import lengths as ln

CSV = """id,type,ground_truth_m,used_as_anchor,endpoints/notes
S01,local_distance,1.0,0,"A=(0.000, 0.500, 0.500) B=(0.000, 1.500, 0.500); rộng tủ"
S05,door_window,1.9199,1,"A=(-0.716, 1.065, 1.335) B=(-0.715, 1.065, -0.585); mốc"
S02,local_distance,1.2,0,"A=(0.0, 1.0, 0.2) B=(0.0, 1.0, 1.4); cao tủ"
"""


def _rot_z(deg):
    c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


@pytest.fixture()
def segs(tmp_path):
    p = tmp_path / "measurements.csv"
    p.write_text(CSV, encoding="utf-8")
    return ln.read_measurements(p)


def test_doc_gt_va_loai_moc_scale(segs):
    assert [s["id"] for s in segs] == ["S01", "S05", "S02"]
    assert np.allclose(segs[0]["b"], [0, 1.5, 0.5]) and segs[1]["anchor"] and not segs[0]["anchor"]
    assert [s["id"] for s in ln.test_segments(segs)] == ["S01", "S02"]            # mốc không vào chỉ số test (ĐC §8.1)


def test_doc_gt_thieu_dau_mut_thi_loi(tmp_path):
    p = tmp_path / "m.csv"
    p.write_text('id,type,ground_truth_m,used_as_anchor,endpoints/notes\nS01,x,1.0,0,"không có toạ độ"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="S01"):
        ln.read_measurements(p)


def test_kabsch_cung_khoi_phuc_phep_bien_doi_va_khong_doi_scale():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(20, 3))
    r, t = _rot_z(37.0), np.array([1.0, -2.0, 0.5])
    r_hat, t_hat, rms = ln.kabsch_rigid(x, x @ r.T + t)
    assert np.allclose(r_hat, r) and np.allclose(t_hat, t) and rms < 1e-12
    _, _, rms2 = ln.kabsch_rigid(x, 2.0 * x @ r.T + t)                              # scale khác 1 không được hấp thụ
    assert rms2 > 0.1
    with pytest.raises(ValueError):
        ln.kabsch_rigid(x[:2], x[:2])


def _wall(step=0.01):
    y, z = np.meshgrid(np.arange(0, 2.0001, step), np.arange(0, 2.0001, step))
    return np.stack([np.zeros(y.size), y.ravel(), z.ravel()], axis=1)


def test_measure_auto_snap_va_khong_snap(segs):
    r, t = _rot_z(30.0), np.array([1.0, 2.0, 3.0])
    cloud = _wall() @ r.T + t                                                       # tường x = 0 ở hệ scene, đã đưa sang hệ mô hình
    rows = ln.measure_auto(ln.test_segments(segs), r, t, cloud, 0.02)
    assert all(x["valid"] and x["mode"] == "auto" for x in rows)
    assert rows[0]["pred_m"] == pytest.approx(1.0, abs=1e-6) and rows[1]["pred_m"] == pytest.approx(1.2, abs=1e-6)
    far = ln.measure_auto(ln.test_segments(segs), r, t + 0.5 * r[:, 0], cloud, 0.02)               # căn lệch 0,5 m theo pháp tuyến tường: không snap
    assert not any(x["valid"] for x in far) and all(x["pred_m"] is None and x["err_m"] is None for x in far)
    s = ln.snap_summary(far)
    assert s["n_unsnapped"] == 4 and s["n_endpoints"] == 4 and s["nn_median_cm"] > 40 and s["snap_mean_cm"] is None
    assert ln.length_metrics(far)["n_valid"] == 0 and ln.length_metrics(far)["mae_cm"] is None


def test_manual_va_endpoints_json(segs, tmp_path):
    p = tmp_path / "endpoints_B0.json"
    p.write_text(json.dumps({"scene": "arkitscenes/1", "variant": "B0", "unit": "m", "frame": "variant_cloud",
                             "endpoints": {"S01": {"a": [0, 0, 0], "b": [1.04, 0, 0]}}}), encoding="utf-8")
    ep = ln.read_endpoints_json(p, "arkitscenes/1")
    rows = ln.measure_manual(ln.test_segments(segs), ep)
    assert rows[0]["valid"] and rows[0]["err_m"] == pytest.approx(0.04) and rows[0]["mode"] == "manual"
    assert not rows[1]["valid"]                                                     # S02 chưa chấm
    with pytest.raises(ValueError):
        ln.read_endpoints_json(p, "arkitscenes/2")
    p.write_text(json.dumps({"unit": "cm", "endpoints": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        ln.read_endpoints_json(p)


def test_chi_so_chieu_dai_phong_R02():
    """ĐC §20.2: sai số 6, 3, 3, 3, 7, 2 cm trên 3,30; 2,85; 2,40; 0,90; 1,20; 1,40 m → MAE 4,0; median 3; %<5 cm = 67%."""
    gt = [3.30, 2.85, 2.40, 0.90, 1.20, 1.40]
    err = [0.06, 0.03, 0.03, 0.03, 0.07, 0.02]
    rows = [{"id": f"S{i}", "valid": True, "pred_m": g + e, "gt_m": g} for i, (g, e) in enumerate(zip(gt, err))]
    m = ln.length_metrics(rows)
    assert m["n_valid"] == 6 and m["mae_cm"] == pytest.approx(4.0) and m["median_cm"] == pytest.approx(3.0)
    assert m["pct_lt5cm"] == pytest.approx(66.67, abs=0.01) and m["mape_pct"] == pytest.approx(2.45, abs=0.05)
    sub = ln.length_metrics(rows, {"S0", "S1"})
    assert sub["n_valid"] == 2 and sub["mae_cm"] == pytest.approx(4.5)


def _frame(rot_deg=25.0, t=(0.3, 1.2, -0.4)):
    return {"rotation_from_colmap_metric": _rot_z(rot_deg).tolist(), "translation": list(t)}


def test_endpoints_do_measure_ghi_doc_duoc(tmp_path):
    """Hợp đồng measure → eval: file do chính thư viện `pipeline.export.measure` ghi (list `segments`, hệ model) phải đọc được và đổi về hệ COLMAP mét."""
    from pipeline.export import measure as ms
    frame = _frame()
    r, t = np.array(frame["rotation_from_colmap_metric"]), np.array(frame["translation"])
    a_cm, b_cm = np.array([0.0, 0.5, 0.5]), np.array([0.0, 1.5, 0.5])
    doc = ms.new_endpoints("arkitscenes/1", "proposed", "proposed/export/model_points.ply", "0" * 64)
    assert doc["frame"] == ms.MODEL_FRAME
    ms.add_segment(doc, "S01", (r @ a_cm + t).tolist(), (r @ b_cm + t).tolist())
    p = tmp_path / "endpoints_proposed.json"
    ms.save_endpoints(p, doc)
    ep = ln.read_endpoints_json(p, "arkitscenes/1", frame)
    assert np.allclose(ep["S01"][0], a_cm, atol=1e-9) and np.allclose(ep["S01"][1], b_cm, atol=1e-9)
    assert ln.measure_manual(ln.test_segments([{"id": "S01", "type": "x", "gt_m": 1.0, "anchor": False}]), ep)[0]["pred_m"] == pytest.approx(1.0)
    with pytest.raises(ValueError, match="model.glb"):                              # thiếu thông tin hệ model → không đoán
        ln.read_endpoints_json(p)


def test_endpoints_khung_cloud_va_frame_la(tmp_path):
    from pipeline.export import measure as ms
    assert ms.frame_of_points_file("x/proposed/export/model_points.ply") == ms.MODEL_FRAME and ms.frame_of_points_file("a/model.glb") == ms.MODEL_FRAME
    assert ms.frame_of_points_file("baselines/colmap/metric/fused_metric.ply") == ms.CLOUD_FRAME
    p = tmp_path / "e.json"
    p.write_text(json.dumps({"frame": ms.CLOUD_FRAME, "segments": [{"id": "S01", "a": [0, 0, 0], "b": [1, 0, 0]}]}), encoding="utf-8")
    assert np.allclose(ln.read_endpoints_json(p)["S01"][1], [1, 0, 0])               # hệ cloud: giữ nguyên, không cần hệ model
    p.write_text(json.dumps({"frame": "lạ", "segments": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="frame"):
        ln.read_endpoints_json(p)
    p.write_text(json.dumps({"frame": ms.CLOUD_FRAME}), encoding="utf-8")
    with pytest.raises(ValueError, match="endpoints"):
        ln.read_endpoints_json(p)


def test_measure_transfer_snap_va_doan_chua_cham():
    r, t = _rot_z(30.0), np.array([1.0, 2.0, 3.0])
    cloud = _wall() @ r.T + t
    segs = [{"id": "S01", "type": "x", "gt_m": 1.0}, {"id": "S02", "type": "x", "gt_m": 1.2}]
    ep = {"S01": (np.array([0.0, 0.5, 0.5]), np.array([0.0, 1.5, 0.5]))}              # nguồn chỉ chấm S01, ở hệ "nguồn" = hệ tường
    rows = ln.measure_transfer(segs, ep, r, t, cloud, 0.02)
    assert rows[0]["valid"] and rows[0]["mode"] == "manual_transfer" and rows[0]["pred_m"] == pytest.approx(1.0, abs=1e-6)
    assert not rows[1]["valid"] and rows[1]["mode"] == "manual_transfer"
    far = ln.measure_transfer(segs, ep, r, t + 0.5 * r[:, 0], cloud, 0.02)             # lệch 0,5 m: không snap được
    assert not far[0]["valid"]


def test_kabsch_cat_tia_bo_camera_sai_va_khoi_phuc_phep_can():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(40, 3)) * 2.0
    r, t = _rot_z(25.0), np.array([0.3, 1.0, -0.7])
    y = x @ r.T + t + rng.normal(scale=0.01, size=x.shape)
    bad = [3, 7, 8, 20]
    y[bad] += np.array([[4, 3, 0], [-3, 4, 0], [0, 5, 2], [6, 0, -3]])               # 4 camera SfM đặt sai vài mét
    r0, t0, rms0 = ln.kabsch_rigid(x, y)
    r1, t1, rms1, keep = ln.kabsch_rigid_trimmed(x, y, 3.0)
    assert set(np.nonzero(~keep)[0]) == set(bad)
    assert np.linalg.norm(t1 - t) < 0.01 < np.linalg.norm(t0 - t) and rms1 < 0.02 < rms0
    assert np.degrees(np.arccos(np.clip((np.trace(r1.T @ r) - 1) / 2, -1, 1))) < 0.5


def test_kabsch_cat_tia_khong_loai_gi_khi_khop_hoan_hao_hoac_con_qua_it_cap():
    x = np.random.default_rng(2).normal(size=(10, 3))
    y = x @ _rot_z(10.0).T + [1.0, 0.0, 0.0]
    assert ln.kabsch_rigid_trimmed(x, y, 3.0)[3].all()                              # residual đều ≈ 0: không loại ai
    x3 = x[:4]
    y3 = x3 @ _rot_z(10.0).T
    y3[0] += 100.0                                                                  # chỉ 4 cặp: loại 1 còn 3 vẫn hợp lệ
    assert ln.kabsch_rigid_trimmed(x3, y3, 0.0)[3].sum() >= 3
