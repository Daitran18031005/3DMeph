"""
adapters.py — giao diện đọc dữ liệu thô ARKitScenes + Faro dùng chung (kế hoạch §4.0d; M1 chuyển từ `scripts/` sang gói `pipeline`).

Gom `AssetReader` từng bị chép ở `validate_dataset.py` và `explore_dataset.py`, thêm:
  - `Trajectory`: pose `.traj` (world→camera) có nội suy theo thời gian; tâm camera theo (5)
  - đọc intrinsics `.pincam`, đổi tỉ lệ cho ảnh độ phân giải khác (vd. `highres_depth` 1920×1440)
  - `unproject_depth`: depth (mm) → điểm world (m), depth hợp lệ theo (6)
  - đọc PLY nhị phân của Faro theo chunk (RAM máy chỉ 15,7 GB, mỗi scan Faro 1,7–1,9 GB), voxel hoá streaming

Chỉ ĐỌC dữ liệu; không giải nén, không ghi vào `data/raw`. Quy ước camera OpenCV (x phải, y xuống, z tới) đã kiểm bằng dữ liệu
(`faro_align.py`: khoảng cách tới mesh ARKit trung vị 2,84 cm với OpenCV, 39 cm với OpenGL). `scripts/adapters.py` chỉ còn là lớp chuyển tiếp.
"""

from __future__ import annotations

import math
import os
import zipfile
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from scipy.spatial.transform import Rotation, Slerp

from . import geometry as geo
from . import io as pio

# ---------------------------------------------------------------------------
# Đọc asset ARKitScenes (thư mục đã giải nén hoặc zip)
# ---------------------------------------------------------------------------


class AssetReader:
    """Đọc file bên trong 1 asset ARKitScenes, hỗ trợ cả thư mục đã giải nén lẫn file .zip chưa giải nén
    (tên hiển thị có thể không có đuôi .zip trên Windows). Dùng qua `with` để tự đóng zip."""

    def __init__(self, scene_dir, asset_name):
        self.kind: Optional[str] = None   # "dir" | "zip" | None
        self.zf: Optional[zipfile.ZipFile] = None
        self.dir_path: Optional[str] = None

        dir_path = os.path.join(scene_dir, asset_name)
        if os.path.isdir(dir_path):
            self.kind = "dir"
            self.dir_path = dir_path
            return

        candidates = [dir_path if dir_path.lower().endswith(".zip") else dir_path + ".zip", dir_path]
        for c in candidates:
            if os.path.isfile(c) and zipfile.is_zipfile(c):
                self.kind = "zip"
                self.zf = zipfile.ZipFile(c)
                return

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def exists(self) -> bool:
        return self.kind is not None

    def list_entries(self) -> List[str]:
        """Tất cả file bên trong (không tính mục thư mục), không lọc đuôi — dùng để đếm."""
        if self.kind == "dir":
            return sorted(f for f in os.listdir(self.dir_path) if os.path.isfile(os.path.join(self.dir_path, f)))
        if self.kind == "zip":
            return sorted(n for n in self.zf.namelist() if not n.endswith("/"))
        return []

    def list_pngs(self) -> List[str]:
        return [f for f in self.list_entries() if f.lower().endswith(".png")]

    def read_bytes(self, entry: str) -> bytes:
        if self.kind == "dir":
            with open(os.path.join(self.dir_path, entry), "rb") as f:
                return f.read()
        if self.kind == "zip":
            return self.zf.read(entry)
        raise FileNotFoundError(f"asset không tồn tại: {entry}")

    def read(self, entry, flags=cv2.IMREAD_UNCHANGED):
        if self.kind == "dir":
            return cv2.imread(os.path.join(self.dir_path, entry), flags)
        if self.kind == "zip":
            arr = np.frombuffer(self.zf.read(entry), dtype=np.uint8)
            return cv2.imdecode(arr, flags)
        return None

    def close(self):
        if self.zf is not None:
            self.zf.close()


