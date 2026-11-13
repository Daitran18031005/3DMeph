"""Vẽ hai ảnh cố định của một point cloud mét (nhìn từ trên xuống + một góc xiên) để so các biến thể cùng góc nhìn.

Cùng scene thì cùng khung hình: lần đầu ghi `view_params.json` (hộp 1–99% của cloud tham chiếu) vào `--out-dir`, các lần sau
đọc lại file đó (cloud khác vẫn vẽ trong đúng khung). Tên file ra cố định: `<tag>_topdown.png`, `<tag>_view.png` (800×800 px).

    python scripts/render_cloud_views.py --cloud data/scenes/arkitscenes/42897599/proposed/export/model_points.ply \
        --out-dir docs/evidence/m4_improve/baseline_truoc_doi/42897599 --tag proposed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import pipeline  # noqa: F401,E402  (torch trước các thư viện khác)
from pipeline.common.ply import read_ply  # noqa: E402

MAX_POINTS = 300_000
VIEW_AZIM_DEG, VIEW_ELEV_DEG = 35.0, 30.0


def view_box(xyz: np.ndarray) -> dict:
    lo, hi = np.percentile(xyz, 1, axis=0), np.percentile(xyz, 99, axis=0)
    pad = 0.05 * (hi - lo)
    return {"lo": (lo - pad).tolist(), "hi": (hi + pad).tolist()}


def render(xyz: np.ndarray, box: dict, out_dir: Path, tag: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    lo, hi = np.array(box["lo"]), np.array(box["hi"])
    if len(xyz) > MAX_POINTS:
        xyz = xyz[np.random.default_rng(0).choice(len(xyz), MAX_POINTS, replace=False)]
    keep = np.all((xyz >= lo) & (xyz <= hi), axis=1)
    p = xyz[keep]
    c = (p[:, 1] - lo[1]) / max(hi[1] - lo[1], 1e-9)          # tô màu theo chiều cao (y lên)
    fig, ax = plt.subplots(figsize=(8, 8), dpi=100)
    ax.scatter(p[:, 0], p[:, 2], c=c, s=0.3, cmap="viridis", vmin=0, vmax=1, linewidths=0)
    ax.set_xlim(lo[0], hi[0])
    ax.set_ylim(lo[2], hi[2])
    ax.set_aspect("equal")
    ax.set_title(f"{tag}: nhìn từ trên xuống ({len(p):,} điểm)")
    fig.savefig(out_dir / f"{tag}_topdown.png")
    plt.close(fig)
    fig = plt.figure(figsize=(8, 8), dpi=100)
    a3 = fig.add_subplot(111, projection="3d")
    a3.scatter(p[:, 0], p[:, 2], p[:, 1], c=c, s=0.3, cmap="viridis", vmin=0, vmax=1, linewidths=0)
    a3.set_xlim(lo[0], hi[0])
    a3.set_ylim(lo[2], hi[2])
    a3.set_zlim(lo[1], hi[1])
    a3.set_box_aspect((hi[0] - lo[0], hi[2] - lo[2], hi[1] - lo[1]))
    a3.view_init(VIEW_ELEV_DEG, VIEW_AZIM_DEG)
    a3.set_title(f"{tag}: góc xiên")
    fig.savefig(out_dir / f"{tag}_view.png")
    plt.close(fig)


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cloud", required=True, help="PLY mét đã dựng đứng (y lên), ví dụ proposed/export/model_points.ply")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--tag", required=True, help="tiền tố tên ảnh, ví dụ proposed hoặc proposed_b")
    ap.add_argument("--frame-from", help="measurements.json của export (khung R·x + t, COLMAP×s_m → model +Y lên) để dựng đứng cloud của biến thể (refined_points.ply)")
    a = ap.parse_args(argv)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    d = read_ply(a.cloud)
    xyz = np.stack([d["x"], d["y"], d["z"]], axis=1).astype(np.float64)
    if a.frame_from:
        fr = json.loads(Path(a.frame_from).read_text(encoding="utf-8"))["frame"]
        xyz = xyz @ np.array(fr["rotation_from_colmap_metric"]).T + np.array(fr["translation"])
    vp = out / "view_params.json"
    if vp.is_file():
        box = json.loads(vp.read_text(encoding="utf-8"))
    else:
        box = view_box(xyz)
        vp.write_text(json.dumps(box), encoding="utf-8")
    render(xyz, box, out, a.tag)
    print(f"[ok] {out / (a.tag + '_topdown.png')}, {out / (a.tag + '_view.png')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
