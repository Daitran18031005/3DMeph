#!/usr/bin/env python3
"""
annotate_segments.py — chấm đầu mút 1 mốc scale + các đoạn test trên point cloud Faro đã căn (kế hoạch §4.0d, ĐC §8, §9).

Người dùng tự chọn đầu mút bằng cửa sổ Open3D; script KHÔNG tự chọn đoạn. Mỗi đoạn lưu ngay vào
`ground_truth/annotation_session.json` (đóng ngang không mất). `--finalize` kiểm luật rồi mới ghi:
  ground_truth/measurements.csv   cột `id,type,ground_truth_m,used_as_anchor,endpoints/notes` [ĐC §9]
  ground_truth/scale_anchor.json  đoạn mốc 1–2 m (`used_as_anchor=1`), bị loại khỏi chỉ số test [ĐC §8.1]

Cách dùng (từ thư mục gốc repo, env 3d_metric):
    python scripts/annotate_segments.py --scene arkitscenes/42444738 --view       # chỉ xem point cloud
    python scripts/annotate_segments.py --scene arkitscenes/42444738              # chấm từng đoạn (tương tác)
    python scripts/annotate_segments.py --scene arkitscenes/42444738 --check      # kiểm luật trên phiên hiện có
    python scripts/annotate_segments.py --scene arkitscenes/42444738 --finalize   # ghi measurements.csv + scale_anchor.json
    python scripts/annotate_segments.py --scene arkitscenes/42444738 --from-json doan.json   # nạp toạ độ không GUI

Luật kiểm (cấu trúc, không phải ngưỡng sai số): đúng 1 mốc, dài 1–2 m, đã xác nhận không nằm trên gương/kính; ≥ 12 đoạn test (12–20 theo ĐC §8.2);
id không trùng; hai đầu mút một đoạn khác nhau; đầu mút mốc không trùng hoặc gần (≤ `eval.snap_radius_m`) đầu mút đoạn test.

Mã thoát: 0 ok; 1 lỗi đầu vào (scene held-out, thiếu faro_to_scene.json...); 2 không đạt luật kiểm.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import pipeline  # noqa: E402,F401  (import torch trước cv2/open3d/pycolmap)

# isort: split
import adapters  # noqa: E402
import faro_align  # noqa: E402
import faro_registration as frs  # noqa: E402
import numpy as np  # noqa: E402

from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402

CSV_COLUMNS = ["id", "type", "ground_truth_m", "used_as_anchor", "endpoints/notes"]
ROLES = ("anchor", "test")
SEGMENT_TYPES = ("main_dimension", "door_window", "local_distance", "diagonal", "other")   # nhóm gợi ý theo ĐC §8.2 [Suy luận]
ANCHOR_RANGE_M = (1.0, 2.0)          # ĐC §8.1: mốc 1–2 m
TEST_COUNT_RANGE = (12, 20)          # ĐC §8.2: 12–20 đoạn test; < 12 là lỗi (tiêu chí M0b), > 20 chỉ cảnh báo
SHORT_SEGMENT_WARN_M = 0.2           # đoạn ngắn hơn khó phân biệt với sai số click (cảnh báo, không chặn)
DEFAULT_DISPLAY_VOXEL = 0.01
SCENE_PLY_NAME = "faro_scene_frame.ply"
RGB_PLY_NAME = "faro_display_rgb.ply"


class AnnotationError(ValueError):
    """Dữ liệu chấm không hợp lệ."""


# ---------------------------------------------------------------------------
# Đường dẫn, phiên
# ---------------------------------------------------------------------------


class Paths:
    def __init__(self, gt_dir: Path):
        self.gt = Path(gt_dir)
        self.faro = self.gt / "faro"
        self.f2s = self.faro / "faro_to_scene.json"
        self.ply = self.faro / SCENE_PLY_NAME
        self.rgb_ply = self.faro / RGB_PLY_NAME
        self.rgb_meta = self.faro / "faro_display_rgb.json"
        self.session = self.gt / "annotation_session.json"
        self.csv = self.gt / "measurements.csv"
        self.anchor = self.gt / "scale_anchor.json"


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_alignment(paths: Paths) -> Dict:
    """Cần bản căn chính thức (đã `--commit`); trả về nội dung `faro_to_scene.json`."""
    if not paths.f2s.is_file() or not paths.ply.is_file():
        raise AnnotationError(f"chưa có {paths.f2s.name} / {paths.ply.name}: chạy scripts/faro_align.py và --commit trước")
    d = json.loads(paths.f2s.read_text(encoding="utf-8"))
    if d.get("status") != "committed":
        raise AnnotationError(f"{paths.f2s.name} có status {d.get('status')!r}, cần 'committed'")
    return d


def new_session(scene: str, f2s_sha: str, voxel: float) -> Dict:
    return {"scene": scene, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "faro_to_scene_sha256": f2s_sha,
            "display_voxel_m": voxel, "frame": "scene (ARKit), mét", "segments": []}


def load_session(paths: Paths) -> Optional[Dict]:
    if not paths.session.is_file():
        return None
    return json.loads(paths.session.read_text(encoding="utf-8"))


def save_session(paths: Paths, sess: Dict) -> None:
    """Ghi nguyên tử (ghi file tạm rồi thay) để đóng ngang không làm hỏng phiên."""
    paths.session.parent.mkdir(parents=True, exist_ok=True)
    tmp = paths.session.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(sess, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, paths.session)


def check_session_alignment(sess: Dict, f2s_sha: str) -> None:
    if sess.get("faro_to_scene_sha256") != f2s_sha:
        raise AnnotationError("faro_to_scene.json đã đổi sau khi bắt đầu chấm (hash khác): toạ độ đầu mút cũ có thể sai hệ; "
                              "xoá phiên cũ hoặc chấm lại")


# ---------------------------------------------------------------------------
# Đoạn và luật kiểm
# ---------------------------------------------------------------------------


def segment_length(a: Sequence[float], b: Sequence[float]) -> float:
    return float(np.linalg.norm(np.asarray(b, dtype=np.float64) - np.asarray(a, dtype=np.float64)))   # (30)


def make_segment(seg_id: str, role: str, seg_type: str, a: Sequence[float], b: Sequence[float], label: str = "", notes: str = "",
                 uncertainty_m: float = DEFAULT_DISPLAY_VOXEL, a_index: Optional[int] = None, b_index: Optional[int] = None,
                 confirmed_not_glass: Optional[bool] = None, display: str = SCENE_PLY_NAME) -> Dict:
    a = [float(v) for v in a]
    b = [float(v) for v in b]
    seg = {"id": seg_id, "role": role, "type": seg_type, "label": label, "notes": notes, "a": a, "b": b,
           "length_m": round(segment_length(a, b), 4), "endpoint_uncertainty_m": uncertainty_m,
           "a_index": a_index, "b_index": b_index, "display_file": display, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if role == "anchor":
        seg["confirmed_not_on_glass_or_moving"] = bool(confirmed_not_glass)
    return seg


def validate_segments(segments: List[Dict], snap_radius_m: float, test_min: int = TEST_COUNT_RANGE[0],
                      test_max: int = TEST_COUNT_RANGE[1]) -> Tuple[List[str], List[str]]:
    """Trả về (lỗi, cảnh báo). Lỗi chặn `--finalize`; chỉ kiểm cấu trúc theo ĐC §8 và kế hoạch, không đặt ngưỡng sai số."""
    errors: List[str] = []
    warns: List[str] = []
    ids = [s["id"] for s in segments]
    for i in {x for x in ids if ids.count(x) > 1}:
        errors.append(f"id trùng: {i}")
    anchors = [s for s in segments if s["role"] == "anchor"]
    tests = [s for s in segments if s["role"] == "test"]
    for s in segments:
        if s["role"] not in ROLES:
            errors.append(f"{s['id']}: role {s['role']!r} không hợp lệ (anchor/test)")
        if not str(s.get("type", "")).strip():
            errors.append(f"{s['id']}: thiếu type")
        length = segment_length(s["a"], s["b"])
        if length <= 1e-9:
            errors.append(f"{s['id']}: hai đầu mút trùng nhau")
        elif length < SHORT_SEGMENT_WARN_M:
            warns.append(f"{s['id']}: đoạn chỉ dài {length * 100:.1f} cm, sai số click 1–2 cm chiếm tỉ lệ lớn")
        if abs(length - s["length_m"]) > 5e-4:
            errors.append(f"{s['id']}: length_m {s['length_m']} không khớp toạ độ ({length:.4f} m)")
    if len(anchors) != 1:
        errors.append(f"cần đúng 1 đoạn mốc (anchor), đang có {len(anchors)}")
    for a in anchors:
        lo, hi = ANCHOR_RANGE_M
        if not (lo <= segment_length(a["a"], a["b"]) <= hi):
            errors.append(f"{a['id']}: mốc dài {segment_length(a['a'], a['b']):.3f} m, ngoài {lo}–{hi} m [ĐC §8.1]")
        if not a.get("confirmed_not_on_glass_or_moving"):
            errors.append(f"{a['id']}: chưa xác nhận mốc không nằm trên gương/kính/vật di chuyển được")
    if len(tests) < test_min:
        errors.append(f"cần ≥ {test_min} đoạn test, đang có {len(tests)}")
    if len(tests) > test_max:
        warns.append(f"{len(tests)} đoạn test, nhiều hơn {test_max} (ĐC §8.2 nêu 12–20)")
    # đầu mút: mốc không được trùng/gần đầu mút test; test-test chỉ cảnh báo khi gần
    pts = [(s["id"], s["role"], k, np.asarray(s[k], dtype=np.float64)) for s in segments for k in ("a", "b")]
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            (ida, ra, ka, pa), (idb, rb, kb, pb) = pts[i], pts[j]
            if ida == idb:
                continue
            d = float(np.linalg.norm(pa - pb))
            if d <= 1e-9:
                errors.append(f"đầu mút {ida}.{ka} trùng đầu mút {idb}.{kb}")
            elif d <= snap_radius_m:
                msg = f"đầu mút {ida}.{ka} cách {idb}.{kb} chỉ {d * 100:.1f} cm (≤ bán kính snap {snap_radius_m * 100:g} cm)"
                (errors if {ra, rb} == {"anchor", "test"} else warns).append(msg)
    return errors, warns


# ---------------------------------------------------------------------------
# Ghi measurements.csv, scale_anchor.json
# ---------------------------------------------------------------------------


def _fmt3(p: Sequence[float]) -> str:
    return "(" + ", ".join(f"{v:.3f}" for v in p) + ")"


def segments_to_rows(segments: List[Dict]) -> List[Dict]:
    rows = []
    for s in segments:
        note = f"A={_fmt3(s['a'])} B={_fmt3(s['b'])}"
        if s.get("label"):
            note += f"; {s['label']}"
        if s.get("notes"):
            note += f"; {s['notes']}"
        rows.append({"id": s["id"], "type": s["type"], "ground_truth_m": f"{s['length_m']:.4f}",
                     "used_as_anchor": 1 if s["role"] == "anchor" else 0, "endpoints/notes": note})
    return rows


def anchor_json(seg: Dict, f2s_sha: str) -> Dict:
    return {"id": seg["id"], "L_real": seg["length_m"], "used_as_anchor": 1, "type": seg["type"], "label": seg.get("label", ""),
            "endpoints_scene_xyz": {"a": seg["a"], "b": seg["b"]}, "frame": "scene (ARKit), mét", "source": "faro",
            "endpoint_uncertainty_m": seg.get("endpoint_uncertainty_m"),
            "confirmed_not_on_glass_or_moving": bool(seg.get("confirmed_not_on_glass_or_moving")),
            "faro_to_scene_sha256": f2s_sha, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "note": "L_real đo trên Faro; L_model (click 2D + tam giác hoá bằng camera COLMAP) do stage alignment ở M1 điền"}


def finalize(paths: Paths, sess: Dict, snap_radius_m: float, overwrite: bool = False) -> Dict:
    errors, warns = validate_segments(sess["segments"], snap_radius_m)
    if errors:
        raise AnnotationError("không đạt luật kiểm:\n  - " + "\n  - ".join(errors))
    if not overwrite and (paths.csv.exists() or paths.anchor.exists()):
        raise AnnotationError(f"{paths.csv.name} hoặc {paths.anchor.name} đã có; dùng --overwrite nếu muốn ghi đè")
    rows = segments_to_rows(sess["segments"])
    paths.gt.mkdir(parents=True, exist_ok=True)
    with open(paths.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    anchor = next(s for s in sess["segments"] if s["role"] == "anchor")
    aj = anchor_json(anchor, sess["faro_to_scene_sha256"])
    paths.anchor.write_text(json.dumps(aj, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"rows": rows, "anchor": aj, "warnings": warns}


def check_outputs_match_session(paths: Paths, sess: Dict) -> List[str]:
    """Nếu đã có measurements.csv / scale_anchor.json: có khớp phiên hiện tại không (phát hiện sửa tay)."""
    out = []
    if paths.csv.is_file():
        with open(paths.csv, newline="", encoding="utf-8") as f:
            got = list(csv.DictReader(f))
        if list(got[0].keys() if got else CSV_COLUMNS) != CSV_COLUMNS:
            out.append(f"{paths.csv.name}: tiêu đề cột khác {CSV_COLUMNS}")
        want = {r["id"]: r for r in segments_to_rows(sess["segments"])}
        for r in got:
            w = want.get(r["id"])
            if w is None:
                out.append(f"{paths.csv.name}: id {r['id']} không có trong phiên")
            elif r["ground_truth_m"] != w["ground_truth_m"] or str(r["used_as_anchor"]) != str(w["used_as_anchor"]):
                out.append(f"{paths.csv.name}: {r['id']} khác phiên (ground_truth_m/used_as_anchor)")
        for i in want:
            if i not in {r["id"] for r in got}:
                out.append(f"{paths.csv.name}: thiếu {i}")
    return out


# ---------------------------------------------------------------------------
# Nạp từ JSON (không GUI)
# ---------------------------------------------------------------------------


def segments_from_json(path: Path, existing: List[Dict], uncertainty_m: float) -> List[Dict]:
    """File JSON: danh sách (hoặc {"segments": [...]}) các đoạn {a:[x,y,z], b:[x,y,z], role, type, label?, notes?, id?,
    confirmed_not_on_glass?}. Trả về các đoạn mới (id tự đánh nếu thiếu)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data.get("segments") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise AnnotationError("JSON phải là danh sách đoạn hoặc {\"segments\": [...]}")
    used = {s["id"] for s in existing}
    out = []
    for n, it in enumerate(items, 1):
        for k in ("a", "b", "role", "type"):
            if k not in it:
                raise AnnotationError(f"đoạn #{n} thiếu khoá {k!r}")
        for k in ("a", "b"):
            if len(it[k]) != 3 or not all(isinstance(v, (int, float)) for v in it[k]):
                raise AnnotationError(f"đoạn #{n}: {k} phải là [x, y, z] số")
        seg_id = it.get("id") or next_id(list(existing) + out)
        if seg_id in used or seg_id in {s["id"] for s in out}:
            raise AnnotationError(f"id {seg_id} đã có")
        out.append(make_segment(seg_id, it["role"], it["type"], it["a"], it["b"], it.get("label", ""), it.get("notes", ""),
                                it.get("endpoint_uncertainty_m", uncertainty_m), confirmed_not_glass=it.get("confirmed_not_on_glass")))
    return out


