"""Stage `keyframe` (ĐC §7, kế hoạch §4.1): từ `vga_wide.zip` của ARKitScenes (hoặc video điện thoại) ra keyframe đã xoay đứng.

Quy trình (M2):
  1. chọn khung gần nhất mỗi `1/keyframe.fps` giây (ví dụ 2 fps cho ~120 ứng viên, ĐC §7);
  2. đo `V` (phương sai Laplacian), `q_blur` (3) với `quality.v_ref.vga`, `q_exposure` (20);
  3. bỏ khung `q_blur < keyframe.blur.q_drop` hoặc `q_exposure < keyframe.exposure.q_drop`;
  4. lọc theo overlap RGB (`overlap.py`): bỏ khung trùng (> `keyframe.overlap.max`), lùi một khung khi sắp mất kết nối (< `keyframe.overlap.min`);
  5. dưới `keyframe.target_min` thì `E_TOO_FEW_KEYFRAMES`;
  6. xoay đứng theo `sky_direction`, ghi tập ứng viên DÀY vào `frames/candidates/NNNN.jpg`, `metadata/candidates.csv`, `metadata/camera.json`, `raw/source.json`.

Tập dày dành cho SfM: SfM trên 80 khung thưa đều đăng ký chỉ 8–40% ở scene Validation (M2). Chọn 40–80 keyframe cho VGGT/MVS (ĐC §7) làm ở
stage `sfm`, từ các ảnh đã đăng ký (`pipeline.colmap.run_colmap.select_keyframes`), ghi `frames/keyframes/` và `metadata/keyframes.csv`.

Chỉ dùng RGB; pose ARKit không được đọc (không suy scale hay hình học từ pose GT).
Intrinsics của `vga_wide` đổi theo từng khung (đã đo trên 42444738: fx 522–546 px), nên `keyframes.csv` ghi intrinsics từng khung còn
`camera.json` là trung vị (điểm khởi đầu cho một camera PINHOLE của COLMAP, COLMAP sẽ tinh chỉnh tiêu cự).

Nguồn video (`extract_video_keyframes`, dữ liệu tự thu): cùng các bước 1–6 (`_densify`), khác ở đầu vào: timestamp lấy từ container, hướng xoay từ tag
rotation của video, intrinsics ước lượng từ tiêu cự tương đương 35 mm [Suy luận], và ảnh hạ về cạnh dài `video.long_edge` (640) TRƯỚC khi đo `V` để dùng đúng
`V_ref`/`G_ref` đã đo trên `vga_wide` 640×480. [chưa kiểm chứng trên video điện thoại thật]
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from ..common import adapters
from ..common import config as cfgmod
from ..common import quality as qual
from ..common.errors import E_MISSING_INPUT, E_TOO_FEW_KEYFRAMES, StageError
from ..common.io import SceneLayout, ensure_dir, read_json, write_json
from ..common.schema import write_keyframes_csv
from .orientation import rotation_for_video, upright, upright_rot
from .overlap import Features, make_overlap_fn, select_by_overlap

JPEG_QUALITY = 95


def select_candidates(ts: Sequence[float], fps: float) -> List[int]:
    """Chỉ số khung gần nhất mỗi 1/fps giây kể từ khung đầu (không trùng, tăng dần). `ts` đã sắp tăng."""
    ts = np.asarray(ts, dtype=np.float64)
    if len(ts) == 0:
        return []
    if fps <= 0:
        raise ValueError("fps phải > 0")
    targets = np.arange(ts[0], ts[-1] + 1e-9, 1.0 / fps)
    idx = np.abs(ts[None, :] - targets[:, None]).argmin(axis=1)
    return sorted(set(int(i) for i in idx))


def thin_even(items: Sequence, max_n: int) -> List:
    """Lấy đều `max_n` phần tử (giữ phần tử đầu và cuối) nếu nhiều hơn; nếu không thì giữ nguyên."""
    items = list(items)
    if max_n <= 0:
        raise ValueError("max_n phải > 0")
    if len(items) <= max_n:
        return items
    pick = np.unique(np.round(np.linspace(0, len(items) - 1, max_n)).astype(int))
    return [items[i] for i in pick]


def _densify(layout: SceneLayout, cfg: Dict, ts: Sequence[float], cand: Sequence[int],
             gray_at: Callable[[int], np.ndarray], frame_at: Callable[[int], Tuple[np.ndarray, Tuple[float, float, float, float], str, str]],
             sky_label: str, t0: float, log: Callable[[str], None], camera_extra: Optional[Dict] = None) -> Dict:
    """Bước 2–6 dùng chung cho mọi nguồn: đo chất lượng các ứng viên `cand` (chỉ số vào `ts`), lọc blur/exposure/overlap, ghi tập dày.

    `gray_at(i)`: ảnh xám khung i để đo V/exposure/ORB; `frame_at(i)` → (ảnh đã xoay đứng, (fx, fy, cx, cy) sau xoay, rot_applied, src_name).
    Trả về thống kê (chưa gồm thông tin riêng của nguồn)."""
    target_min = int(cfgmod.require(cfg, "keyframe.target_min"))
    fps = float(cfgmod.require(cfg, "keyframe.fps"))
    q_drop = float(cfgmod.require(cfg, "keyframe.blur.q_drop"))
    exp_drop = float(cfgmod.require(cfg, "keyframe.exposure.q_drop"))
    o_max, o_min = float(cfgmod.require(cfg, "keyframe.overlap.max")), float(cfgmod.require(cfg, "keyframe.overlap.min"))
    v_ref = float(cfgmod.require(cfg, "quality.v_ref.vga"))
    dark_px = int(cfgmod.require(cfg, "quality.dark_px"))
    bright_px = int(cfgmod.require(cfg, "quality.bright_px"))

    measured = []
    for i in cand:
        gray = gray_at(i)
        v = qual.laplacian_variance(gray)
        m = {"i": i, "V": v, "q_blur": qual.q_blur(v, v_ref), "q_exposure": qual.q_exposure(gray, dark_px, bright_px)}
        if m["q_blur"] >= q_drop and m["q_exposure"] >= exp_drop:
            m["feat"] = Features(gray)                       # chỉ tính ORB cho khung đã qua lọc mờ và phơi sáng
        measured.append(m)
    kept = [m for m in measured if m["q_blur"] >= q_drop]
    n_after_blur = len(kept)
    kept = [m for m in kept if m["q_exposure"] >= exp_drop]
    n_after_exposure = len(kept)
    log(f"[keyframe] {len(cand)} ứng viên → bỏ {len(measured) - n_after_blur} khung q_blur < {q_drop:g} (V_ref {v_ref:g}) → bỏ {n_after_blur - n_after_exposure} khung "
        f"q_exposure < {exp_drop:g} ⇒ còn {n_after_exposure}")
    idx, n_breaks = select_by_overlap(len(kept), make_overlap_fn([m["feat"] for m in kept]), o_max, o_min)
    kept = [kept[i] for i in idx]
    n_after_overlap = len(kept)
    log(f"[keyframe] lọc overlap (max {o_max:g}, min {o_min:g}): bỏ {n_after_exposure - n_after_overlap} khung trùng ⇒ còn {n_after_overlap}; {n_breaks} chỗ mất kết nối (liền kề overlap < {o_min:g})")
    if len(kept) < target_min:
        raise StageError(E_TOO_FEW_KEYFRAMES, f"chỉ còn {len(kept)} khung ứng viên, cần ≥ {target_min}")

    ensure_dir(layout.candidates)
    ensure_dir(layout.metadata)
    ensure_dir(layout.raw)
    rows, per_view_k = [], []
    for view_id, m in enumerate(kept):
        img2, (fx, fy, cx, cy), rot, src_name = frame_at(m["i"])
        h, w = img2.shape[:2]
        if not cv2.imwrite(str(layout.candidates / f"{view_id:04d}.jpg"), np.ascontiguousarray(img2), [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]):
            raise StageError(E_MISSING_INPUT, f"không ghi được ứng viên {view_id:04d}.jpg")
        rows.append({"view_id": view_id, "frame_ts": float(ts[m["i"]]), "src_name": src_name, "V": round(m["V"], 3),
                     "q_blur": round(m["q_blur"], 5), "q_exposure": round(m["q_exposure"], 5), "sky_direction": sky_label,
                     "rot_applied": rot, "w": w, "h": h, "fx": fx, "fy": fy, "cx": cx, "cy": cy})
        per_view_k.append((fx, fy, cx, cy))

    write_keyframes_csv(rows, layout.metadata / "candidates.csv")
    k = np.array(per_view_k)
    med = np.median(k, axis=0)
    camera = {"camera_model": "PINHOLE", "w": int(rows[0]["w"]), "h": int(rows[0]["h"]),
              "fx": float(med[0]), "fy": float(med[1]), "cx": float(med[2]), "cy": float(med[3]),
              "intrinsics_per_frame": "candidates.csv", "fx_min": float(k[:, 0].min()), "fx_max": float(k[:, 0].max()),
              "note": "trung vị intrinsics các keyframe (đã xoay đứng); intrinsics vga_wide đổi theo khung, COLMAP tinh chỉnh tiêu cự"}
    camera.update(camera_extra or {})
    write_json(layout.metadata / "camera.json", camera)
    stats = {"n_frames": len(ts), "n_candidates": len(cand), "n_after_blur": n_after_blur, "n_after_exposure": n_after_exposure,
             "n_after_overlap": n_after_overlap, "n_overlap_breaks": n_breaks, "n_dense": len(rows),
             "exposure_q_drop": exp_drop, "overlap_max": o_max, "overlap_min": o_min,
             "q_drop": q_drop, "fps": fps, "target_min": target_min, "v_ref": v_ref,
             "q_blur_min": float(min(r["q_blur"] for r in rows)), "q_exposure_min": float(min(r["q_exposure"] for r in rows)),
             "seconds": round(time.time() - t0, 2)}
    log(f"[keyframe] {len(rows)} khung ứng viên cho SfM {camera['w']}×{camera['h']} đã xoay ({rows[0]['rot_applied']}); "
        f"fx {camera['fx_min']:.1f}–{camera['fx_max']:.1f}, trung vị {camera['fx']:.1f}; {stats['seconds']} s")
    return stats


def extract_keyframes(raw_dir: Path, layout: SceneLayout, cfg: Dict, sky_direction: str, source_info: Optional[Dict] = None,
                      log: Callable[[str], None] = print) -> Dict:
    """Chạy stage `keyframe` cho một scene. `raw_dir` chứa `vga_wide.zip` và `vga_wide_intrinsics.zip`. Trả về thống kê."""
    t0 = time.time()
    fps = float(cfgmod.require(cfg, "keyframe.fps"))
    rotate = bool(cfgmod.require(cfg, "keyframe.rotate_from_sky"))

    with adapters.AssetReader(str(raw_dir), "vga_wide") as rgb, adapters.AssetReader(str(raw_dir), "vga_wide_intrinsics") as intr_rd:
        if not rgb.exists() or not intr_rd.exists():
            raise StageError(E_MISSING_INPUT, f"thiếu vga_wide hoặc vga_wide_intrinsics trong {raw_dir}")
        entries = sorted(rgb.list_pngs(), key=adapters.frame_timestamp)
        ts = [adapters.frame_timestamp(e) for e in entries]
        intr = adapters.read_intrinsics(intr_rd)
        cand = select_candidates(ts, fps)
        log(f"[keyframe] {len(entries)} khung vga_wide ({ts[-1] - ts[0]:.1f} s); {fps:g} fps ⇒ {len(cand)} ứng viên")

        def gray_at(i):
            return rgb.read(entries[i], cv2.IMREAD_GRAYSCALE)   # cùng cách đọc với `pipeline.common.reference` (đo V_ref)

        def frame_at(i):
            if ts[i] not in intr:
                raise StageError(E_MISSING_INPUT, f"không có intrinsics cho khung {entries[i]}")
            p = intr[ts[i]]
            img = rgb.read(entries[i], cv2.IMREAD_COLOR)
            if rotate:
                img2, k, rot = upright(img, (p["fx"], p["fy"], p["cx"], p["cy"]), sky_direction)
            else:
                img2, k, rot = img, (p["fx"], p["fy"], p["cx"], p["cy"]), "none"
            return img2, k, rot, Path(entries[i]).name

        stats = _densify(layout, cfg, ts, cand, gray_at, frame_at, sky_direction, t0, log)

    src = dict(source_info or {})
    src.update(sky_direction=sky_direction, raw_dir=str(raw_dir), vga_wide=str(Path(raw_dir) / "vga_wide.zip"), stats=stats)
    write_json(layout.raw / "source.json", src)
    return stats


def extract_video_keyframes(video_path: Path, layout: SceneLayout, cfg: Dict, source_info: Optional[Dict] = None,
                            log: Callable[[str], None] = print) -> Dict:
    """Stage `keyframe` cho video điện thoại (mp4/MOV) → cùng hợp đồng đầu ra như `extract_keyframes`.

    Mỗi khung: xoay đứng theo tag rotation (cập nhật intrinsics qua `rotate_intrinsics`) rồi hạ về cạnh dài `video.long_edge` bằng INTER_AREA
    (không phóng to); `V`, `q_blur`, `q_exposure` đo trên chính ảnh đã hạ ⇒ dùng đúng `V_ref`/`G_ref.vga` của `vga_wide` 640×480 [Suy luận: khác camera
    nên chỉ tương đương theo độ phân giải]. Intrinsics: `adapters.estimate_intrinsics` với `video.focal35_mm` (hoặc `video.json` cạnh video:
    {"focal35_mm": …}) [Suy luận]; COLMAP tinh chỉnh tiêu cự. Giữ cả tập ứng viên trong RAM.
    # shortcut: ~0,9 MB/khung ở 640×480 (~1000 khung ≈ 1 GB), video dài hơn ~15 phút nên nén JPEG tạm.
    [chưa kiểm chứng trên video điện thoại thật]"""
    t0 = time.time()
    fps = float(cfgmod.require(cfg, "keyframe.fps"))
    long_edge = int(cfgmod.require(cfg, "video.long_edge"))
    focal35 = float(cfgmod.require(cfg, "video.focal35_mm"))
    video_path = Path(video_path)
    sidecar = video_path.with_name("video.json")
    if sidecar.is_file():
        focal35 = float(read_json(sidecar).get("focal35_mm", focal35))
    try:
        vid = adapters.VideoSource(video_path)
    except (FileNotFoundError, ValueError) as e:
        raise StageError(E_MISSING_INPUT, str(e)) from e

    with vid:
        try:
            ts = vid.timestamps()
            rot = rotation_for_video(vid.rotation_deg)
        except ValueError as e:
            raise StageError(E_MISSING_INPUT, str(e)) from e
        cand = select_candidates(ts, fps)
        log(f"[keyframe] video {video_path.name}: {len(ts)} khung ({ts[-1] - ts[0]:.1f} s), rotation {vid.rotation_deg}° ({rot}), "
            f"timestamp {'suy từ fps metadata' if vid.ts_from_meta else 'của container'}; {fps:g} fps ⇒ {len(cand)} ứng viên")
        size = {}

        def prepare(img):
            h0, w0 = img.shape[:2]
            p = adapters.estimate_intrinsics(w0, h0, focal35)
            img1, k1, _ = upright_rot(img, (p["fx"], p["fy"], p["cx"], p["cy"]), rot)
            size.setdefault("raw", (w0, h0))
            h1, w1 = img1.shape[:2]
            s = min(1.0, long_edge / max(w1, h1))             # chỉ hạ, không phóng to
            w2, h2 = max(1, round(w1 * s)), max(1, round(h1 * s))
            if (w2, h2) == (w1, h1):
                return np.ascontiguousarray(img1), k1
            sx, sy = w2 / w1, h2 / h1
            small = cv2.resize(np.ascontiguousarray(img1), (w2, h2), interpolation=cv2.INTER_AREA)
            return small, (k1[0] * sx, k1[1] * sy, k1[2] * sx, k1[3] * sy)

        frames = vid.read_frames(cand, transform=prepare)

    def gray_at(i):
        return cv2.cvtColor(frames[i][0], cv2.COLOR_BGR2GRAY)

    def frame_at(i):
        img, k = frames[i]
        return img, k, rot, f"{video_path.stem}_{ts[i]:.3f}"

    extra = {"intrinsics_source": "estimated_from_focal35", "focal35_mm": focal35,
             "note": "video không có .pincam: fx = fy = focal35·√(w²+h²)/43,27 trên ảnh gốc, tâm ở giữa, rồi xoay đứng và hạ về video.long_edge [Suy luận]; COLMAP tinh chỉnh tiêu cự"}
    stats = _densify(layout, cfg, ts, cand, gray_at, frame_at, "video", t0, log, camera_extra=extra)
    src = dict(source_info or {})
    src.update(video=str(video_path), video_size=list(size["raw"]), rotation_deg=vid.rotation_deg, rot_applied=rot, fps_meta=vid.fps_meta,
               timestamps_from_fps_meta=vid.ts_from_meta, focal35_mm=focal35, long_edge=long_edge, stats=stats)
    write_json(layout.raw / "source.json", src)
    return stats