def frame_timestamp(name: str) -> float:
    """Thời gian (s) của một khung từ tên file: '42444738_77951.184.png' → 77951.184 (frame_id, ĐC §10.2)."""
    return float(pio.frame_id_from_name(name))


def read_intrinsics(reader: AssetReader) -> Dict[float, Dict[str, float]]:
    """Mọi `.pincam` trong asset intrinsics → {timestamp: {w,h,fx,fy,cx,cy}}."""
    out: Dict[float, Dict[str, float]] = {}
    for entry in reader.list_entries():
        if entry.lower().endswith(".pincam"):
            out[frame_timestamp(entry)] = pio.parse_pincam(reader.read_bytes(entry).decode("utf-8"))
    return out


def intrinsics_matrix(p: Dict[str, float]) -> np.ndarray:
    """dict pincam → ma trận K 3×3."""
    return np.array([[p["fx"], 0.0, p["cx"]], [0.0, p["fy"], p["cy"]], [0.0, 0.0, 1.0]])


def scale_intrinsics(p: Dict[str, float], w: int, h: int, convention: str = "proportional") -> Dict[str, float]:
    """Đổi intrinsics sang ảnh cùng tỉ lệ khung nhưng kích thước khác (vd. 640×480 → 1920×1440 của `highres_depth`).

    `proportional`: f' = f·s, c' = c·s (toạ độ liên tục, mép ảnh ở số nguyên).
    `pixel_center`: c' = (c + 0,5)·s − 0,5 (chỉ số pixel là tâm pixel).
    Hai kiểu lệch nhau tối đa (s−1)/2 = 1 px ở s=3. Tỉ lệ x và y phải bằng nhau (cùng tỉ lệ khung)."""
    sx, sy = w / p["w"], h / p["h"]
    if abs(sx - sy) > 1e-9:
        raise ValueError(f"tỉ lệ khung khác nhau: {p['w']}x{p['h']} → {w}x{h}")
    if convention == "proportional":
        cx, cy = p["cx"] * sx, p["cy"] * sy
    elif convention == "pixel_center":
        cx, cy = (p["cx"] + 0.5) * sx - 0.5, (p["cy"] + 0.5) * sy - 0.5
    else:
        raise ValueError(f"convention không hợp lệ: {convention!r}")
    return {"w": w, "h": h, "fx": p["fx"] * sx, "fy": p["fy"] * sy, "cx": cx, "cy": cy}


# ---------------------------------------------------------------------------
# Quỹ đạo camera (.traj) có nội suy
# ---------------------------------------------------------------------------