def next_id(segments: Sequence[Dict]) -> str:
    nums = [int(s["id"][1:]) for s in segments if s["id"][:1] == "S" and s["id"][1:].isdigit()]
    return f"S{(max(nums) if nums else 0) + 1:02d}"


# ---------------------------------------------------------------------------
# Point cloud hiển thị và GUI Open3D
# ---------------------------------------------------------------------------


def height_colors(z: np.ndarray) -> np.ndarray:
    """z → màu xanh → lục → vàng → đỏ (cho dễ nhìn cấu trúc; chỉ để hiển thị)."""
    t = np.clip((z - z.min()) / max(float(np.ptp(z)), 1e-9), 0.0, 1.0)
    r = np.clip(1.5 - np.abs(4 * t - 3), 0, 1)
    g = np.clip(1.5 - np.abs(4 * t - 2), 0, 1)
    b = np.clip(1.5 - np.abs(4 * t - 1), 0, 1)
    return np.stack([r, g, b], axis=1)


def load_display_points(ply: Path, box: Optional[Tuple[np.ndarray, np.ndarray]], voxel: float) -> np.ndarray:
    """Điểm Faro (hệ scene) cắt theo hộp `box` và voxel hoá `voxel` (≥ 1 cm, là độ phân giải của file)."""
    chunks = (c[np.all((c >= box[0]) & (c <= box[1]), axis=1)] if box is not None else c for c in adapters.iter_ply_xyz(ply))
    if voxel > DEFAULT_DISPLAY_VOXEL + 1e-12:
        pts, _ = adapters.voxel_downsample_stream(chunks, voxel)
    else:
        parts = [c for c in chunks if len(c)]
        pts = np.concatenate(parts) if parts else np.empty((0, 3))
    if len(pts) == 0:
        raise AnnotationError("không còn điểm nào sau khi cắt hộp hiển thị (kiểm --box)")
    return pts


