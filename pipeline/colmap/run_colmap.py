"""Stage `sfm` và `mvs` bằng COLMAP CLI 4.2 (kế hoạch §4.2). pycolmap 3.10 chỉ ĐỌC model và tính tín hiệu; mọi bước ghi đều do CLI.

SfM: `feature_extractor` (một camera PINHOLE, tham số từ `metadata/camera.json`) → `sequential_matcher` → `mapper`; chọn model nhiều ảnh nhất làm `sparse/0`.
MVS: `image_undistorter` → `patch_match_stereo` (geom_consistency) → `stereo_fusion` ra `fused.ply` + `fused.ply.vis`.
Tín hiệu: `observations.npz`, `e_reproj_map/<view>.npy` (sfm) và `sigma_depth/<view>.npy` (mvs).
Peak VRAM của tiến trình con được thăm dò bằng `nvidia-smi` mỗi giây [chưa kiểm chứng độ chính xác; ghi cả mức nền].
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from ..common import config as cfgmod
from ..common.errors import E_COLMAP_FAILED, E_MISSING_INPUT, E_SFM_FAILED, E_TOO_FEW_KEYFRAMES, StageError
from ..common.io import SceneLayout, ensure_dir, read_json, write_json
from ..common.schema import read_keyframes_csv, write_keyframes_csv
from ..keyframe.extract import thin_even
from . import depth_io, signals

# ---------------------------------------------------------------------------
# Chạy tiến trình con và đo VRAM
# ---------------------------------------------------------------------------


def gpu_memory_used_mib() -> Optional[float]:
    """Bộ nhớ GPU đang dùng (MiB) theo `nvidia-smi`; None nếu không đọc được."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True,
                             text=True, timeout=10, check=True).stdout.strip().splitlines()
        return float(out[0])
    except Exception:
        return None


class VramPoller:
    """Thread thăm dò `gpu_memory_used_mib` mỗi `interval` giây, giữ giá trị lớn nhất."""

    def __init__(self, interval: float = 1.0, probe: Callable[[], Optional[float]] = gpu_memory_used_mib):
        self.interval, self.probe = interval, probe
        self.peak: Optional[float] = None
        self.baseline: Optional[float] = probe()
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            v = self.probe()
            if v is not None and (self.peak is None or v > self.peak):
                self.peak = v
            self._stop.wait(self.interval)

    def __enter__(self):
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._t.join(timeout=5)


def run_cmd(exe, args: Sequence, log: Callable[[str], None] = print, poll_vram: bool = True, cwd: Optional[Path] = None) -> Dict:
    """Chạy `exe args` và đợi xong. Thoát khác 0 thì `E_COLMAP_FAILED` kèm phần cuối đầu ra. Trả về {seconds, peak_vram_mib, baseline_vram_mib}."""
    cmd = [str(exe)] + [str(a) for a in args]
    log("  $ " + " ".join(cmd[:3]) + (" ..." if len(cmd) > 3 else ""))
    t0 = time.time()
    poller = VramPoller() if poll_vram else None
    try:
        if poller:
            poller.__enter__()
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd)
    finally:
        if poller:
            poller.__exit__(None, None, None)
    sec = time.time() - t0
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + "\n" + proc.stderr).strip().splitlines()[-15:])
        raise StageError(E_COLMAP_FAILED, f"{' '.join(cmd[:2])} thoát mã {proc.returncode} sau {sec:.0f} s:\n{tail}")
    return {"seconds": round(sec, 1), "peak_vram_mib": None if not poller else poller.peak,
            "baseline_vram_mib": None if not poller else poller.baseline}


def _merge_runs(runs: List[Dict]) -> Dict:
    peaks = [r["peak_vram_mib"] for r in runs if r.get("peak_vram_mib") is not None]
    base = [r["baseline_vram_mib"] for r in runs if r.get("baseline_vram_mib") is not None]
    return {"seconds": round(sum(r["seconds"] for r in runs), 1), "peak_vram_mib": max(peaks) if peaks else None,
            "baseline_vram_mib": min(base) if base else None}


# ---------------------------------------------------------------------------
# SfM
# ---------------------------------------------------------------------------


def feature_extractor_args(images: Path, db: Path, cam: Dict, max_image_size=None, use_gpu: bool = True, sift: Optional[Dict] = None) -> List:
    args = ["feature_extractor", "--database_path", db, "--image_path", images,
            "--ImageReader.camera_model", cam.get("camera_model", "PINHOLE"), "--ImageReader.single_camera", 1,
            "--ImageReader.camera_params", f"{cam['fx']},{cam['fy']},{cam['cx']},{cam['cy']}",
            "--FeatureExtraction.use_gpu", 1 if use_gpu else 0]
    if max_image_size is not None:
        args += ["--FeatureExtraction.max_image_size", int(max_image_size)]
    for k, v in (sift or {}).items():                              # SiftExtraction.<khoá> từ colmap.sift
        args += [f"--SiftExtraction.{k}", int(v) if isinstance(v, bool) else v]
    return args


