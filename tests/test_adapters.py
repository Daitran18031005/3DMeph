"""Test scripts/adapters.py: AssetReader, Trajectory (nội suy), intrinsics, unproject, PLY Faro theo chunk, voxel streaming.

Phần lớn dùng dữ liệu tổng hợp; một test đọc dữ liệu thật (bỏ qua nếu thiếu `data/raw`).
"""

import importlib.util
import zipfile
from pathlib import Path

import cv2
import numpy as np
import pytest

from pipeline.common import geometry as geo
from pipeline.common import io as pio

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw" / "arkitscenes"


def _load():
    spec = importlib.util.spec_from_file_location("adapters_under_test", REPO / "scripts" / "adapters.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ad = _load()


# ---------------------------------------------------------------------------
# AssetReader
# ---------------------------------------------------------------------------


def _png_bytes(value: int) -> bytes:
    ok, buf = cv2.imencode(".png", np.full((4, 6), value, dtype=np.uint8))
    assert ok
    return buf.tobytes()


def test_asset_reader_dir_and_zip_cho_cung_ket_qua(tmp_path):
    scene = tmp_path / "scene"
    (scene / "lowres_wide").mkdir(parents=True)
    for i, name in enumerate(["7_1.0.png", "7_2.0.png", "notes.txt"]):
        data = _png_bytes(10 * (i + 1)) if name.endswith(".png") else b"x"
        (scene / "lowres_wide" / name).write_bytes(data)
    with zipfile.ZipFile(tmp_path / "scene" / "zipped.zip", "w") as zf:
        zf.writestr("zipped/", b"")  # mục thư mục không được tính
        for name in ["7_1.0.png", "7_2.0.png", "notes.txt"]:
            zf.writestr("zipped/" + name, (scene / "lowres_wide" / name).read_bytes())

    with ad.AssetReader(str(scene), "lowres_wide") as rd, ad.AssetReader(str(scene), "zipped") as rz:
        assert rd.kind == "dir" and rz.kind == "zip"
        assert rd.list_pngs() == ["7_1.0.png", "7_2.0.png"]
        assert [n.split("/")[-1] for n in rz.list_pngs()] == rd.list_pngs()
        assert len(rd.list_entries()) == len(rz.list_entries()) == 3
        a = rd.read("7_2.0.png", cv2.IMREAD_GRAYSCALE)
        b = rz.read("zipped/7_2.0.png", cv2.IMREAD_GRAYSCALE)
        assert np.array_equal(a, b) and a[0, 0] == 20
        assert rz.read_bytes("zipped/notes.txt") == b"x" == rd.read_bytes("notes.txt")


def test_asset_reader_khong_ton_tai(tmp_path):
    rd = ad.AssetReader(str(tmp_path), "khong_co")
    assert not rd.exists() and rd.list_pngs() == [] and rd.read("x.png") is None
    with pytest.raises(FileNotFoundError):
        rd.read_bytes("x.png")


def test_frame_timestamp_va_read_intrinsics(tmp_path):
    assert ad.frame_timestamp("47333462_5201.456.png") == 5201.456
    with zipfile.ZipFile(tmp_path / "intr.zip", "w") as zf:
        zf.writestr("intr/", b"")
        zf.writestr("intr/9_10.5.pincam", "640 480 528.863 528.863 320.591 239.326")
        zf.writestr("intr/9_11.5.pincam", "640 480 529.0 529.0 320.0 240.0")
    with ad.AssetReader(str(tmp_path), "intr") as rd:
        got = ad.read_intrinsics(rd)
    assert set(got) == {10.5, 11.5}
    assert got[10.5]["fx"] == 528.863 and got[10.5]["w"] == 640
    k = ad.intrinsics_matrix(got[10.5])
    assert k[0, 2] == 320.591 and k[1, 2] == 239.326 and k[2, 2] == 1


def test_scale_intrinsics():
    p = {"w": 640, "h": 480, "fx": 528.863, "fy": 528.863, "cx": 320.591, "cy": 239.326}
    q = ad.scale_intrinsics(p, 1920, 1440)
    assert (q["w"], q["h"]) == (1920, 1440)
    assert q["fx"] == pytest.approx(3 * 528.863) and q["cx"] == pytest.approx(3 * 320.591)
    c = ad.scale_intrinsics(p, 1920, 1440, "pixel_center")
    assert c["cx"] == pytest.approx((320.591 + 0.5) * 3 - 0.5) and c["fx"] == q["fx"]
    assert c["cx"] - q["cx"] == pytest.approx(1.0)       # lệch (s−1)/2 = 1 px ở s=3
    with pytest.raises(ValueError):
        ad.scale_intrinsics(p, 1920, 1000)               # khác tỉ lệ khung
    with pytest.raises(ValueError):
        ad.scale_intrinsics(p, 1920, 1440, "la")


# ---------------------------------------------------------------------------
# Trajectory
# ---------------------------------------------------------------------------


def _rows_two_poses():
    """Hai pose: camera quay quanh trục z từ 0° đến 90°, tâm đi từ (0,0,0) đến (2,0,0)."""
    rows = []
    for ts, ang, c in [(10.0, 0.0, [0.0, 0.0, 0.0]), (11.0, np.pi / 2, [2.0, 0.0, 0.0])]:
        r_wc = geo.rodrigues(np.array([0.0, 0.0, ang]))
        r_cw = r_wc.T
        rows.append((ts, r_cw, -r_cw @ np.array(c)))
    return rows


def test_trajectory_chinh_xac_tai_nut_va_giua_hai_nut():
    tr = ad.Trajectory(_rows_two_poses())
    assert len(tr) == 2 and tr.t_min == 10.0 and tr.t_max == 11.0
    assert np.allclose(tr.camera_center(10.0), [0, 0, 0]) and np.allclose(tr.camera_center(11.0), [2, 0, 0])
    mid = tr.pose_wc(10.5)
    assert np.allclose(mid[:3, 3], [1.0, 0.0, 0.0])
    assert np.allclose(mid[:3, :3], geo.rodrigues(np.array([0.0, 0.0, np.pi / 4])), atol=1e-12)   # slerp: 45°
    assert np.allclose(mid[:3, :3] @ mid[:3, :3].T, np.eye(3), atol=1e-12)
    r_cw, t_cw = tr.pose_cw(10.5)
    assert np.allclose(geo.camera_center(r_cw, t_cw), [1.0, 0.0, 0.0])      # (5)
    assert np.allclose(geo.invert_pose(r_cw, t_cw), mid)


def test_trajectory_gan_nhat_va_ngoai_mien_va_max_gap():
    tr = ad.Trajectory(_rows_two_poses())
    near = tr.pose_wc(10.3, interpolate=False)
    assert np.allclose(near[:3, 3], [0, 0, 0])
    assert np.allclose(tr.pose_wc(10.7, interpolate=False)[:3, 3], [2, 0, 0])
    with pytest.raises(ValueError):
        tr.pose_wc(9.9)
    with pytest.raises(ValueError):
        tr.pose_wc(11.1)
    assert tr.gap_at(10.5) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        tr.pose_wc(10.5, max_gap=0.5)
    assert tr.pose_wc(10.5, max_gap=1.5) is not None


def test_trajectory_dau_vao_khong_hop_le():
    with pytest.raises(ValueError):
        ad.Trajectory(_rows_two_poses()[:1])
    rows = _rows_two_poses()
    with pytest.raises(ValueError):
        ad.Trajectory([rows[0], rows[0]])   # timestamp trùng


def test_trajectory_from_file_khop_vi_du_de_cuong(tmp_path):
    line1 = "5201.456 0 0 -1.5708 -1.20 1.65 -1.40"
    line2 = "5201.556 0 0 -1.5708 -1.20 1.65 -1.40"
    f = tmp_path / "a.traj"
    f.write_text(line1 + "\n" + line2 + "\n", encoding="utf-8")
    tr = ad.Trajectory.from_file(f)
    ts, r, t = pio.parse_traj_line(line1)
    assert np.allclose(tr.camera_center(ts), geo.camera_center(r, t))
    assert np.allclose(tr.camera_center(5201.5), geo.camera_center(r, t))     # hai pose giống nhau


# ---------------------------------------------------------------------------
# unproject_depth
# ---------------------------------------------------------------------------


def test_unproject_roi_chieu_lai_khop_pixel():
    k = np.array([[500.0, 0, 320.0], [0, 500.0, 240.0], [0, 0, 1.0]])
    depth = np.zeros((480, 640), dtype=np.uint16)
    depth[100:200, 300:400] = 2500                       # 2,5 m
    depth[10, 10] = 30                                   # 0,03 m: không hợp lệ (6)
    depth[20, 20] = 12000                                # 12 m: không hợp lệ
    r_wc = geo.rodrigues(np.array([0.1, -0.2, 0.3]))
    c = np.array([1.0, 2.0, 0.5])
    t_wc = np.eye(4)
    t_wc[:3, :3], t_wc[:3, 3] = r_wc, c
    pts = ad.unproject_depth(depth, k, t_wc, dtype=np.float64)
    assert len(pts) == 100 * 100
    r_cw = r_wc.T
    pix = geo.project(k, r_cw, -r_cw @ c, pts)
    uu, vv = np.meshgrid(np.arange(300, 400), np.arange(100, 200))
    expect = np.stack([uu.ravel(), vv.ravel()], axis=1)
    order = np.lexsort((pix[:, 0].round(), pix[:, 1].round()))
    order_e = np.lexsort((expect[:, 0], expect[:, 1]))
    assert np.allclose(pix[order], expect[order_e], atol=1e-6)
    cam = (pts - c) @ r_wc
    assert np.allclose(cam[:, 2], 2.5)


def test_unproject_stride_va_opengl_va_offset():
    k = np.array([[400.0, 0, 8.0], [0, 400.0, 6.0], [0, 0, 1.0]])
    depth = np.full((12, 16), 2000, dtype=np.uint16)
    eye = np.eye(4)
    full = ad.unproject_depth(depth, k, eye, dtype=np.float64)
    sub = ad.unproject_depth(depth, k, eye, stride=4, dtype=np.float64)
    assert len(full) == 192 and len(sub) == 3 * 4
    gl = ad.unproject_depth(depth, k, eye, cam_convention="opengl", dtype=np.float64)
    assert np.allclose(gl, full * np.array([1, -1, -1]))
    half = ad.unproject_depth(depth, k, eye, pixel_offset=0.5, dtype=np.float64)
    assert np.allclose(half[:, 0] - full[:, 0], 0.5 / 400 * 2.0)
    with pytest.raises(ValueError):
        ad.unproject_depth(depth, k, eye, cam_convention="x")


# ---------------------------------------------------------------------------
# PLY Faro theo chunk
# ---------------------------------------------------------------------------

FARO_HEADER = (b"ply\nformat binary_little_endian 1.0\ncomment VCGLIB generated\nelement vertex %d\n"
               b"property double x\nproperty double y\nproperty double z\nproperty uchar red\nproperty uchar green\n"
               b"property uchar blue\nproperty uchar alpha\nproperty double quality\nproperty double radius\n"
               b"element face 0\nproperty list uchar int vertex_indices\nend_header\n")
FARO_DTYPE = np.dtype([("x", "<f8"), ("y", "<f8"), ("z", "<f8"), ("r", "u1"), ("g", "u1"), ("b", "u1"), ("a", "u1"),
                       ("q", "<f8"), ("rad", "<f8")])


def _write_faro_like(path: Path, xyz: np.ndarray, header=FARO_HEADER) -> None:
    arr = np.zeros(len(xyz), dtype=FARO_DTYPE)
    arr["x"], arr["y"], arr["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    arr["q"] = 0.5
    path.write_bytes(header % len(xyz) + arr.tobytes())


def test_ply_header_va_chunk(tmp_path):
    rng = np.random.default_rng(0)
    xyz = rng.uniform(-3, 3, (1000, 3)) + np.array([0, 0, 215.77])
    f = tmp_path / "169892.ply"
    _write_faro_like(f, xyz)
    h = ad.read_ply_header(f)
    assert h["n"] == 1000 and h["offset"] == len(FARO_HEADER % 1000) and h["dtype"].itemsize == 44
    chunks = list(ad.iter_ply_xyz(f, chunk=300))
    assert [len(c) for c in chunks] == [300, 300, 300, 100]
    assert np.array_equal(np.concatenate(chunks), xyz)           # float64 giữ nguyên bit


def test_ply_header_khac_332_byte_van_doc_duoc(tmp_path):
    xyz = np.arange(30, dtype=np.float64).reshape(10, 3)
    f = tmp_path / "x.ply"
    _write_faro_like(f, xyz, header=FARO_HEADER.replace(b"VCGLIB generated", b"mot dong ghi chu dai hon nhieu"))
    assert ad.read_ply_header(f)["offset"] != 332
    assert np.array_equal(np.concatenate(list(ad.iter_ply_xyz(f))), xyz)


def test_ply_loi(tmp_path):
    xyz = np.zeros((5, 3))
    f = tmp_path / "cut.ply"
    _write_faro_like(f, xyz)
    f.write_bytes(f.read_bytes()[:-10])                          # cắt cụt
    with pytest.raises(ValueError, match="kích thước"):
        ad.read_ply_header(f)
    g = tmp_path / "face.ply"
    _write_faro_like(g, xyz, header=FARO_HEADER.replace(b"element face 0", b"element face 3"))
    with pytest.raises(ValueError):
        ad.read_ply_header(g)
    h = tmp_path / "ascii.ply"
    h.write_bytes(b"ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\nend_header\n1\n")
    with pytest.raises(ValueError, match="binary_little_endian"):
        ad.read_ply_header(h)
    k = tmp_path / "no.ply"
    k.write_bytes(b"khong phai ply")
    with pytest.raises(ValueError):
        ad.read_ply_header(k)


def test_pose_txt_va_list_scans(tmp_path):
    v = tmp_path / "421267"
    v.mkdir()
    _write_faro_like(v / "169897.ply", np.zeros((3, 3)))
    _write_faro_like(v / "169892.ply", np.ones((4, 3)))
    text = "0.2,0.97,-0.0004,0.0\n-0.97,0.2,0.016,0.0\n0.0158,-0.003,0.9998,0.0\n-0.19,-0.95,215.76,1.0\n"
    for s in ("169892", "169897"):
        (v / f"{s}_pose.txt").write_text(text, encoding="utf-8")
    scans = ad.list_scans(v)
    assert [s["scan_id"] for s in scans] == ["169892", "169897"]
    assert [s["n_points"] for s in scans] == [4, 3]
    assert scans[0]["pose"].shape == (4, 4) and scans[0]["pose"][3, 2] == pytest.approx(215.76)
    (v / "169897_pose.txt").unlink()
    with pytest.raises(FileNotFoundError):
        ad.list_scans(v)
    (v / "bad_pose.txt").write_text("1,2,3\n", encoding="utf-8")
    with pytest.raises(ValueError):
        ad.read_pose_txt(v / "bad_pose.txt")


# ---------------------------------------------------------------------------
# voxel_downsample_stream
# ---------------------------------------------------------------------------


def _brute_force(pts: np.ndarray, voxel: float):
    idx = np.floor(pts / voxel).astype(np.int64)
    out = {}
    for i, key in enumerate(map(tuple, idx)):
        out.setdefault(key, []).append(i)
    return {k: (pts[v].mean(axis=0), len(v)) for k, v in out.items()}


def test_voxel_streaming_bang_brute_force_va_khong_phu_thuoc_chunk():
    rng = np.random.default_rng(1)
    pts = rng.uniform(-2, 2, (5000, 3)) + np.array([0, 0, 215.0])
    voxel = 0.25
    ref = _brute_force(pts, voxel)
    for sizes in ([5000], [1000] * 5, [1, 4999], [777, 1234, 2989]):
        chunks, a = [], 0
        for s in sizes:
            chunks.append(pts[a:a + s])
            a += s
        cen, cnt = ad.voxel_downsample_stream(iter(chunks), voxel)
        assert len(cen) == len(ref) and cnt.sum() == len(pts)
        got = {tuple(np.floor(c / voxel + 1e-9).astype(np.int64)): (c, n) for c, n in zip(cen, cnt)}
        # trọng tâm nằm trong voxel đúng và bằng trung bình các điểm
        for key, (mean, n) in ref.items():
            assert got[key][1] == n
            assert np.allclose(got[key][0], mean, atol=1e-9)


def test_voxel_rong_va_loi():
    cen, cnt = ad.voxel_downsample_stream(iter([]), 0.1)
    assert cen.shape == (0, 3) and cnt.shape == (0,)
    with pytest.raises(ValueError):
        ad.voxel_downsample_stream(iter([np.zeros((1, 3))]), 0.0)
    with pytest.raises(ValueError, match="21 bit"):
        ad.voxel_downsample_stream(iter([np.array([[1e9, 0.0, 0.0]])]), 0.01)


def test_voxel_cung_luoi_giua_cac_lan_goi():
    a = np.array([[0.004, 0.0, 0.0], [0.006, 0.0, 0.0]])   # hai điểm cạnh biên voxel 1 cm
    cen1, _ = ad.voxel_downsample_stream(iter([a[:1]]), 0.01)
    cen2, _ = ad.voxel_downsample_stream(iter([a[1:]]), 0.01)
    cen3, _ = ad.voxel_downsample_stream(iter([a]), 0.01)
    assert len(cen1) == len(cen2) == 1 and len(cen3) == 1       # cùng voxel [0, 0.01)


# ---------------------------------------------------------------------------
# Dữ liệu thật (bỏ qua nếu thiếu)
# ---------------------------------------------------------------------------

DEV = RAW / "Training" / "42444738"
FARO = RAW / "laser_scanner_point_clouds" / "421267"


@pytest.mark.skipif(not (FARO / "169892.ply").is_file(), reason="chưa có Faro visit 421267")
def test_that_faro_header_va_pose():
    scans = ad.list_scans(FARO)
    assert [s["scan_id"] for s in scans] == ["169892", "169895", "169897", "169970", "169973", "169975"]
    n = {s["scan_id"]: s["n_points"] for s in scans}
    assert n["169892"] == 42_348_620 and n["169895"] == 41_467_500 and n["169897"] == 40_935_479
    assert n["169973"] == n["169892"] and n["169970"] == n["169895"] and n["169975"] == n["169897"]
    first = next(ad.iter_ply_xyz(FARO / "169892.ply", chunk=1000))
    assert 214.0 < first[:, 2].min() and first[:, 2].max() < 218.0      # z-up, ~215 m (đã đo)
    assert scans[0]["pose"][3, 2] == pytest.approx(215.7665803)


@pytest.mark.skipif(not (DEV / "lowres_wide.traj").is_file() or not (DEV / "highres_depth.zip").is_file(),
                    reason="chưa có scene dev")
def test_that_trajectory_va_highres():
    tr = ad.Trajectory.from_file(DEV / "lowres_wide.traj")
    assert len(tr) == 595
    with ad.AssetReader(str(DEV), "highres_depth") as rd:
        names = rd.list_pngs()
        assert len(names) == 104          # zip có 105 mục = 104 ảnh + 1 thư mục (PLAN §4.0d ghi "105 khung")
        ts = sorted(ad.frame_timestamp(n) for n in names)
        assert tr.t_min <= ts[0] and ts[-1] <= tr.t_max
        t_wc = tr.pose_wc(ts[10])
        assert np.allclose(t_wc[:3, :3] @ t_wc[:3, :3].T, np.eye(3), atol=1e-9)
        img = rd.read(names[0])
        assert img.shape == (1440, 1920) and img.dtype == np.uint16