class Trajectory:
    """Pose camera từ `.traj` (ARKitScenes: world→camera, ~10 Hz). Nội suy: slerp cho xoay camera→world,
    tuyến tính cho tâm camera (tâm camera = −Rᵀt, công thức (5)); đúng tại các nút.

    Khung RGB/depth không trùng thời điểm pose (vd. `highres_depth` cách pose gần nhất 0,033–0,05 s), nên mặc định nội suy."""

    def __init__(self, rows: Sequence[Tuple[float, np.ndarray, np.ndarray]]):
        if len(rows) < 2:
            raise ValueError("quỹ đạo cần ít nhất 2 pose")
        rows = sorted(rows, key=lambda r: r[0])
        self.ts = np.array([r[0] for r in rows], dtype=np.float64)
        if np.any(np.diff(self.ts) <= 0):
            raise ValueError("timestamp .traj phải tăng nghiêm ngặt")
        self.r_cw = np.stack([np.asarray(r[1], dtype=np.float64) for r in rows])
        self.t_cw = np.stack([np.asarray(r[2], dtype=np.float64).reshape(3) for r in rows])
        self.r_wc = np.transpose(self.r_cw, (0, 2, 1))
        self.centers = -np.einsum("nij,nj->ni", self.r_wc, self.t_cw)
        self._slerp = Slerp(self.ts, Rotation.from_matrix(self.r_wc))

    @classmethod
    def from_file(cls, path: os.PathLike) -> "Trajectory":
        return cls(pio.read_traj(path))

    def __len__(self) -> int:
        return len(self.ts)

    @property
    def t_min(self) -> float:
        return float(self.ts[0])

    @property
    def t_max(self) -> float:
        return float(self.ts[-1])

    def nearest_index(self, ts: float) -> int:
        return int(np.argmin(np.abs(self.ts - ts)))

    def gap_at(self, ts: float) -> float:
        """Khoảng cách thời gian giữa hai pose bao quanh ts (s); 0 nếu ts trùng một nút ở biên."""
        self._check_range(ts)
        i = min(max(int(np.searchsorted(self.ts, ts, side="right")) - 1, 0), len(self.ts) - 2)
        return float(self.ts[i + 1] - self.ts[i])

    def _check_range(self, ts: float) -> None:
        if not (self.t_min <= ts <= self.t_max):
            raise ValueError(f"timestamp {ts} ngoài quỹ đạo [{self.t_min}, {self.t_max}]")

    def pose_wc(self, ts: float, interpolate: bool = True, max_gap: Optional[float] = None) -> np.ndarray:
        """Ma trận 4×4 camera→world tại ts. `interpolate=False` lấy pose gần nhất (để so sánh).
        `max_gap` (s): nếu hai pose bao quanh cách nhau hơn thì `ValueError` (tránh nội suy qua khoảng mất pose)."""
        self._check_range(ts)
        t_wc = np.eye(4)
        if not interpolate:
            i = self.nearest_index(ts)
            t_wc[:3, :3], t_wc[:3, 3] = self.r_wc[i], self.centers[i]
            return t_wc
        gap = self.gap_at(ts)
        if max_gap is not None and gap > max_gap:
            raise ValueError(f"khoảng trống pose {gap:.3f} s quanh {ts} lớn hơn max_gap {max_gap}")
        i = min(max(int(np.searchsorted(self.ts, ts, side="right")) - 1, 0), len(self.ts) - 2)
        a = (ts - self.ts[i]) / (self.ts[i + 1] - self.ts[i])
        t_wc[:3, :3] = self._slerp([ts]).as_matrix()[0]
        t_wc[:3, 3] = (1 - a) * self.centers[i] + a * self.centers[i + 1]
        return t_wc

    def pose_cw(self, ts: float, interpolate: bool = True, max_gap: Optional[float] = None) -> Tuple[np.ndarray, np.ndarray]:
        """(R_cw, t_cw) world→camera tại ts (nghịch đảo của `pose_wc`)."""
        t_wc = self.pose_wc(ts, interpolate, max_gap)
        r_cw = t_wc[:3, :3].T
        return r_cw, -r_cw @ t_wc[:3, 3]

    def camera_center(self, ts: float, interpolate: bool = True) -> np.ndarray:
        return self.pose_wc(ts, interpolate)[:3, 3]


# ---------------------------------------------------------------------------
# Depth → điểm world
# ---------------------------------------------------------------------------


def unproject_depth(depth_mm: np.ndarray, k: np.ndarray, t_wc: np.ndarray, stride: int = 1,
                    lo: float = 0.05, hi: float = 10.0, cam_convention: str = "opencv",
                    pixel_offset: float = 0.0, dtype=np.float32) -> np.ndarray:
    """Depth uint16 (mm) → điểm world (m), shape (n, 3). Chỉ lấy depth hợp lệ 0,05 ≤ D ≤ 10 m (6).

    k: K 3×3; t_wc: camera→world 4×4; stride: bước pixel; pixel_offset cộng vào (u, v) = (cột, hàng) trước khi chiếu ngược
    (0 = chỉ số pixel là toạ độ, 0,5 = tâm pixel). `cam_convention`: `opencv` (x phải, y xuống, z tới) hoặc `opengl`
    (x phải, y lên, z lùi: điểm camera = (X, −Y, −Z))."""
    if cam_convention not in ("opencv", "opengl"):
        raise ValueError(f"cam_convention không hợp lệ: {cam_convention!r}")
    d = np.asarray(depth_mm)[::stride, ::stride].astype(np.float64) / 1000.0
    rows = np.arange(0, depth_mm.shape[0], stride, dtype=np.float64)
    cols = np.arange(0, depth_mm.shape[1], stride, dtype=np.float64)
    uu, vv = np.meshgrid(cols + pixel_offset, rows + pixel_offset)
    ok = geo.valid_depth(d, lo, hi)
    z = d[ok]
    x = (uu[ok] - k[0, 2]) / k[0, 0] * z
    y = (vv[ok] - k[1, 2]) / k[1, 1] * z
    cam = np.stack([x, y, z], axis=1)
    if cam_convention == "opengl":
        cam = cam * np.array([1.0, -1.0, -1.0])
    world = cam @ np.asarray(t_wc)[:3, :3].T + np.asarray(t_wc)[:3, 3]
    return world.astype(dtype, copy=False)


