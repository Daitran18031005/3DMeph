"""Test các stage fuse, gate, export (M1d) bằng cảnh tổng hợp: không cần COLMAP, VGGT hay GPU."""

import json
import struct

import cv2
import numpy as np
import pytest

from pipeline.common import config as cfgmod
from pipeline.common import io as pio
from pipeline.common.errors import E_MISSING_INPUT, StageError
from pipeline.common.ply import read_ply, write_ply
from pipeline.common.schema import write_keyframes_csv
from pipeline.export import mesh as exp
from pipeline.fusion import stage as fs
from pipeline.plane_gate import stage as gs
from pipeline.vggt.infer import pad_geometry

W, H, F = 48, 64, 50.0
CX, CY = W / 2, H / 2


# ---------------------------------------------------------------------------
# PLY, vis, lấy mẫu
# ---------------------------------------------------------------------------


def write_images_bin(path, ids_names, n_points2d=0):
    """Ghi `images.bin` tối giản của COLMAP: danh sách (image_id, tên) theo đúng thứ tự cho trước, mỗi ảnh `n_points2d` điểm 2D rỗng."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = struct.pack("<Q", len(ids_names))
    for iid, name in ids_names:
        body += struct.pack("<I7dI", iid, 1, 0, 0, 0, 0, 0, 0, 1) + name.encode() + b"\0" + struct.pack("<Q", n_points2d) + b"\0" * (24 * n_points2d)
    path.write_bytes(body)


def test_read_fusion_image_names_theo_image_id_khong_theo_thu_tu_file(tmp_path):
    """`fused.ply.vis` đánh chỉ số theo image_id tăng dần trong mvs/sparse/images.bin; `fusion.cfg` (xáo thứ tự) không được dùng."""
    write_images_bin(tmp_path / "sparse" / "images.bin", [(9, "0000.jpg"), (2, "0003.jpg"), (5, "0001.jpg")], n_points2d=3)
    (tmp_path / "stereo").mkdir()
    (tmp_path / "stereo" / "fusion.cfg").write_text("0000.jpg\n0001.jpg\n0003.jpg\n", encoding="utf-8")
    assert fs.read_fusion_image_names(tmp_path) == ["0003.jpg", "0001.jpg", "0000.jpg"]
    f = tmp_path / "sparse" / "images.bin"
    f.write_bytes(f.read_bytes() + b"\0")
    with pytest.raises(StageError):
        fs.read_fusion_image_names(tmp_path)
    with pytest.raises(StageError):
        fs.read_fusion_image_names(tmp_path / "khong_co")


def test_ply_khu_hoi_nhieu_kieu(tmp_path):
    f = {"x": np.array([1, 2], np.float32), "y": np.array([3, 4], np.float32), "n_views": np.array([5, 6], np.uint8), "plane_id": np.array([-1, 7], np.int32)}
    write_ply(tmp_path / "a.ply", f)
    g = read_ply(tmp_path / "a.ply")
    assert all(np.array_equal(f[k], g[k]) and f[k].dtype == g[k].dtype for k in f)
    with pytest.raises(ValueError):
        write_ply(tmp_path / "b.ply", {"x": np.zeros(2, np.float16)})


def test_read_vis_va_sample_bilinear(tmp_path):
    body = struct.pack("<Q", 2) + struct.pack("<I3I", 3, 0, 4, 9) + struct.pack("<I2I", 2, 1, 2)
    (tmp_path / "v.vis").write_bytes(body)
    counts, flat = fs.read_vis(tmp_path / "v.vis")
    assert counts.tolist() == [3, 2] and flat.tolist() == [0, 4, 9, 1, 2]
    (tmp_path / "bad.vis").write_bytes(body + b"\0")
    with pytest.raises(ValueError, match="thừa"):
        fs.read_vis(tmp_path / "bad.vis")
    ramp = np.add.outer(np.arange(6.0) * 10, np.arange(8.0))                    # f(y, x) = 10y + x, tuyến tính nên song tuyến chính xác
    uv = np.array([[3.5, 2.5], [4.0, 3.0], [0.0, 0.0], [99.0, 99.0]])             # tâm pixel ở nửa số nguyên; ngoài biên bị kẹp
    out = fs.sample_bilinear(ramp, uv)
    assert np.allclose(out[:2], [2 * 10 + 3, 2.5 * 10 + 3.5]) and out[2] == 0 and out[3] == ramp[-1, -1]


def test_view_to_chunk_chon_chunk_xa_bien_hon_va_pad_pairs():
    chunks = [{"chunk": 0, "views": list(range(0, 12))}, {"chunk": 1, "views": list(range(10, 22))}]
    m = fs.view_to_chunk(chunks)
    assert m[10] == (0, 10) and m[11] == (1, 1)     # view 10: lề 1 ở chunk 0 so với 0 ở chunk 1; view 11: lề 0 ở chunk 0 so với 1 ở chunk 1
    assert m[5][0] == 0 and m[15][0] == 1 and len(m) == 22
    counts = np.array([2, 1, 3])
    padded = fs.pad_pairs(counts, np.arange(6.0) + 1)
    assert padded.tolist() == [[1, 2, 0], [3, 0, 0], [4, 5, 6]]


# ---------------------------------------------------------------------------
# fuse: chuỗi hình học chiếu → pad → Sim(3) chunk → s_m, kiểm bằng mặt phẳng z = 2 biết trước
# ---------------------------------------------------------------------------


def cam_for(cx_shift):
    r, t = np.eye(3), np.array([-cx_shift, 0.0, 0.0])
    return {"K": np.array([[F, 0, CX], [0, F, CY], [0, 0, 1.0]]), "R": r, "t": t, "center": np.array([cx_shift, 0.0, 0.0])}


def make_fuse_scene(tmp_path, s_m=0.5):
    """3 view (camera dịch ngang 0, 0,2, 0,4), điểm MVS nằm trên mặt phẳng z = 2; bản đồ VGGT chính là mặt phẳng đó (đv VGGT = đv COLMAP, Sim(3) đơn vị)."""
    lay = pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777")
    geo = pad_geometry(W, H)
    cams = {v: cam_for(0.2 * i) for i, v in enumerate((0, 1, 2))}
    for d in (lay.keyframes, lay.metadata, lay.alignment, lay.colmap_mvs / "sigma_depth", lay.colmap_mvs / "stereo", lay.colmap_sfm / "e_reproj_map", lay.vggt / "chunk_00"):
        pio.ensure_dir(d)
    rng = np.random.default_rng(0)
    rows = []
    for v in cams:
        cv2.imwrite(str(lay.keyframes / f"{v:04d}.jpg"), rng.integers(0, 256, (H, W, 3), dtype=np.uint8))
        np.save(lay.colmap_sfm / "e_reproj_map" / f"{v:04d}.npy", np.full((H, W), 0.5, np.float32))
        np.save(lay.colmap_mvs / "sigma_depth" / f"{v:04d}.npy", np.full((H, W), 0.01, np.float32))
        rows.append({"view_id": v, "frame_ts": v, "src_name": f"x{v}", "V": 1, "q_blur": 1.0, "q_exposure": 1.0, "w": W, "h": H, "fx": F, "fy": F, "cx": CX, "cy": CY})
    write_keyframes_csv(rows, lay.metadata / "keyframes.csv")
    # bản đồ điểm VGGT: pixel (a, b) của ảnh 518×518 → pixel gốc → điểm trên z = 2 (camera view v)
    gy, gx = np.mgrid[0:518, 0:518] + 0.5
    u = (gx - geo["pad_left"]) / geo["scale_x"]
    v_ = (gy - geo["pad_top"]) / geo["scale_y"]
    pts = np.stack([np.stack([cams[v]["center"][0] + 2.0 * (u - CX) / F, 2.0 * (v_ - CY) / F, np.full_like(u, 2.0)], axis=-1) for v in cams]).astype(np.float32)
    np.savez(lay.vggt / "chunk_00" / "vggt_raw.npz", extrinsic=np.zeros((3, 3, 4)), intrinsic=np.zeros((3, 3, 3)), depth=np.zeros((3, 2, 2)), depth_conf=np.ones((3, 2, 2)))
    np.savez(lay.vggt / "chunk_00" / "vggt_out.npz", c_model=np.full((3, 518, 518), 0.8, np.float32), points=pts)
    pio.write_json(lay.vggt / "chunk_00" / "chunk_meta.json", {"chunk": 0, "start": 0, "end": 3, "views": [0, 1, 2]})
    pio.write_json(lay.alignment / "chunk_00_sim3.json", {"chunk": 0, "accepted": True, "views": [0, 1, 2], "s": 1.0, "R": np.eye(3).tolist(), "t": [0, 0, 0]})
    pio.write_json(lay.alignment / "scale.json", {"s_m": s_m})
    # điểm MVS: lưới trên mặt phẳng z = 2, nhìn thấy bởi cả 3 view
    xs, ys = np.meshgrid(np.linspace(-0.3, 0.3, 6), np.linspace(-0.4, 0.4, 6))
    x_colmap = np.stack([xs.ravel() + 0.2, ys.ravel(), np.full(36, 2.0)], axis=1)
    import open3d as o3d
    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(x_colmap))
    o3d.io.write_point_cloud(str(lay.colmap_mvs / "fused.ply"), pcd)
    (lay.colmap_mvs / "fused.ply.vis").write_bytes(struct.pack("<Q", 36) + b"".join(struct.pack("<I3I", 3, 0, 1, 2) for _ in range(36)))
    write_images_bin(lay.colmap_mvs / "sparse" / "images.bin", [(1, "0000.jpg"), (2, "0001.jpg"), (3, "0002.jpg")])
    return lay, cams, x_colmap


def test_run_fuse_chuoi_hinh_hoc_khop_mat_phang_biet_truoc(tmp_path):
    lay, cams, x = make_fuse_scene(tmp_path, s_m=0.5)
    st = fs.run_fuse(lay, cfgmod.load_config(), log=lambda m: None, load_cameras=lambda lay_: cams)
    assert st["n_points_fused"] == 36 and st["n_pairs_valid"] == 108 and st["sigma_nan_fraction"] == 0
    f = read_ply(lay.fusion / "fused_points.ply")
    got = np.stack([f["x"], f["y"], f["z"]], axis=1)
    assert np.allclose(got, x * 0.5, atol=2e-3)                                  # đúng s_m · (điểm COLMAP)
    assert st["vggt_vs_colmap_pair_cm"]["median"] < 0.3 and (f["n_views"] == 3).all()
    assert 0 < f["w_k"].min() and f["w_k"].max() <= 1
    log = np.load(lay.fusion / "fusion_log.npz")
    assert len(log["w"]) == 108 and np.allclose(np.bincount(log["point"], weights=log["w_tilde"]), 1.0, atol=1e-5)   # Σ w̃ = 1 mỗi điểm


def test_run_fuse_thieu_dau_vao(tmp_path):
    lay = pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777")
    with pytest.raises(StageError) as e:
        fs.run_fuse(lay, cfgmod.load_config(), log=lambda m: None, load_cameras=lambda lay_: {})
    assert e.value.code == E_MISSING_INPUT


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------


def room_points(rng, n=3000, noise=0.01):
    floor = np.stack([rng.uniform(0, 4, n), np.zeros(n), rng.uniform(0, 3, n)], axis=1)            # y = 0 (u = +y)
    ceil = np.stack([rng.uniform(0, 4, n), np.full(n, 2.5), rng.uniform(0, 3, n)], axis=1)
    wall = np.stack([np.zeros(n), rng.uniform(0, 2.5, n), rng.uniform(0, 3, n)], axis=1)
    return np.vstack([floor, ceil, wall]) + rng.normal(0, noise, (3 * n, 3))


def test_find_planes_nhan_san_tran_tuong():
    rng = np.random.default_rng(0)
    pts = room_points(rng)
    u = np.array([0.0, 1.0, 0.0])
    planes = gs.find_planes(pts, u, np.array([1.2, 1.3]), tau_r=0.05, tau_n_deg=15, max_planes=5, min_frac=0.05)
    labels = sorted(p["label"] for p in planes)
    assert labels == ["ceiling", "floor", "wall"]
    h = {p["label"]: p["height_m"] for p in planes if p["height_m"] is not None}
    assert h["floor"] == pytest.approx(0.0, abs=0.03) and h["ceiling"] == pytest.approx(2.5, abs=0.03)
    assert gs.label_plane(np.array([0.0, 0.6, 0.8]), 0.0, u, np.array([1.0]), 15)[0] == "other"      # nghiêng 53°


def test_camera_up_va_refine_up_va_xoay_len_y():
    r = np.eye(3)
    cams = {i: {"R": r} for i in range(3)}
    assert np.allclose(gs.camera_up(cams), [0, -1, 0])                                               # −y_cam
    rng = np.random.default_rng(1)
    pts = room_points(rng)
    tilt = np.array([0.0, 1.0, 0.1]) / np.linalg.norm([0.0, 1.0, 0.1])                               # u0 lệch ~5,7° so với pháp tuyến sàn thật
    u, info = gs.refine_up(pts, gs.estimate_normals(pts, 30), tilt, 20.0, 0.05)
    assert info["refined"] and np.degrees(np.arccos(abs(u @ [0, 1, 0]))) < 1.5
    for v in ([0, 1, 0], [0.3, 0.9, 0.1], [0, -1, 0]):
        v = np.array(v, float) / np.linalg.norm(v)
        assert np.allclose(exp.rotation_up_to_y(v) @ v, [0, 1, 0], atol=1e-9)


def synthetic_gate_scene(tmp_path, w_k=0.9):
    lay = pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777")
    rng = np.random.default_rng(2)
    pts = room_points(rng, n=2000, noise=0.01)
    write_ply(lay.fusion / "fused_points.ply", {"x": pts[:, 0].astype(np.float32), "y": pts[:, 1].astype(np.float32), "z": pts[:, 2].astype(np.float32),
                                                 "w_k": np.full(len(pts), w_k, np.float32), "n_views": np.full(len(pts), 3, np.uint8)})
    pio.write_json(lay.alignment / "scale.json", {"s_m": 1.0})
    cams = {i: {"R": np.diag([1.0, -1.0, -1.0]), "center": np.array([2.0, 1.2, 1.5])} for i in range(3)}     # −y_cam = +y thế giới
    return lay, cams


def test_run_gate_keo_diem_qua_cong_ve_mat_phang_va_giu_diem_khong_qua(tmp_path):
    lay, cams = synthetic_gate_scene(tmp_path, w_k=0.9)
    cfg = cfgmod.load_config()
    st = gs.run_gate(lay, cfg, log=lambda m: None, load_cameras=lambda lay_: cams)
    assert st["n_struct_planes"] == 3 and st["frac_gate_pass"] > 0.5
    src = read_ply(lay.fusion / "fused_points.ply")
    out = read_ply(lay.plane_refinement / "refined_points.ply")
    assert len(out["x"]) == len(src["x"])                                                              # không xoá điểm nào
    floor = np.abs(src["y"]) < 0.04
    moved = (out["g"] == 1) & floor
    assert moved.sum() > 500
    assert np.abs(out["y"][moved]).mean() < np.abs(src["y"][moved]).mean() * 0.7                     # α = 0,5: còn khoảng một nửa độ lệch
    assert (np.abs(out["x"] - src["x"])[out["g"] == 0] == 0).all()                                    # điểm không qua cổng giữ nguyên
    low = synthetic_gate_scene(tmp_path / "low", w_k=0.1)
    st2 = gs.run_gate(low[0], cfg, log=lambda m: None, load_cameras=lambda lay_: low[1])
    assert st2["n_gate_pass"] == 0 and st2["condition_pass_fraction"]["w_k>tau_w"] == 0                  # w_k ≤ τ_w: không điểm nào qua
    assert (lay.plane_refinement / "gate_log.csv").read_text(encoding="utf-8").startswith("point,plane_id,label")
    assert json.loads((lay.plane_refinement / "planes.json").read_text(encoding="utf-8"))["structural_plane_ids"]


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def test_orient_towards_cameras():
    pts = np.array([[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]])
    n = np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    out = exp.orient_towards_cameras(pts, n, np.array([[2.0, 0.0, 0.0], [10.0, 0.0, 0.0]]))
    assert out[0].tolist() == [1.0, 0.0, 0.0] and out[1][0] == -1.0            # điểm x=5 gần camera x=2 (bên trái) hơn x=10 → lật
    out = exp.orient_towards_cameras(pts, n, np.array([[-3.0, 0.0, 0.0]]))
    assert out[0][0] < 0 and out[1][0] < 0


def test_run_export_glb_mo_duoc_va_dung_huong_len(tmp_path):
    import trimesh
    lay = pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777")
    rng = np.random.default_rng(3)
    d = rng.normal(size=(4000, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    # elip 4 × 1 × 2 m dài theo trục x, "lên" thật sự là +z (hướng lên u = (0, 0, 1) trong hệ COLMAP × s_m)
    pts = d * np.array([2.0, 0.5, 1.0])
    write_ply(lay.plane_refinement / "refined_points.ply", {"x": pts[:, 0].astype(np.float32), "y": pts[:, 1].astype(np.float32), "z": pts[:, 2].astype(np.float32),
                                                             "w_k": np.ones(len(pts), np.float32), "g": np.zeros(len(pts), np.uint8)})
    pio.write_json(lay.plane_refinement / "planes.json", {"up": [0.0, 0.0, 1.0], "planes": []})
    pio.write_json(lay.alignment / "scale.json", {"s_m": 1.0})
    cams = {0: {"R": np.eye(3), "center": np.zeros(3)}}
    cfg = cfgmod.load_config()
    cfg["export"]["poisson_depth"] = 6
    info = exp.run_export(lay, cfg, log=lambda m: None, load_cameras=lambda lay_: cams)
    m = trimesh.load(lay.export / "model.glb")
    ext = np.asarray(m.extents)
    assert info["n_faces"] > 100 and abs(ext[0] - 4.0) < 0.4 and abs(ext[1] - 2.0) < 0.3 and abs(ext[2] - 1.0) < 0.3     # z (lên) → y của GLB: độ cao 2 m ở trục y
    assert json.loads((lay.export / "measurements.json").read_text(encoding="utf-8"))["up_axis"] == "y"
    with pytest.raises(StageError):
        exp.run_export(pio.scene_layout(tmp_path / "x", "arkitscenes", "1"), cfg, log=lambda m: None, load_cameras=lambda lay_: cams)