def sequential_matcher_args(db: Path, overlap=None, use_gpu: bool = True) -> List:
    args = ["sequential_matcher", "--database_path", db, "--FeatureMatching.use_gpu", 1 if use_gpu else 0]
    if overlap is not None:
        args += ["--SequentialMatching.overlap", int(overlap)]
    return args


def exhaustive_matcher_args(db: Path, use_gpu: bool = True) -> List:
    return ["exhaustive_matcher", "--database_path", db, "--FeatureMatching.use_gpu", 1 if use_gpu else 0]


def mapper_args(db: Path, images: Path, out: Path, opts: Optional[Dict] = None) -> List:
    args = ["mapper", "--database_path", db, "--image_path", images, "--output_path", out]
    for k, v in (opts or {}).items():                              # Mapper.<khoá> từ colmap.mapper
        args += [f"--Mapper.{k}", v]
    return args


def choose_best_model(sparse_dir: Path):
    """Trong `sparse/<n>` chọn model nhiều ảnh đăng ký nhất và đặt nó làm `sparse/0`. Trả về (Reconstruction, số model)."""
    import pycolmap
    dirs = sorted(p for p in Path(sparse_dir).iterdir() if p.is_dir() and (p / "images.bin").is_file())
    if not dirs:
        raise StageError(E_SFM_FAILED, f"mapper không dựng được model nào trong {sparse_dir}")
    recs = [(p, pycolmap.Reconstruction(str(p))) for p in dirs]
    best_p, best = max(recs, key=lambda t: (t[1].num_reg_images(), len(t[1].points3D)))
    if best_p.name != "0":
        tmp, zero = Path(sparse_dir) / "_swap", Path(sparse_dir) / "0"
        if zero.exists():
            zero.rename(tmp)
        best_p.rename(zero)
        if tmp.exists():
            tmp.rename(best_p)
    return best, len(dirs)


def select_keyframes(layout: SceneLayout, cfg: Dict, sparse: Path, rec, log: Callable[[str], None] = print):
    """Chọn ≤ `keyframe.target_max` keyframe (ĐC §7) đều theo thời gian trong số ảnh ĐÃ đăng ký của `rec` (= `sparse/0`).

    Ghi `frames/keyframes/NNNN.jpg` và `metadata/keyframes.csv` (đánh số lại view_id 0..n−1, cùng chỉ số i mọi stage sau), giữ model đầy đủ ở
    `sfm/sparse_full/0` và ghi model rút gọn (chỉ ảnh được chọn, tên đổi thành NNNN.jpg, tư thế giữ nguyên từ BA trên tập dày) vào `sparse/0`.
    Dưới `keyframe.target_min` ảnh đã đăng ký thì `E_TOO_FEW_KEYFRAMES`. Trả về model rút gọn.
    """
    t_min, t_max = int(cfgmod.require(cfg, "keyframe.target_min")), int(cfgmod.require(cfg, "keyframe.target_max"))
    rows = {f"{int(r['view_id']):04d}.jpg": r for r in read_keyframes_csv(layout.metadata / "candidates.csv")}
    reg = sorted(im.name for im in rec.images.values() if rec.is_image_registered(im.image_id))
    if len(reg) < t_min:
        raise StageError(E_TOO_FEW_KEYFRAMES, f"SfM chỉ đăng ký {len(reg)} ảnh, cần ≥ {t_min} keyframe")
    chosen = thin_even(reg, t_max)
    new_name = {old: f"{i:04d}.jpg" for i, old in enumerate(chosen)}
    for im in rec.images.values():
        if rec.is_image_registered(im.image_id) and im.name not in new_name:
            rec.deregister_image(im.image_id)                     # điểm 3D mất quan sát tự bị xoá
    for im in rec.images.values():
        if rec.is_image_registered(im.image_id):
            im.name = new_name[im.name]
    if layout.keyframes.exists():
        shutil.rmtree(layout.keyframes)
    ensure_dir(layout.keyframes)
    out_rows = []
    for old, new in new_name.items():
        shutil.copy2(layout.candidates / old, layout.keyframes / new)
        out_rows.append({**rows[old], "view_id": int(new[:4])})
    write_keyframes_csv(out_rows, layout.metadata / "keyframes.csv")
    full = sparse.parent / "sparse_full"
    if full.exists():
        shutil.rmtree(full)
    full.mkdir()
    shutil.move(str(sparse / "0"), str(full / "0"))
    (sparse / "0").mkdir()
    rec.write(str(sparse / "0"))
    log(f"[sfm] chọn {len(chosen)}/{len(reg)} ảnh đã đăng ký làm keyframe (target {t_min}–{t_max}); model đầy đủ ở {full.name}/0")
    return rec