# ---------------------------------------------------------------------------
# PLY nhị phân của Faro, đọc theo chunk
# ---------------------------------------------------------------------------

_PLY_TYPES = {"char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1", "short": "<i2", "int16": "<i2",
              "ushort": "<u2", "uint16": "<u2", "int": "<i4", "int32": "<i4", "uint": "<u4", "uint32": "<u4",
              "float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8"}


def read_ply_header(path: os.PathLike) -> Dict:
    """Header PLY nhị phân little-endian chỉ có element `vertex` (và `face` rỗng).

    Trả về {n, offset, dtype, names}. Kiểm `offset + n×itemsize == kích thước file`; lệch thì `ValueError`
    (không đoán, vd. PLY có mặt tam giác)."""
    with open(path, "rb") as f:
        head = f.read(8192)
    end = head.find(b"end_header")
    if end < 0:
        raise ValueError(f"{path}: không thấy end_header trong 8 KB đầu")
    nl = head.index(b"\n", end) + 1
    lines = head[:nl].decode("ascii", errors="replace").splitlines()
    if not lines or lines[0].strip() != "ply":
        raise ValueError(f"{path}: không phải PLY")
    if "format binary_little_endian 1.0" not in lines:
        raise ValueError(f"{path}: chỉ hỗ trợ binary_little_endian")
    n, cur, fields, face_n = None, None, [], 0
    for ln in lines:
        p = ln.split()
        if len(p) >= 3 and p[0] == "element":
            cur = p[1]
            if cur == "vertex":
                n = int(p[2])
            elif cur == "face":
                face_n = int(p[2])
        elif len(p) == 3 and p[0] == "property" and cur == "vertex":
            if p[1] not in _PLY_TYPES:
                raise ValueError(f"{path}: kiểu thuộc tính không hỗ trợ: {p[1]}")
            fields.append((p[2], _PLY_TYPES[p[1]]))
    if n is None or not fields:
        raise ValueError(f"{path}: thiếu element vertex")
    dtype = np.dtype(fields)
    size = os.path.getsize(path)
    if face_n or nl + n * dtype.itemsize != size:
        raise ValueError(f"{path}: header ({nl} B) + {n}×{dtype.itemsize} B = {nl + n * dtype.itemsize} ≠ kích thước file {size} "
                         f"(face={face_n})")
    return {"n": n, "offset": nl, "dtype": dtype, "names": [f[0] for f in fields]}


def iter_ply_xyz(path: os.PathLike, chunk: int = 2_000_000) -> Iterator[np.ndarray]:
    """Sinh từng chunk toạ độ xyz (float64, (m, 3)) của PLY, không nạp cả file (memmap)."""
    h = read_ply_header(path)
    mm = np.memmap(path, dtype=h["dtype"], mode="r", offset=h["offset"], shape=(h["n"],))
    try:
        for a in range(0, h["n"], chunk):
            blk = mm[a:a + chunk]
            yield np.stack([blk["x"], blk["y"], blk["z"]], axis=1).astype(np.float64)
    finally:
        del mm


