"""Điều phối các stage của pipeline 3DMeph trên một scene (kế hoạch §3, §10 M1).

    python -m pipeline.run --scene arkitscenes/<video_id> --config configs/default.yaml [--from-stage X] [--to-stage Y]

Chín stage theo thứ tự: keyframe, sfm, mvs, vggt, align, fuse, gate, export, eval. Các stage chỉ giao tiếp qua file trong
`data/scenes/<dataset>/<video_id>/`. Mỗi stage ghi một mục vào `evaluation/logs/run_meta.json` (trạng thái, thời gian, peak VRAM, mã lỗi,
số liệu của stage) cùng `config_hash`. Stage chưa cài báo `E_NOT_IMPLEMENTED`.

Mã thoát: 0 mọi stage trong khoảng đã chạy xong; 1 lỗi đầu vào (scene held-out, thiếu scene, cấu hình); 2 một stage thất bại (kèm mã lỗi).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .common import config as cfgmod
from .common import splits as sp
from .common.errors import E_NOT_IMPLEMENTED, StageError
from .common.io import SceneLayout, ensure_dir, read_json, scene_layout, write_json

STAGES: List[str] = ["keyframe", "sfm", "mvs", "vggt", "align", "fuse", "gate", "export", "eval"]
NOT_IMPLEMENTED = {"eval": "M3"}
REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------


def resolve_scene(root: Path, scene: str, cfg: Dict, allow_heldout: bool = False) -> Dict:
    """`arkitscenes/<video_id>` → thông tin từ `data/splits.csv` (kiểm `splits.lock`). Scene held-out bị chặn trừ khi `allow_heldout`."""
    if scene.startswith("self_collected/"):
        return resolve_video_scene(root, scene, cfg)
    try:
        dataset, vid = scene.split("/", 1)
    except ValueError:
        raise ValueError(f"--scene cần dạng arkitscenes/<video_id>, nhận {scene!r}")
    if dataset != "arkitscenes":
        raise ValueError(f"chưa hỗ trợ dataset {dataset!r}")
    splits_csv = root / "data" / "splits.csv"
    splits = sp.load_splits(splits_csv)
    if vid not in splits:
        raise ValueError(f"scene {vid} không có trong splits.csv")
    if splits[vid] == sp.SPLIT_HELDOUT and not allow_heldout:
        raise sp.HeldoutError(f"scene {vid} là held-out: chạy đúng một lần ở M4, cần --allow-heldout và không được chỉnh tham số sau đó")
    row = next(r for r in sp.read_rows(splits_csv) if r["video_id"] == vid)
    return {"dataset": dataset, "video_id": vid, "split": splits[vid], "visit_id": row["visit_id"], "sky_direction": row["sky_direction"],
            "raw_dir": root / row["source_dir"], "layout": scene_layout(root / cfgmod.require(cfg, "paths.data_root"), dataset, vid)}


def resolve_video_scene(root: Path, scene: str, cfg: Dict) -> Dict:
    """`self_collected/<id>` → video điện thoại duy nhất (mp4/mov/m4v) trong `video.source_dir/<id>/`. Không copy video, không ghi vào `data/raw`;
    scene tự thu không nằm trong `splits.csv` (không có V_ref/G_ref hay ngưỡng nào được chỉnh trên nó)."""
    from .common.adapters import VIDEO_EXTENSIONS
    dataset, vid = scene.split("/", 1)
    src = root / cfgmod.require(cfg, "video.source_dir") / vid
    files = sorted(p for p in src.iterdir() if p.suffix.lower() in VIDEO_EXTENSIONS) if src.is_dir() else []
    if len(files) != 1:
        raise FileNotFoundError(f"cần đúng 1 video {'/'.join(VIDEO_EXTENSIONS)} trong {src}, thấy {len(files)}")
    return {"dataset": dataset, "video_id": vid, "split": "self_collected", "visit_id": "", "sky_direction": "video", "raw_dir": src,
            "video_path": files[0], "layout": scene_layout(root / cfgmod.require(cfg, "paths.data_root"), dataset, vid)}


# ---------------------------------------------------------------------------
# run_meta.json
# ---------------------------------------------------------------------------


def git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "?"


def torch_peak_vram_mib() -> Optional[float]:
    try:
        import torch
        return round(torch.cuda.max_memory_allocated() / 2**20, 1) if torch.cuda.is_available() else None
    except Exception:
        return None


def torch_reset_peak() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:
        pass


def update_run_meta(layout: SceneLayout, scene: str, cfg: Dict, stage: str, entry: Dict) -> Path:
    path = ensure_dir(layout.logs) / "run_meta.json"
    meta = read_json(path) if path.is_file() else {"stages": {}}
    meta.update(scene=scene, config_hash=cfgmod.config_hash(cfg), git_head=git_head(), updated=time.strftime("%Y-%m-%dT%H:%M:%S"))
    meta.setdefault("stages", {})[stage] = entry
    write_json(path, meta)
    return path


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------


def _stage_keyframe(ctx: Dict, log) -> Dict:
    if ctx["info"].get("video_path"):                     # dữ liệu tự thu: nguồn là video điện thoại
        from .keyframe.extract import extract_video_keyframes
        info = ctx["info"]
        return extract_video_keyframes(info["video_path"], info["layout"], ctx["cfg"],
                                       source_info={"dataset": info["dataset"], "video_id": info["video_id"], "split": info["split"]}, log=log)
    from .keyframe.extract import extract_keyframes
    info = ctx["info"]
    return extract_keyframes(info["raw_dir"], info["layout"], ctx["cfg"], info["sky_direction"],
                             source_info={"dataset": info["dataset"], "video_id": info["video_id"], "split": info["split"],
                                          "visit_id": info["visit_id"]}, log=log)


def _stage_sfm(ctx: Dict, log) -> Dict:
    from .colmap.run_colmap import run_sfm
    return run_sfm(ctx["info"]["layout"], ctx["cfg"], cfgmod.resolve_colmap_exe(ctx["cfg"]), log)


def _stage_mvs(ctx: Dict, log) -> Dict:
    from .colmap.run_colmap import run_mvs
    return run_mvs(ctx["info"]["layout"], ctx["cfg"], cfgmod.resolve_colmap_exe(ctx["cfg"]), log)


def _stage_vggt(ctx: Dict, log) -> Dict:
    from .vggt.infer import run_vggt
    return run_vggt(ctx["info"]["layout"], ctx["cfg"], log)


def _stage_align(ctx: Dict, log) -> Dict:
    from .alignment.stage import run_align
    return run_align(ctx["info"]["layout"], ctx["cfg"], log)


def _stage_fuse(ctx: Dict, log) -> Dict:
    from .fusion.stage import run_fuse
    return run_fuse(ctx["info"]["layout"], ctx["cfg"], log)


def _stage_gate(ctx: Dict, log) -> Dict:
    from .plane_gate.stage import run_gate
    return run_gate(ctx["info"]["layout"], ctx["cfg"], log)


def _stage_export(ctx: Dict, log) -> Dict:
    from .export.mesh import run_export
    return run_export(ctx["info"]["layout"], ctx["cfg"], log)


IMPLEMENTED: Dict[str, Callable[[Dict, Callable[[str], None]], Dict]] = {"keyframe": _stage_keyframe, "sfm": _stage_sfm, "mvs": _stage_mvs,
                                                                         "vggt": _stage_vggt, "align": _stage_align, "fuse": _stage_fuse,
                                                                         "gate": _stage_gate, "export": _stage_export}


def _stage_eval(ctx: Dict, log) -> Dict:
    from .eval.stage import run_eval
    return run_eval(ctx["info"]["layout"], ctx["cfg"], log, [ctx["variant"]] if ctx.get("variant") else None)


IMPLEMENTED["eval"] = _stage_eval


def run_stage(name: str, ctx: Dict, log: Callable[[str], None] = print) -> Dict:
    """Chạy một stage và ghi `run_meta.json`. Ném `StageError` khi thất bại (đã ghi mục lỗi trước khi ném)."""
    info, cfg = ctx["info"], ctx["cfg"]
    t0 = time.time()
    torch_reset_peak()
    entry: Dict = {"status": "running", "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        if name not in IMPLEMENTED:
            raise StageError(E_NOT_IMPLEMENTED, f"stage {name} chưa cài ({NOT_IMPLEMENTED.get(name, '?')})")
        stats = IMPLEMENTED[name](ctx, log)
        entry.update(status="ok", error_code=None, stats=stats)
    except StageError as e:
        entry.update(status="failed", error_code=e.code, error=e.message)
        raise
    except Exception as e:      # lỗi ngoài dự kiến: vẫn ghi vào run_meta thay vì để "running"
        entry.update(status="failed", error_code="E_UNEXPECTED", error=f"{type(e).__name__}: {e}")
        raise
    finally:
        entry["seconds"] = round(time.time() - t0, 1)
        vram = (entry.get("stats") or {}).get("peak_vram_mib")
        entry["peak_vram_mib"] = vram if vram is not None else torch_peak_vram_mib()
        update_run_meta(info["layout"], f"{info['dataset']}/{info['video_id']}", cfg, name, entry)
    return stats


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Chạy pipeline 3DMeph trên một scene")
    ap.add_argument("--scene", required=True, help="arkitscenes/<video_id>")
    ap.add_argument("--config", default=str(cfgmod.DEFAULT_CONFIG))
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--from-stage", choices=STAGES, default=STAGES[0])
    ap.add_argument("--to-stage", choices=STAGES, default="export", help="mặc định export: stage eval hoãn sang M3 (NOT_IMPLEMENTED)")
    ap.add_argument("--variant", default=None, choices=["proposed", "B0", "B1", "B3", "abl_quality"],
                    help="mặc định (không ghi): fuse/gate/export chạy proposed, eval chấm mọi biến thể có đầu ra; B0/B1/B3 chỉ cho eval; abl_quality cho fuse, gate, eval")
    ap.add_argument("--allow-heldout", action="store_true", help="cho phép scene held-out (chỉ M4, đúng một lần)")
    args = ap.parse_args(argv)

    root = Path(args.root)
    i0, i1 = STAGES.index(args.from_stage), STAGES.index(args.to_stage)
    if i0 > i1:
        print(f"[LỖI] --from-stage {args.from_stage} đứng sau --to-stage {args.to_stage}")
        return 1
    try:
        cfg = cfgmod.load_config(args.config)
        info = resolve_scene(root, args.scene, cfg, args.allow_heldout)
    except (sp.HeldoutError, sp.LockError, ValueError, FileNotFoundError, KeyError) as e:
        print(f"[LỖI] {type(e).__name__}: {e}")
        return 1
    ctx = {"info": info, "cfg": cfg}
    ctx["variant"] = args.variant
    todo = STAGES[i0:i1 + 1]
    if args.variant in ("B0", "B1", "B3") and todo != ["eval"]:
        print(f"[LỖI] --variant {args.variant} chỉ dùng với --from-stage eval --to-stage eval (B0/B1/B3 do các stage proposed và eval dựng)")
        return 1
    if args.variant == "abl_quality":
        if not set(todo) <= {"fuse", "gate", "eval"} or ("eval" in todo and len(todo) > 1):
            print("[LỖI] --variant abl_quality chỉ chạy --from-stage fuse --to-stage gate, hoặc riêng stage eval")
            return 1
        import copy

        from .eval.variants import VariantLayout
        ctx["info"] = {**info, "layout": VariantLayout(info["layout"].root, "abl_quality")}
        ctx["cfg"] = copy.deepcopy(cfg)
        ctx["cfg"]["fusion"]["use_quality"] = False
    print(f"[run] {args.scene} ({info['split']}, sky {info['sky_direction']}); stage {args.from_stage} → {args.to_stage}; config_hash "
          f"{cfgmod.config_hash(cfg)[:12]}")
    t0 = time.time()
    for name in STAGES[i0:i1 + 1]:
        print(f"[run] === stage {name} ===")
        try:
            run_stage(name, ctx)
        except StageError as e:
            print(f"[DỪNG] stage {name} thất bại: {e}")
            return 2
    print(f"[run] xong {args.from_stage} → {args.to_stage} trong {time.time() - t0:.0f} s; "
          f"run_meta: {info['layout'].logs / 'run_meta.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