def run_sfm(layout: SceneLayout, cfg: Dict, exe, log: Callable[[str], None] = print) -> Dict:
    """Stage `sfm`. Đầu vào: `frames/candidates/*.jpg` (tập dày), `metadata/camera.json`, `metadata/candidates.csv`.
    Ra: model đầy đủ `sparse_full/0`, keyframe đã chọn `frames/keyframes/`, `metadata/keyframes.csv`, model rút gọn `sparse/0`, tín hiệu."""
    t0 = time.time()
    cam_path = layout.metadata / "camera.json"
    if not layout.candidates.is_dir() or not cam_path.is_file() or not (layout.metadata / "candidates.csv").is_file():
        raise StageError(E_MISSING_INPUT, "thiếu frames/candidates, metadata/candidates.csv hoặc metadata/camera.json: chạy stage keyframe trước")
    cam = read_json(cam_path)
    n_images = len(list(layout.candidates.glob("*.jpg")))
    sfm = ensure_dir(layout.colmap_sfm)
    db, sparse = sfm / "database.db", sfm / "sparse"
    for stale in (db, sparse, sfm / "sparse_full"):               # làm lại sạch: không trộn với lần chạy trước
        if stale.is_file():
            stale.unlink()
        elif stale.is_dir():
            shutil.rmtree(stale)
    sparse.mkdir()
    use_gpu = bool(cfgmod.require(cfg, "colmap.use_gpu"))
    matcher = str(cfgmod.require(cfg, "colmap.matcher"))
    if matcher not in ("exhaustive", "sequential"):
        raise StageError(E_MISSING_INPUT, f"colmap.matcher phải là exhaustive hoặc sequential, nhận {matcher!r}")
    match_args = exhaustive_matcher_args(db, use_gpu) if matcher == "exhaustive" else sequential_matcher_args(db, cfgmod.get(cfg, "colmap.matcher_overlap"), use_gpu)
    runs = [run_cmd(exe, feature_extractor_args(layout.candidates, db, cam, cfgmod.get(cfg, "colmap.max_image_size"), use_gpu,
                                                cfgmod.get(cfg, "colmap.sift")), log),
            run_cmd(exe, match_args, log),
            run_cmd(exe, mapper_args(db, layout.candidates, sparse, cfgmod.get(cfg, "colmap.mapper")), log)]
    rec, n_models = choose_best_model(sparse)
    n_reg = rec.num_reg_images()                                  # trên tập dày: đây là tỉ lệ đăng ký của tiêu chí M2
    rec = select_keyframes(layout, cfg, sparse, rec, log)
    obs = signals.observations_from_model(rec)
    np.savez_compressed(sfm / "observations.npz", **obs)
    name_to_view = {img.name: iid for iid, img in rec.images.items() if rec.is_image_registered(iid)}
    e_cap = float(cfgmod.require(cfg, "fusion.e_cap_px"))
    map_dir = ensure_dir(sfm / "e_reproj_map")
    h, w = int(cam["h"]), int(cam["w"])
    for name, iid in name_to_view.items():
        sel = obs["image_id"] == iid
        np.save(map_dir / f"{Path(name).stem}.npy", signals.interpolate_e_reproj(obs["xy"][sel], obs["e_reproj"][sel], (h, w), e_cap))
    run = _merge_runs(runs)
    c0 = next(iter(rec.cameras.values()))
    stats = {"n_images": n_images, "n_registered": int(n_reg), "registered_ratio": round(n_reg / max(n_images, 1), 4),
             "n_keyframes": int(rec.num_reg_images()), "n_models": n_models, "n_points3D": len(rec.points3D), "n_observations": int(len(obs["e_reproj"])),
             "mean_reproj_error_px": round(float(rec.compute_mean_reprojection_error()), 4),
             "e_reproj_obs_median_px": round(float(np.median(obs["e_reproj"])), 4) if len(obs["e_reproj"]) else None,
             "camera_model": str(c0.model), "camera_params_refined": [round(float(x), 3) for x in c0.params],
             "camera_params_initial": [cam["fx"], cam["fy"], cam["cx"], cam["cy"]],
             "peak_vram_mib": run["peak_vram_mib"], "baseline_vram_mib": run["baseline_vram_mib"],
             "seconds": round(time.time() - t0, 1)}
    write_json(sfm / "sfm_result.json", stats)
    log(f"[sfm] đăng ký {n_reg}/{n_images} ảnh dày ({stats['registered_ratio'] * 100:.1f}%), giữ {stats['n_keyframes']} keyframe, {stats['n_points3D']:,} điểm 3D, "
        f"{stats['n_observations']:,} quan sát, reproj {stats['mean_reproj_error_px']} px, {n_models} model; "
        f"camera {stats['camera_model']} {stats['camera_params_initial']} → {stats['camera_params_refined']}; {stats['seconds']} s")
    return stats