def default_box(raw_dir: Path, video_id: str, margin: float = 0.3) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Hộp hiển thị mặc định = hộp bao mesh ARKit ± `margin` (m): đủ phòng, bỏ điểm xa nhìn qua cửa sổ.
    Đã đo trên 42444738: tường x ≈ −1,25…4,4, y ≈ −1,85…3,75, sàn z ≈ −0,64, trần z ≈ 1,72; mesh ± 0,3 m ôm đúng phòng.
    None (không cắt) nếu thiếu mesh."""
    mesh = raw_dir / f"{video_id}_3dod_mesh.ply"
    if not mesh.is_file():
        return None
    import open3d as o3d
    v = np.asarray(o3d.io.read_triangle_mesh(str(mesh)).vertices)
    if len(v) == 0:
        return None
    return v.min(axis=0) - margin, v.max(axis=0) + margin


def write_ply_xyz_rgb(path: Path, xyz: np.ndarray, rgb: np.ndarray) -> None:
    """PLY nhị phân: float32 x y z + uchar red green blue."""
    xyz = np.asarray(xyz, dtype=np.float32)
    rgb = np.asarray(rgb, dtype=np.uint8)
    if xyz.shape[0] != rgb.shape[0]:
        raise ValueError("xyz và rgb khác số dòng")
    arr = np.zeros(len(xyz), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("red", "u1"), ("green", "u1"), ("blue", "u1")])
    arr["x"], arr["y"], arr["z"] = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    arr["red"], arr["green"], arr["blue"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    header = "\n".join(["ply", "format binary_little_endian 1.0", "comment annotate_segments.py display file, not ground truth",
                        f"element vertex {len(xyz)}", "property float x", "property float y", "property float z",
                        "property uchar red", "property uchar green", "property uchar blue", "end_header", ""]).encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(header)
        f.write(arr.tobytes())


def read_ply_xyz_rgb(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """Đọc PLY có màu → (xyz float64, rgb float64 trong [0, 1])."""
    parts = list(adapters.iter_ply_xyz_rgb(path))
    if not parts:
        raise AnnotationError(f"{Path(path).name}: rỗng")
    return np.concatenate([p[0] for p in parts]), np.concatenate([p[1] for p in parts]).astype(np.float64) / 255.0


def make_rgb_display(paths: Paths, faro_dir: Path, f2s: Dict, f2s_sha: str, box: Optional[Tuple[np.ndarray, np.ndarray]],
                     voxel: float, out: Callable[[str], None] = print) -> Dict:
    """Tạo `faro_display_rgb.ply` (chỉ để nhìn): đọc lại các scan Faro gốc (mỗi nhóm pose một scan, như `faro_scene_frame.ply`),
    đưa vào hệ scene bằng `faro_to_scene.json`, cắt theo `box`, voxel hoá `voxel` và lấy RGB trung bình mỗi voxel.
    KHÔNG ghi đè `faro_scene_frame.ply` (GT). Ghi kèm `faro_display_rgb.json` (hộp, voxel, hash faro_to_scene.json)."""
    t = np.array(f2s["T_faro_to_scene"], dtype=np.float64)
    reps = f2s.get("unique_scans_used")
    if not reps:
        raise AnnotationError("faro_to_scene.json không có unique_scans_used (nguồn không phải Faro?)")
    scans = {s["scan_id"]: s for s in adapters.list_scans(faro_dir)}
    missing = [r for r in reps if r not in scans]
    if missing:
        raise AnnotationError(f"thiếu scan Faro {missing} trong {faro_dir}")

    def chunks():
        for rid in reps:
            out(f"  đọc scan {rid} ({scans[rid]['n_points']:,} điểm)...")
            for xyz, rgb in adapters.iter_ply_xyz_rgb(scans[rid]["ply"]):
                sc = frs.apply_T(t, xyz)
                keep = np.ones(len(sc), dtype=bool) if box is None else np.all((sc >= box[0]) & (sc <= box[1]), axis=1)
                yield sc[keep], rgb[keep]

    cen, col, _ = adapters.voxel_downsample_attr_stream(chunks(), voxel)
    if len(cen) == 0:
        raise AnnotationError("không còn điểm nào sau khi cắt hộp hiển thị")
    write_ply_xyz_rgb(paths.rgb_ply, cen, np.clip(np.rint(col), 0, 255))
    meta = {"purpose": "chỉ để hiển thị khi chấm; GT là faro_scene_frame.ply", "n_points": int(len(cen)), "voxel_m": voxel,
            "box": None if box is None else [list(map(float, box[0])), list(map(float, box[1]))], "scans": reps,
            "faro_to_scene_sha256": f2s_sha, "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    paths.rgb_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def load_rgb_display(paths: Paths, f2s_sha: str) -> Tuple[np.ndarray, np.ndarray]:
    """Nạp file hiển thị RGB; từ chối nếu thiếu hoặc được tạo từ faro_to_scene.json khác."""
    if not paths.rgb_ply.is_file() or not paths.rgb_meta.is_file():
        raise AnnotationError(f"chưa có {RGB_PLY_NAME}: chạy với --make-rgb trước")
    meta = json.loads(paths.rgb_meta.read_text(encoding="utf-8"))
    if meta.get("faro_to_scene_sha256") != f2s_sha:
        raise AnnotationError(f"{RGB_PLY_NAME} được tạo từ faro_to_scene.json khác: chạy lại --make-rgb")
    return read_ply_xyz_rgb(paths.rgb_ply)


def pick_two_points(points: np.ndarray, title: str, colors: Optional[np.ndarray] = None) -> Optional[Tuple[int, int]]:
    """Mở cửa sổ Open3D (VisualizerWithEditing): shift + chuột trái để chọn, shift + chuột phải để bỏ điểm vừa chọn, Q để đóng.
    Trả về chỉ số 2 điểm theo thứ tự chọn, hoặc None nếu không đúng 2 điểm."""
    import open3d as o3d
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    pcd.colors = o3d.utility.Vector3dVector(height_colors(points[:, 2]) if colors is None else colors)
    vis = o3d.visualization.VisualizerWithEditing()
    vis.create_window(window_name=title, width=1500, height=950)
    vis.add_geometry(pcd)
    vis.get_render_option().point_size = 3.0
    vis.run()
    vis.destroy_window()
    idx = list(vis.get_picked_points())
    return (int(idx[0]), int(idx[1])) if len(idx) == 2 else None


def view_only(points: np.ndarray, title: str, colors: Optional[np.ndarray] = None) -> None:
    import open3d as o3d
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    pcd.colors = o3d.utility.Vector3dVector(height_colors(points[:, 2]) if colors is None else colors)
    o3d.visualization.draw_geometries([pcd], window_name=title, width=1500, height=950)


HELP_TEXT = """\
  Cửa sổ Open3D:  chuột trái kéo = xoay · Ctrl + chuột trái kéo (hoặc chuột giữa kéo) = dịch · cuộn chuột = phóng to/thu nhỏ
                  + / - = đổi cỡ điểm · R = về góc nhìn ban đầu
                  SHIFT + chuột trái = chọn điểm (đúng 2 điểm: A rồi B) · SHIFT + chuột phải = bỏ điểm vừa chọn · Q = đóng cửa sổ
                  Đừng bấm K, C, S (chế độ cắt/lưu của cửa sổ)."""


def annotate_loop(paths: Paths, sess: Dict, points: np.ndarray, snap_radius_m: float,
                  pick: Callable[[np.ndarray, str], Optional[Tuple[int, int]]] = pick_two_points,
                  ask: Callable[[str], str] = input, out: Callable[[str], None] = print,
                  display_name: str = SCENE_PLY_NAME) -> None:
    """Vòng chấm tương tác. `pick` và `ask` có thể thay bằng bản giả để test. Lưu phiên sau mỗi đoạn."""
    segs = sess["segments"]
    while True:
        n_a = sum(s["role"] == "anchor" for s in segs)
        n_t = sum(s["role"] == "test" for s in segs)
        out(f"\n[phiên] {n_a}/1 mốc, {n_t} đoạn test (cần ≥ {TEST_COUNT_RANGE[0]}, nên ≤ {TEST_COUNT_RANGE[1]})")
        cmd = ask("Enter = chấm đoạn mới · l = liệt kê · u = xoá đoạn cuối · q = dừng: ").strip().lower()
        if cmd == "q":
            return
        if cmd == "l":
            for s in segs:
                out(f"  {s['id']} {s['role']:<6} {s['type']:<16} {s['length_m']:.4f} m  {s.get('label', '')}")
            continue
        if cmd == "u":
            if segs:
                gone = segs.pop()
                save_session(paths, sess)
                out(f"  đã xoá {gone['id']} ({gone['length_m']:.4f} m)")
            else:
                out("  chưa có đoạn nào")
            continue
        out(HELP_TEXT)
        picked = pick(points, f"Chấm đoạn {next_id(segs)}: chọn 2 điểm bằng SHIFT+chuột trái, rồi bấm Q")
        if picked is None:
            out("  [!] cần đúng 2 điểm; không lưu. Thử lại.")
            continue
        ia, ib = picked
        a, b = points[ia], points[ib]
        length = segment_length(a, b)
        out(f"  A = {_fmt3(a)}\n  B = {_fmt3(b)}\n  chiều dài = {length:.4f} m")
        role_in = ask("  Vai trò: t = test, a = mốc scale (1–2 m, đúng 1 đoạn): ").strip().lower()
        if role_in not in ("t", "a"):
            out("  [!] chỉ nhận t hoặc a; không lưu.")
            continue
        role = "anchor" if role_in == "a" else "test"
        if role == "anchor" and n_a >= 1:
            out("  [!] đã có mốc; xoá mốc cũ bằng 'u' hoặc chọn t. Không lưu.")
            continue
        types = "/".join(SEGMENT_TYPES)
        seg_type = ask(f"  Loại ({types}) [Enter = other]: ").strip() or "other"
        label = ask("  Nhãn ngắn (vd. 'rộng cửa chính'): ").strip()
        notes = ask("  Ghi chú (Enter bỏ qua): ").strip()
        confirmed = None
        if role == "anchor":
            confirmed = ask("  Mốc nằm trên bề mặt dễ thấy, KHÔNG trên gương/kính/vật di chuyển được? (y/n): ").strip().lower() == "y"
        if ask("  Lưu đoạn này? (y/n): ").strip().lower() != "y":
            out("  bỏ qua.")
            continue
        seg = make_segment(next_id(segs), role, seg_type, a, b, label, notes, uncertainty_m=float(sess["display_voxel_m"]),
                           a_index=ia, b_index=ib, confirmed_not_glass=confirmed, display=display_name)
        segs.append(seg)
        save_session(paths, sess)
        errs, warns = validate_segments(segs, snap_radius_m, test_min=0)
        for e in errs:
            if "cần đúng 1 đoạn mốc" not in e:
                out(f"  [lỗi] {e}")
        for w in warns:
            out(f"  [cảnh báo] {w}")
        out(f"  đã lưu {seg['id']} ({seg['length_m']:.4f} m)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def print_report(segments: List[Dict], errors: List[str], warns: List[str]) -> None:
    print(f"{'id':<5} {'vai trò':<7} {'loại':<16} {'dài (m)':>8}  nhãn")
    for s in segments:
        print(f"{s['id']:<5} {s['role']:<7} {s['type']:<16} {s['length_m']:>8.4f}  {s.get('label', '')}")
    n_t = sum(s["role"] == "test" for s in segments)
    print(f"\n{sum(s['role'] == 'anchor' for s in segments)} mốc, {n_t} đoạn test")
    for w in warns:
        print(f"[cảnh báo] {w}")
    for e in errors:
        print(f"[lỗi] {e}")
    if not errors:
        print("[OK] đạt luật kiểm")


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Chấm 1 mốc scale + các đoạn test trên Faro đã căn")
    ap.add_argument("--scene", required=True, help="arkitscenes/<video_id>")
    ap.add_argument("--root", default=str(REPO))
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--view", action="store_true", help="chỉ mở cửa sổ xem point cloud (không chọn)")
    mode.add_argument("--check", action="store_true", help="kiểm luật trên phiên hiện có, không mở GUI")
    mode.add_argument("--finalize", action="store_true", help="kiểm luật rồi ghi measurements.csv + scale_anchor.json")
    mode.add_argument("--make-rgb", action="store_true",
                      help=f"tạo {RGB_PLY_NAME} (file hiển thị có màu RGB, tách riêng, KHÔNG ghi đè {SCENE_PLY_NAME}); dùng --box/--display-voxel")
    mode.add_argument("--from-json", metavar="FILE", help="nạp các đoạn (toạ độ hệ scene) từ JSON vào phiên, không GUI")
    ap.add_argument("--overwrite", action="store_true", help="cho phép --finalize ghi đè measurements.csv / scale_anchor.json")
    ap.add_argument("--display-voxel", type=float, default=DEFAULT_DISPLAY_VOXEL, help="voxel (m) của điểm hiển thị, ≥ 0,01")
    ap.add_argument("--box", type=float, nargs=6, metavar=("X0", "Y0", "Z0", "X1", "Y1", "Z1"),
                    help="hộp hiển thị (hệ scene); mặc định: hộp bao mesh ARKit ± 0,3 m")
    ap.add_argument("--no-crop", action="store_true", help="hiển thị cả điểm ngoài phòng")
    ap.add_argument("--rgb", action="store_true", help=f"hiển thị bằng {RGB_PLY_NAME} (màu thật) thay vì tô theo độ cao; cần --make-rgb trước")
    args = ap.parse_args(argv)

    try:
        info = faro_align.resolve_scene(Path(args.root), args.scene)
    except (sp.HeldoutError, sp.LockError, ValueError, FileNotFoundError) as e:
        print(f"[LỖI] {type(e).__name__}: {e}")
        return 1
    paths = Paths(info["layout"].ground_truth)
    cfg = cfgmod.load_config(Path(args.root) / "configs" / "default.yaml")
    snap = float(cfgmod.require(cfg, "eval.snap_radius_m"))
    try:
        require_alignment(paths)
        f2s_sha = sha256_file(paths.f2s)
        sess = load_session(paths)
        if sess is not None:
            check_session_alignment(sess, f2s_sha)
        if args.display_voxel < DEFAULT_DISPLAY_VOXEL - 1e-12:
            raise AnnotationError("--display-voxel phải ≥ 0,01 (độ phân giải của faro_scene_frame.ply)")

        if args.check or args.finalize:
            if sess is None:
                raise AnnotationError("chưa có phiên chấm (annotation_session.json)")
            errors, warns = validate_segments(sess["segments"], snap)
            print_report(sess["segments"], errors, warns)
            if args.finalize:
                if errors:
                    return 2
                res = finalize(paths, sess, snap, overwrite=args.overwrite)
                print(f"[OK] ghi {paths.csv} ({len(res['rows'])} dòng) và {paths.anchor} (mốc {res['anchor']['id']}, L_real {res['anchor']['L_real']} m)")
                return 0
            mism = check_outputs_match_session(paths, sess)
            for m in mism:
                print(f"[lỗi] {m}")
            return 2 if errors or mism else 0

        if args.from_json:
            sess = sess or new_session(args.scene, f2s_sha, args.display_voxel)
            new = segments_from_json(Path(args.from_json), sess["segments"], args.display_voxel)
            sess["segments"].extend(new)
            save_session(paths, sess)
            errors, warns = validate_segments(sess["segments"], snap)
            print(f"[OK] nạp {len(new)} đoạn vào {paths.session}")
            print_report(sess["segments"], errors, warns)
            return 2 if errors else 0

        box = None
        if not args.no_crop:
            box = (np.array(args.box[:3]), np.array(args.box[3:])) if args.box else default_box(info["raw_dir"], info["video_id"])
        box_txt = "không cắt" if box is None else np.round(np.concatenate(box), 2).tolist()
        if args.make_rgb:
            f2s = json.loads(paths.f2s.read_text(encoding="utf-8"))
            print(f"[make-rgb] hộp {box_txt}, voxel {args.display_voxel * 100:g} cm; đọc 3 scan Faro gốc (vài phút)")
            meta = make_rgb_display(paths, info["faro_dir"], f2s, f2s_sha, box, args.display_voxel)
            print(f"[OK] ghi {paths.rgb_ply} ({meta['n_points']:,} điểm) và {paths.rgb_meta.name}; {SCENE_PLY_NAME} không bị đụng tới")
            return 0
        colors = None
        display_name = SCENE_PLY_NAME
        if args.rgb:
            points, colors = load_rgb_display(paths, f2s_sha)
            display_name = RGB_PLY_NAME
            print(f"[hiển thị] {len(points):,} điểm từ {RGB_PLY_NAME} (màu RGB); --box/--display-voxel bị bỏ qua (đã cố định lúc --make-rgb)")
        else:
            points = load_display_points(paths.ply, box, args.display_voxel)
            print(f"[hiển thị] {len(points):,} điểm (voxel {args.display_voxel * 100:g} cm), tô theo độ cao; hộp {box_txt}")
        if args.view:
            print(HELP_TEXT)
            view_only(points, f"Faro đã căn: {args.scene}", colors)
            return 0
        sess = sess or new_session(args.scene, f2s_sha, args.display_voxel)
        save_session(paths, sess)
        print(f"[phiên] {paths.session}")
        print("Quy tắc chấm: 1 mốc 1–2 m dễ thấy, không trên gương/kính; ≥ 12 đoạn test (12–20), đầu mút khác nhau; "
              "mốc không dùng chung đầu mút với đoạn test. Chọn góc/cạnh rõ nét trên point cloud (sai số click cỡ 1 cm).")
        annotate_loop(paths, sess, points, snap, pick=lambda pts, title: pick_two_points(pts, title, colors), display_name=display_name)
        errors, warns = validate_segments(sess["segments"], snap)
        print_report(sess["segments"], errors, warns)
        print("Khi đủ: chạy lại với --check rồi --finalize.")
        return 0
    except AnnotationError as e:
        print(f"[LỖI] {e}")
        return 2 if "luật kiểm" in str(e) else 1


if __name__ == "__main__":
    sys.exit(main())