def iter_ply_xyz_rgb(path: os.PathLike, chunk: int = 2_000_000) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
    """Như `iter_ply_xyz` nhưng kèm màu: sinh (xyz float64 (m, 3), rgb uint8 (m, 3)). PLY phải có thuộc tính red, green, blue."""
    h = read_ply_header(path)
    missing = [n for n in ("red", "green", "blue") if n not in h["names"]]
    if missing:
        raise ValueError(f"{path}: thiếu thuộc tính màu {missing}")
    mm = np.memmap(path, dtype=h["dtype"], mode="r", offset=h["offset"], shape=(h["n"],))
    try:
        for a in range(0, h["n"], chunk):
            blk = mm[a:a + chunk]
            yield (np.stack([blk["x"], blk["y"], blk["z"]], axis=1).astype(np.float64),
                   np.stack([blk["red"], blk["green"], blk["blue"]], axis=1).astype(np.uint8))
    finally:
        del mm


def read_pose_txt(path: os.PathLike) -> np.ndarray:
    """`<scan>_pose.txt` → (4, 4) đúng như lưu (4 dòng × 4 số, tịnh tiến ở dòng cuối: kiểu vector hàng).
    Ý nghĩa với `.ply` [chưa kiểm chứng]; `faro_align.py` kiểm bằng dữ liệu."""
    rows = [[float(v) for v in ln.split(",")] for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]
    m = np.array(rows, dtype=np.float64)
    if m.shape != (4, 4):
        raise ValueError(f"{path}: cần ma trận 4×4, nhận {m.shape}")
    return m


def list_scans(visit_dir: os.PathLike) -> List[Dict]:
    """Các scan Faro trong thư mục visit: [{scan_id, ply, pose_txt, pose, n_points}], theo scan_id tăng.
    Mỗi `.ply` phải có `_pose.txt` (thiếu thì `FileNotFoundError`)."""
    visit_dir = Path(visit_dir)
    out = []
    for ply in sorted(visit_dir.glob("*.ply"), key=lambda p: int(p.stem) if p.stem.isdigit() else p.stem):
        pose_txt = ply.with_name(ply.stem + "_pose.txt")
        if not pose_txt.is_file():
            raise FileNotFoundError(f"thiếu {pose_txt.name}")
        out.append({"scan_id": ply.stem, "ply": ply, "pose_txt": pose_txt, "pose": read_pose_txt(pose_txt),
                    "n_points": read_ply_header(ply)["n"]})
    return out


# ---------------------------------------------------------------------------
# Voxel hoá streaming
# ---------------------------------------------------------------------------

_KEY_BITS = 21
_KEY_OFFSET = 1 << (_KEY_BITS - 1)


def _voxel_keys(pts: np.ndarray, voxel: float, origin: np.ndarray) -> np.ndarray:
    idx = np.floor((pts - origin) / voxel).astype(np.int64) + _KEY_OFFSET
    if idx.min() < 0 or idx.max() >= (1 << _KEY_BITS):
        raise ValueError("chỉ số voxel vượt 21 bit: tăng kích thước voxel hoặc dời origin")
    return (idx[:, 0] << (2 * _KEY_BITS)) | (idx[:, 1] << _KEY_BITS) | idx[:, 2]


def voxel_downsample_stream(chunks: Iterable[np.ndarray], voxel: float, origin: Optional[np.ndarray] = None
                            ) -> Tuple[np.ndarray, np.ndarray]:
    """Voxel hoá luồng các chunk (m, 3): mỗi voxel cạnh `voxel` cho một điểm = trọng tâm các điểm rơi vào nó.

    Trả về (centroid float64 (n, 3), đếm int64 (n,)). Thứ tự theo khoá voxel tăng. `origin` mặc định = (0,0,0),
    nên cùng `voxel` cho cùng lưới ở mọi lần gọi (voxel của các scan khác nhau trùng khớp)."""
    if voxel <= 0:
        raise ValueError("voxel phải > 0")
    origin = np.zeros(3) if origin is None else np.asarray(origin, dtype=np.float64)
    acc_key = np.empty(0, dtype=np.int64)
    acc_sum = np.empty((0, 3))
    acc_cnt = np.empty(0, dtype=np.int64)
    for pts in chunks:
        pts = np.asarray(pts, dtype=np.float64)
        if len(pts) == 0:
            continue
        keys = _voxel_keys(pts, voxel, origin)
        ukeys, inv = np.unique(keys, return_inverse=True)
        sums = np.stack([np.bincount(inv, weights=pts[:, a], minlength=len(ukeys)) for a in range(3)], axis=1)
        cnts = np.bincount(inv, minlength=len(ukeys)).astype(np.int64)
        all_key = np.concatenate([acc_key, ukeys])
        all_sum = np.concatenate([acc_sum, sums])
        all_cnt = np.concatenate([acc_cnt, cnts])
        acc_key, inv2 = np.unique(all_key, return_inverse=True)
        acc_sum = np.stack([np.bincount(inv2, weights=all_sum[:, a], minlength=len(acc_key)) for a in range(3)], axis=1)
        acc_cnt = np.bincount(inv2, weights=all_cnt, minlength=len(acc_key)).astype(np.int64)
    if len(acc_key) == 0:
        return np.empty((0, 3)), np.empty(0, dtype=np.int64)
    return acc_sum / acc_cnt[:, None], acc_cnt


