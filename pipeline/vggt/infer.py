"""Stage `vggt` (ĐC §7.1, §13, kế hoạch §4.3): chạy VGGT-1B theo chunk trên keyframe, lưu camera, depth, confidence và điểm unproject.

- Chia chunk bằng `chunks.chunk_ranges` (c = `vggt.chunk`, o = `vggt.overlap`, công thức (2)); mỗi chunk có hệ camera riêng (camera đầu chunk là gốc), CHƯA mét.
- Ảnh đứng 480×640 được tiền xử lý bằng chế độ **`pad`** của VGGT (không `crop`: crop cắt mất khoảng 25% chiều cao): thu nhỏ cạnh dài về 518, làm tròn cạnh ngắn
  về bội số của 14, đệm trắng thành 518×518. `pad_geometry` mô tả đúng phép biến đổi này để ánh xạ pixel VGGT ↔ pixel ảnh gốc (fusion cần).
- Depth head rồi unproject (README VGGT: thường chính xác hơn nhánh point map); `c_model = 1 − 1/conf` ((19), `outputs.conf_to_c_model`).
- Chạy tuần tự từng chunk, giải phóng bộ nhớ GPU giữa các chunk; đo peak VRAM bằng `torch.cuda.max_memory_allocated`. Hết bộ nhớ thì `E_CUDA_OOM` (dừng và báo).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from ..common import config as cfgmod
from ..common.errors import E_CUDA_OOM, E_MISSING_INPUT, StageError
from ..common.io import SceneLayout, ensure_dir, read_json, write_json
from ..common.schema import read_keyframes_csv
from .chunks import chunk_ranges
from .outputs import conf_to_c_model

VGGT_SIZE = 518
PATCH = 14


# ---------------------------------------------------------------------------
# Hình học của chế độ `pad`
# ---------------------------------------------------------------------------


def pad_geometry(width: int, height: int, target: int = VGGT_SIZE, patch: int = PATCH) -> Dict:
    """Phép biến đổi pixel ảnh gốc → ảnh VGGT (đúng với `load_and_preprocess_images(mode="pad")` của repo VGGT).

    Toạ độ liên tục, mép pixel ở số nguyên (như COLMAP): `u_vggt = u·scale_x + pad_left`, `v_vggt = v·scale_y + pad_top`.
    `scale_x` ≠ `scale_y` một chút vì cạnh ngắn bị làm tròn về bội số của 14 (480×640 → 392×518: 0,8167 và 0,8094)."""
    if width >= height:
        new_w = target
        new_h = round(height * (new_w / width) / patch) * patch
    else:
        new_h = target
        new_w = round(width * (new_h / height) / patch) * patch
    pad_left = (target - new_w) // 2
    pad_top = (target - new_h) // 2
    return {"orig_w": int(width), "orig_h": int(height), "new_w": int(new_w), "new_h": int(new_h), "pad_left": int(pad_left),
            "pad_top": int(pad_top), "scale_x": new_w / width, "scale_y": new_h / height, "size": int(target)}


def original_to_vggt(uv, geo: Dict) -> np.ndarray:
    uv = np.atleast_2d(np.asarray(uv, dtype=np.float64))
    return np.stack([uv[:, 0] * geo["scale_x"] + geo["pad_left"], uv[:, 1] * geo["scale_y"] + geo["pad_top"]], axis=1)


def vggt_to_original(uv, geo: Dict) -> np.ndarray:
    uv = np.atleast_2d(np.asarray(uv, dtype=np.float64))
    return np.stack([(uv[:, 0] - geo["pad_left"]) / geo["scale_x"], (uv[:, 1] - geo["pad_top"]) / geo["scale_y"]], axis=1)


def vggt_dtype(name: str):
    """`vggt.dtype`: bf16, fp16 hoặc fp32 → (torch.dtype, dùng autocast?)."""
    import torch
    table = {"bf16": (torch.bfloat16, True), "fp16": (torch.float16, True), "fp32": (torch.float32, False)}
    if name not in table:
        raise ValueError(f"vggt.dtype không hợp lệ: {name!r} (bf16, fp16, fp32)")
    return table[name]


# ---------------------------------------------------------------------------
# Mô hình và chạy một chunk
# ---------------------------------------------------------------------------


def load_model(weights_dir: Path, device: str, dtype_name: str = "fp32"):
    """Nạp VGGT-1B từ thư mục có `config.json` và `model.safetensors` (không tải mạng). bf16/fp16: ép trọng số aggregator về dtype đó
    (fp32 ~5 GB không vừa GPU 8 GB cùng activation của chunk 12 ảnh)."""
    from vggt.models.vggt import VGGT
    weights_dir = Path(weights_dir)
    if not (weights_dir / "model.safetensors").is_file() or not (weights_dir / "config.json").is_file():
        raise StageError(E_MISSING_INPUT, f"thiếu config.json hoặc model.safetensors trong {weights_dir} (cấu hình vggt.weights_dir)")
    model = VGGT.from_pretrained(str(weights_dir))
    # Chỉ aggregator (phần lớn tham số) ép dtype; head chạy ngoài autocast (vggt.py: autocast(enabled=False)) nên giữ fp32 như bản gốc.
    model.aggregator.to(vggt_dtype(dtype_name)[0])
    return model.eval().to(device)


def run_chunk(model, image_paths: List[Path], device: str, dtype_name: str) -> Dict[str, np.ndarray]:
    """Một lượt VGGT trên các ảnh của chunk. Trả về extrinsic (S,3,4) world→camera đầu chunk, intrinsic (S,3,3) trên ảnh 518×518,
    depth (S,H,W), depth_conf (S,H,W) ∈ [1, ∞), points (S,H,W,3) đv VGGT."""
    import torch
    from vggt.utils.geometry import unproject_depth_map_to_point_map
    from vggt.utils.load_fn import load_and_preprocess_images
    from vggt.utils.pose_enc import pose_encoding_to_extri_intri

    dtype, use_amp = vggt_dtype(dtype_name)
    images = load_and_preprocess_images([str(p) for p in image_paths], mode="pad").to(device)
    with torch.no_grad():
        if use_amp:
            with torch.autocast(device_type=torch.device(device).type, dtype=dtype):
                pred = model(images)
        else:
            pred = model(images)
        extri, intri = pose_encoding_to_extri_intri(pred["pose_enc"], images.shape[-2:])
        depth = pred["depth"].float().squeeze(0).squeeze(-1)
        conf = pred["depth_conf"].float().squeeze(0)
    extri_np, intri_np = extri.squeeze(0).float().cpu().numpy(), intri.squeeze(0).float().cpu().numpy()
    depth_np, conf_np = depth.cpu().numpy(), conf.cpu().numpy()
    points = unproject_depth_map_to_point_map(depth_np[..., None], extri_np, intri_np).astype(np.float32)
    return {"extrinsic": extri_np.astype(np.float32), "intrinsic": intri_np.astype(np.float32), "depth": depth_np.astype(np.float32),
            "depth_conf": conf_np.astype(np.float32), "points": points}


def resolve_weights_dir(cfg: Dict, root: Optional[Path] = None) -> Path:
    """`vggt.weights_dir` tương đối so với thư mục gốc repo (hoặc `root`)."""
    from ..common.config import REPO_ROOT
    p = Path(str(cfgmod.require(cfg, "vggt.weights_dir")))
    return p if p.is_absolute() else (Path(root) if root else REPO_ROOT) / p


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------


def run_vggt(layout: SceneLayout, cfg: Dict, log: Callable[[str], None] = print, device: Optional[str] = None,
             load: Callable = load_model, weights_dir: Optional[Path] = None) -> Dict:
    """Stage `vggt`. Đầu vào: `frames/keyframes/NNNN.jpg`, `metadata/keyframes.csv`. Ghi `baselines/vggt/chunk_XX/{vggt_raw,vggt_out}.npz`, `chunk_meta.json`."""
    import torch

    t0 = time.time()
    c = int(cfgmod.require(cfg, "vggt.chunk"))
    o = int(cfgmod.require(cfg, "vggt.overlap"))
    dtype_name = str(cfgmod.require(cfg, "vggt.dtype"))
    if str(cfgmod.require(cfg, "vggt.c_model_map")) != "one_minus_inv":
        raise ValueError("vggt.c_model_map chỉ hỗ trợ one_minus_inv")
    csv_path = layout.metadata / "keyframes.csv"
    if not csv_path.is_file() or not layout.keyframes.is_dir():
        raise StageError(E_MISSING_INPUT, "thiếu metadata/keyframes.csv hoặc frames/keyframes: chạy stage keyframe trước")
    rows = read_keyframes_csv(csv_path)
    n_kf = len(rows)
    paths = [layout.keyframes / f"{int(r['view_id']):04d}.jpg" for r in rows]
    missing = [p.name for p in paths if not p.is_file()]
    if missing:
        raise StageError(E_MISSING_INPUT, f"thiếu keyframe: {missing[:3]}...")
    geo = pad_geometry(int(rows[0]["w"]), int(rows[0]["h"]))
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    wdir = Path(weights_dir) if weights_dir else resolve_weights_dir(cfg)
    ranges = chunk_ranges(n_kf, c, o)
    log(f"[vggt] {n_kf} keyframe → {len(ranges)} chunk (c={c}, o={o}); ảnh {geo['orig_w']}×{geo['orig_h']} → pad {geo['new_w']}×{geo['new_h']} "
        f"trong {geo['size']}×{geo['size']} (đệm trái {geo['pad_left']}, trên {geo['pad_top']}); {dtype_name} trên {device}")
    if device == "cuda":
        frac = float(cfgmod.require(cfg, "vggt.vram_fraction"))
        if frac:
            torch.cuda.set_per_process_memory_fraction(frac)
        torch.cuda.reset_peak_memory_stats()
    t_load = time.time()
    model = load(wdir, device, dtype_name)
    load_s = time.time() - t_load
    base_dir = ensure_dir(layout.vggt)
    chunks_meta, idn = [], []
    try:
        for k, (a, b) in enumerate(ranges):
            ck = ensure_dir(base_dir / f"chunk_{k:02d}")
            tc = time.time()
            try:
                out = run_chunk(model, paths[a:b], device, dtype_name)
            except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
                if not isinstance(e, torch.cuda.OutOfMemoryError) and "out of memory" not in str(e):
                    raise
                raise StageError(E_CUDA_OOM, f"hết bộ nhớ GPU ở chunk {k} ({b - a} ảnh, vggt.chunk = {c}); giảm vggt.chunk hoặc báo người dùng")
            np.savez_compressed(ck / "vggt_raw.npz", extrinsic=out["extrinsic"], intrinsic=out["intrinsic"], depth=out["depth"],
                                depth_conf=out["depth_conf"])
            np.savez_compressed(ck / "vggt_out.npz", c_model=conf_to_c_model(out["depth_conf"]).astype(np.float32), points=out["points"])
            ident = float(np.abs(out["extrinsic"][0] - np.hstack([np.eye(3), np.zeros((3, 1))])).max())
            idn.append(ident)
            meta = {"chunk": k, "start": a, "end": b, "views": [int(r["view_id"]) for r in rows[a:b]], "pad_geometry": geo,
                    "seconds": round(time.time() - tc, 2), "depth_median": float(np.median(out["depth"])),
                    "conf_median": float(np.median(out["depth_conf"])), "camera0_identity_err": ident,
                    "peak_vram_mib": round(torch.cuda.max_memory_allocated() / 2**20, 1) if device == "cuda" else None}
            write_json(ck / "chunk_meta.json", meta)
            chunks_meta.append(meta)
            log(f"[vggt] chunk {k:02d} ảnh [{a}, {b}): {meta['seconds']} s, depth trung vị {meta['depth_median']:.3f}, conf trung vị {meta['conf_median']:.2f}, "
                f"|camera0 − I|max {ident:.2e}" + (f", peak VRAM {meta['peak_vram_mib']} MiB" if device == "cuda" else ""))
            del out
            if device == "cuda":
                torch.cuda.empty_cache()
    finally:
        del model
        if device == "cuda":
            try:
                torch.cuda.empty_cache()
            except RuntimeError:        # ngữ cảnh CUDA đã hỏng sau OOM: không che lỗi gốc
                pass
    peak = round(torch.cuda.max_memory_allocated() / 2**20, 1) if device == "cuda" else None
    stats = {"n_keyframes": n_kf, "n_chunks": len(ranges), "chunk": c, "overlap": o, "dtype": dtype_name, "device": device,
             "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None, "model_load_seconds": round(load_s, 1),
             "peak_vram_mib": peak, "peak_vram_reserved_mib": round(torch.cuda.max_memory_reserved() / 2**20, 1) if device == "cuda" else None,
             "camera0_identity_err_max": max(idn), "pad_geometry": geo, "chunks": [{k: m[k] for k in ("chunk", "start", "end", "seconds")} for m in chunks_meta],
             "weights_dir": str(wdir), "seconds": round(time.time() - t0, 1)}
    write_json(base_dir / "vggt_result.json", stats)
    log(f"[vggt] xong {len(ranges)} chunk trong {stats['seconds']} s (nạp mô hình {stats['model_load_seconds']} s); peak VRAM {peak} MiB; "
        f"camera đầu chunk lệch gốc tối đa {stats['camera0_identity_err_max']:.2e}")
    return stats


def read_chunk(layout: SceneLayout, k: int) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray], Dict]:
    """Đọc lại chunk k: (vggt_raw, vggt_out, chunk_meta) — dùng ở align và fuse."""
    ck = layout.vggt / f"chunk_{k:02d}"
    return dict(np.load(ck / "vggt_raw.npz")), dict(np.load(ck / "vggt_out.npz")), read_json(ck / "chunk_meta.json")