# ---------------------------------------------------------------------------
# MVS
# ---------------------------------------------------------------------------


def run_mvs(layout: SceneLayout, cfg: Dict, exe, log: Callable[[str], None] = print) -> Dict:
    """Stage `mvs`. Đầu vào: `baselines/colmap/sfm/sparse/0`, keyframes."""
    t0 = time.time()
    model = layout.colmap_sfm / "sparse" / "0"
    if not (model / "images.bin").is_file():
        raise StageError(E_MISSING_INPUT, "thiếu baselines/colmap/sfm/sparse/0: chạy stage sfm trước")
    mvs = layout.colmap_mvs
    if mvs.exists():
        shutil.rmtree(mvs)
    ensure_dir(mvs)
    max_size = cfgmod.get(cfg, "colmap.max_image_size")
    geom = bool(cfgmod.require(cfg, "colmap.geom_consistency"))
    pm = ["patch_match_stereo", "--workspace_path", mvs, "--workspace_format", "COLMAP",
          "--PatchMatchStereo.geom_consistency", 1 if geom else 0]
    if max_size is not None:
        pm += ["--PatchMatchStereo.max_image_size", int(max_size)]
    runs = [run_cmd(exe, ["image_undistorter", "--image_path", layout.keyframes, "--input_path", model, "--output_path", mvs,
                          "--output_type", "COLMAP"], log),
            run_cmd(exe, pm, log),
            run_cmd(exe, ["stereo_fusion", "--workspace_path", mvs, "--workspace_format", "COLMAP",
                          "--input_type", "geometric" if geom else "photometric", "--output_path", mvs / "fused.ply"], log)]
    fused = mvs / "fused.ply"
    if not fused.is_file() or not (mvs / "fused.ply.vis").is_file():
        raise StageError(E_COLMAP_FAILED, "stereo_fusion không tạo fused.ply / fused.ply.vis")
    sig_dir = ensure_dir(mvs / "sigma_depth")
    depth_dir = mvs / "stereo" / "depth_maps"
    n_sigma, valid_frac, sig_vals = 0, [], []
    for p in sorted(depth_dir.glob("*.photometric.bin")):
        g = depth_dir / p.name.replace(".photometric.bin", ".geometric.bin")
        if not g.is_file():
            continue
        s = signals.sigma_depth_map(depth_io.read_depth_map(p), depth_io.read_depth_map(g))
        stem = p.name.replace(".jpg.photometric.bin", "")
        np.save(sig_dir / f"{stem}.npy", s)
        n_sigma += 1
        valid_frac.append(float(np.isfinite(s).mean()))
        sig_vals.append(s[np.isfinite(s)][::50])
    if n_sigma == 0:
        raise StageError(E_COLMAP_FAILED, f"không có cặp depth photometric/geometric trong {depth_dir} (colmap.geom_consistency?)")
    allv = np.concatenate(sig_vals) if sig_vals else np.empty(0)
    n_pts = _count_ply_vertices(fused)
    run = _merge_runs(runs)
    stats = {"n_depth_maps": n_sigma, "n_fused_points": n_pts, "sigma_depth_valid_fraction_mean": round(float(np.mean(valid_frac)), 4),
             "sigma_depth_median_colmap_units": round(float(np.median(allv)), 6) if allv.size else None,
             "fused_ply_mb": round(fused.stat().st_size / 1e6, 1), "peak_vram_mib": run["peak_vram_mib"],
             "baseline_vram_mib": run["baseline_vram_mib"], "seconds": round(time.time() - t0, 1)}
    write_json(mvs / "mvs_result.json", stats)
    log(f"[mvs] {n_sigma} depth map, fused.ply {n_pts:,} điểm ({stats['fused_ply_mb']} MB), σ_depth hợp lệ trung bình "
        f"{stats['sigma_depth_valid_fraction_mean'] * 100:.1f}% pixel; {stats['seconds']} s")
    return stats


def _count_ply_vertices(path: Path) -> int:
    with open(path, "rb") as f:
        for line in f:
            if line.startswith(b"element vertex"):
                return int(line.split()[2])
            if line.startswith(b"end_header"):
                break
    raise ValueError(f"{path}: không thấy 'element vertex' trong header PLY")


def view_names(layout: SceneLayout) -> List[str]:
    """Tên view `NNNN` theo `keyframes.csv` (cùng chỉ số i mọi stage)."""
    return [f"{int(r['view_id']):04d}" for r in read_keyframes_csv(layout.metadata / "keyframes.csv")]