def voxel_downsample_attr_stream(chunks: Iterable[Tuple[np.ndarray, np.ndarray]], voxel: float,
                                 origin: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Như `voxel_downsample_stream` nhưng mỗi chunk là (xyz (m, 3), thuộc tính (m, k)); trả về
    (centroid (n, 3), trung bình thuộc tính (n, k), đếm (n,)). Dùng để lấy màu trung bình mỗi voxel."""
    if voxel <= 0:
        raise ValueError("voxel phải > 0")
    origin = np.zeros(3) if origin is None else np.asarray(origin, dtype=np.float64)
    acc_key = np.empty(0, dtype=np.int64)
    acc_sum = None
    acc_cnt = np.empty(0, dtype=np.int64)
    k_attr = None
    for pts, attr in chunks:
        pts = np.asarray(pts, dtype=np.float64)
        attr = np.asarray(attr, dtype=np.float64)
        if len(pts) == 0:
            continue
        if attr.shape[0] != pts.shape[0]:
            raise ValueError("xyz và thuộc tính khác số dòng")
        k_attr = attr.shape[1]
        both = np.concatenate([pts, attr], axis=1)
        keys = _voxel_keys(pts, voxel, origin)
        ukeys, inv = np.unique(keys, return_inverse=True)
        sums = np.stack([np.bincount(inv, weights=both[:, a], minlength=len(ukeys)) for a in range(both.shape[1])], axis=1)
        cnts = np.bincount(inv, minlength=len(ukeys)).astype(np.int64)
        if acc_sum is None:
            acc_sum = np.empty((0, both.shape[1]))
        all_key = np.concatenate([acc_key, ukeys])
        all_sum = np.concatenate([acc_sum, sums])
        all_cnt = np.concatenate([acc_cnt, cnts])
        acc_key, inv2 = np.unique(all_key, return_inverse=True)
        acc_sum = np.stack([np.bincount(inv2, weights=all_sum[:, a], minlength=len(acc_key)) for a in range(all_sum.shape[1])], axis=1)
        acc_cnt = np.bincount(inv2, weights=all_cnt, minlength=len(acc_key)).astype(np.int64)
    if len(acc_key) == 0:
        return np.empty((0, 3)), np.empty((0, k_attr or 0)), np.empty(0, dtype=np.int64)
    mean = acc_sum / acc_cnt[:, None]
    return mean[:, :3], mean[:, 3:], acc_cnt


# ---------------------------------------------------------------------------
# Video điện thoại (mp4/MOV) làm nguồn RGB cho dữ liệu tự thu
# ---------------------------------------------------------------------------

VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v")
_DIAG_35MM = 43.27   # mm: đường chéo phim 36×24; tiêu cự "tương đương 35 mm" quy ước theo đường chéo


class VideoSource:
    """Đọc video bằng OpenCV, giữ ảnh ở hướng cảm biến (tắt tự xoay) để `keyframe.orientation` xoay và cập nhật intrinsics.

    `rotation_deg` ∈ {0, 90, 180, 270}: góc xoay THEO CHIỀU KIM ĐỒNG HỒ để ảnh đứng (tag rotation của video, thay `sky_direction`).
    Hai lượt đọc tuần tự: `timestamps()` (grab hết, rẻ hơn decode đầy đủ) rồi `read_frames(indices)` (không seek vì seek theo khung
    không chính xác với nhiều codec). [chưa kiểm chứng trên video điện thoại thật]"""

    def __init__(self, path):
        self.path = str(path)
        self.cap = None
        self._open()
        self.rotation_deg = int(round(self.cap.get(cv2.CAP_PROP_ORIENTATION_META))) % 360
        self.fps_meta = float(self.cap.get(cv2.CAP_PROP_FPS))
        self.ts_from_meta = False        # True khi timestamp của container không dùng được và phải suy từ fps

    def _open(self) -> None:
        self.close()
        cap = cv2.VideoCapture(self.path)
        if not cap.isOpened():
            cap.release()
            raise FileNotFoundError(f"không mở được video: {self.path}")
        cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 0)
        self.cap = cap

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def timestamps(self) -> np.ndarray:
        """Thời gian (s) từng khung theo thứ tự giải mã. Timestamp container không tăng nghiêm ngặt (hoặc toàn 0) thì suy từ fps
        của metadata (`ts_from_meta = True`); fps metadata cũng không có thì `ValueError`."""
        self._open()
        ts = []
        while self.cap.grab():
            ts.append(self.cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0)
        ts = np.asarray(ts, dtype=np.float64)
        if len(ts) == 0:
            raise ValueError(f"video không có khung nào: {self.path}")
        if len(ts) > 1 and np.any(np.diff(ts) <= 0):
            if self.fps_meta <= 0:
                raise ValueError(f"timestamp video không tăng và không có fps trong metadata: {self.path}")
            self.ts_from_meta = True
            ts = np.arange(len(ts)) / self.fps_meta
        return ts

    def read_frames(self, indices: Iterable[int], transform=None) -> Dict[int, np.ndarray]:
        """Giải mã tuần tự và trả {chỉ số khung: ảnh BGR}. `transform(img)` (nếu có) áp ngay khi đọc để không giữ ảnh cỡ gốc trong RAM."""
        want = sorted(set(int(i) for i in indices))
        out: Dict[int, np.ndarray] = {}
        if not want:
            return out
        self._open()
        wanted = set(want)
        for i in range(want[-1] + 1):
            if not self.cap.grab():
                break
            if i in wanted:
                ok, img = self.cap.retrieve()
                if ok:
                    out[i] = transform(img) if transform is not None else img
        missing = wanted - out.keys()
        if missing:
            raise ValueError(f"không đọc được {len(missing)} khung (vd. {min(missing)}) trong {self.path}")
        return out


def estimate_intrinsics(w: int, h: int, focal35_mm: float) -> Dict[str, float]:
    """Intrinsics khởi tạo cho video không có `.pincam`: f = focal35·√(w²+h²)/43,27 (px), fx = fy = f, tâm ở giữa ảnh.
    [Suy luận] chỉ là điểm xuất phát cho PINHOLE của COLMAP (COLMAP tinh chỉnh tiêu cự); ảnh đã xoay thì truyền w, h sau xoay."""
    if focal35_mm <= 0:
        raise ValueError("focal35_mm phải > 0")
    f = focal35_mm * math.hypot(w, h) / _DIAG_35MM
    return {"w": int(w), "h": int(h), "fx": f, "fy": f, "cx": w / 2.0, "cy": h / 2.0}


__all__ = ["AssetReader", "frame_timestamp", "read_intrinsics", "intrinsics_matrix", "scale_intrinsics", "Trajectory",
           "unproject_depth", "read_ply_header", "iter_ply_xyz", "iter_ply_xyz_rgb", "read_pose_txt", "list_scans", "voxel_downsample_stream",
           "voxel_downsample_attr_stream", "VIDEO_EXTENSIONS", "VideoSource", "estimate_intrinsics"]
