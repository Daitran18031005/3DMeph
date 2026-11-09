"""Vùng đánh giá Chamfer/F-score: chọn phần Faro và phần mô hình đem so (kế hoạch 09/11, lệch #46).

Ba chế độ (`eval.region.mode`), cùng một quy tắc cho mọi scene và mọi biến thể:
- `box`: hành vi cũ, cắt theo hộp quỹ đạo camera GT (ARKit) ± `eval.crop_margin_m`. Giữ để đối chiếu số cũ. Hộp phình khi pose ARKit sai (42445022).
- `visible_gt`: chỉ giữ điểm Faro mà ít nhất một keyframe thấy (z-buffer có che khuất, `pipeline/common/visibility.py`). Mô hình không lọc.
- `visible_both`: như `visible_gt`, thêm: chỉ giữ điểm mô hình mà camera thấy VÀ trong bán kính `eval.region.gt_support_m` có điểm Faro đang giữ.

Camera để tính tầm nhìn là camera của MÔ HÌNH (COLMAP, B0) đặt vào hệ scene bằng phép căn bền `lengths.kabsch_rigid_trimmed`, chỉ các view còn lại sau cắt tỉa,
KHÔNG dùng pose ARKit thô (pose sai chính là nguyên nhân phình hộp). Vùng dựng một lần từ camera B0 rồi áp cho mọi biến thể trong scene.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from ..common import config as cfgmod
from ..common.io import SceneLayout
from ..common.schema import read_keyframes_csv
from ..common.visibility import point_visibility
from . import lengths as ln
from .variants import camera_centers

MODES = ("box", "visible_gt", "visible_both")


@dataclass
class Region:
    mode: str
    faro: np.ndarray                                   # điểm Faro đã lọc (hệ scene, mét)
    gt_kept_frac: float
    n_views: int
    box: Optional[Tuple[np.ndarray, np.ndarray]] = None
    cams: List[Dict] = field(default_factory=list)     # camera B0 (hệ scene) cho visible_both
    size: Tuple[int, int] = (0, 0)
    z_range: Tuple[float, float] = (0.5, 4.5)
    margin: int = 20
    occl: float = 0.12
    gt_support: float = 0.10
    dropped_views: List[int] = field(default_factory=list)
    _tree: object = None

    def filter_model(self, model_scene: np.ndarray) -> Tuple[np.ndarray, Optional[float]]:
        """(điểm mô hình giữ lại, tỉ lệ giữ lại). `visible_gt`: không lọc (tỉ lệ None). `box`: tỉ lệ trong hộp (không cắt ở đây, `evaluate_geometry` cắt)."""
        if self.mode == "box":
            lo, hi = self.box
            return model_scene, float(np.all((model_scene >= lo) & (model_scene <= hi), axis=1).mean())
        if self.mode == "visible_gt":
            return model_scene, None
        from scipy.spatial import cKDTree

        if self._tree is None:
            self._tree = cKDTree(self.faro)
        nvis, _ = point_visibility(model_scene, self.cams, self.size, self.margin, self.z_range, occl=self.occl, with_spread=False)
        near = np.isfinite(self._tree.query(model_scene, distance_upper_bound=self.gt_support)[0])
        keep = (nvis >= 1) & near
        return model_scene[keep], float(keep.mean())


def build_region(layout: SceneLayout, cfg: Dict, gt_cams: Dict[int, np.ndarray], faro: np.ndarray,
                 load_cameras: Callable[[SceneLayout], Dict[int, Dict]]) -> Region:
    """Dựng vùng đánh giá một lần cho cả scene (xem docstring module)."""
    mode = str(cfgmod.require(cfg, "eval.region.mode"))
    if mode not in MODES:
        raise ValueError(f"eval.region.mode = {mode!r} không hợp lệ (có: {MODES})")
    if mode == "box":
        pad = float(cfgmod.require(cfg, "eval.crop_margin_m"))
        allc = np.array(list(gt_cams.values()))
        box = (allc.min(axis=0) - pad, allc.max(axis=0) + pad)
        frac = float(np.all((faro >= box[0]) & (faro <= box[1]), axis=1).mean())
        return Region(mode, faro, frac, len(gt_cams), box=box)

    k, iters = float(cfgmod.require(cfg, "eval.align.trim_k")), int(cfgmod.require(cfg, "eval.align.trim_max_iters"))
    cams_cm = load_cameras(layout)
    cen = camera_centers(layout, "B0", load_cameras)                         # COLMAP × s_m (mét), cùng hệ với B0
    views = sorted(set(cen) & set(gt_cams))
    c_mod, c_gt = np.array([cen[v] for v in views]), np.array([gt_cams[v] for v in views])
    r, t, _, keep = ln.kabsch_rigid_trimmed(c_gt, c_mod, k, iters)           # mô hình = R·GT + t
    kept = [v for v, ok in zip(views, keep) if ok]
    cams = []
    for v in kept:
        kk = cams_cm[v]["K"]
        r_wc = cams_cm[v]["R"].T                                             # camera → thế giới COLMAP (cùng hướng với hệ mét của mô hình)
        cams.append({"R": r.T @ r_wc, "c": r.T @ (cen[v] - t), "k": (float(kk[0, 0]), float(kk[1, 1]), float(kk[0, 2]), float(kk[1, 2])), "rot": "none"})
    row = read_keyframes_csv(layout.metadata / "keyframes.csv")[0]
    size = (int(row["w"]), int(row["h"]))                                    # ảnh keyframe đã xoay đứng = ảnh COLMAP
    z_range = tuple(float(x) for x in cfgmod.require(cfg, "eval.region.z_range_m"))
    margin, occl = int(cfgmod.require(cfg, "eval.region.margin_px")), float(cfgmod.require(cfg, "eval.region.occl_m"))
    nvis, _ = point_visibility(faro, cams, size, margin, z_range, occl=occl, with_spread=False)
    seen = nvis >= 1
    return Region(mode, faro[seen], float(seen.mean()), len(kept), cams=cams, size=size, z_range=z_range, margin=margin, occl=occl,
                  gt_support=float(cfgmod.require(cfg, "eval.region.gt_support_m")), dropped_views=[v for v, ok in zip(views, keep) if not ok])
