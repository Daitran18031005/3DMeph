"""Các biến thể được chấm (ĐC §20 Hình 26) và vị trí đầu ra của chúng.

B0 COLMAP mét · B1 VGGT thuần mét (`b1.py`) · B3 fusion không gate · proposed (+ gate) · abl_quality (Ablation 1: bỏ q_*, fuse + gate).
Ablation 2 (ép plane không cổng) và plane metrics chuyển sang Replica (M5): không có ở đây.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict

import numpy as np

from ..common.io import SceneLayout, read_json

VARIANTS = ["B0", "B1", "B3", "proposed", "abl_quality"]


@dataclass(frozen=True)
class VariantLayout(SceneLayout):
    """Cây của một biến thể có thư mục riêng: `fusion`, `plane_refinement`, `logs` đổi chỗ; các thư mục còn lại giống scene gốc.

    Nhờ vậy `fuse`/`gate` chạy cho `abl_quality` mà không ghi đè `proposed/` và `run_meta.json` của biến thể tách riêng."""

    name: str = ""

    @property
    def fusion(self) -> Path: return self.proposed / "variants" / self.name / "fusion"
    @property
    def plane_refinement(self) -> Path: return self.proposed / "variants" / self.name / "plane_refinement"
    @property
    def logs(self) -> Path: return self.evaluation / "variants" / self.name / "logs"


def base_layout(layout: SceneLayout) -> SceneLayout:
    """Cây scene gốc từ bất kỳ layout nào (kể cả `VariantLayout`)."""
    return SceneLayout(layout.root)


def variant_layout(layout: SceneLayout, variant: str) -> SceneLayout:
    return VariantLayout(layout.root, variant) if variant == "abl_quality" else base_layout(layout)


def cloud_path(layout: SceneLayout, variant: str) -> Path:
    """File point cloud (mét) của biến thể."""
    base = base_layout(layout)
    if variant == "B0":
        return base.colmap_metric / "fused_metric.ply"
    if variant == "B1":
        return base.vggt_metric / "points_metric.ply"
    if variant == "B3":
        return base.fusion / "fused_points.ply"
    if variant == "proposed":
        return base.plane_refinement / "refined_points.ply"
    if variant == "abl_quality":
        return variant_layout(base, variant).plane_refinement / "refined_points.ply"
    raise ValueError(f"biến thể không có: {variant!r} (có: {VARIANTS})")


def camera_centers(layout: SceneLayout, variant: str, load_cameras: Callable[[SceneLayout], Dict[int, Dict]]) -> Dict[int, np.ndarray]:
    """view_id → tâm camera (mét) trong cùng hệ với point cloud của biến thể: COLMAP × `s_m` (B0, B3, proposed, abl_quality) hoặc chuỗi VGGT (B1)."""
    base = base_layout(layout)
    if variant == "B1":
        d = read_json(base.vggt_metric / "cameras_metric.json")
        return {int(k): np.asarray(v, dtype=np.float64) for k, v in d["centers"].items()}
    s_m = float(read_json(base.alignment / "scale.json")["s_m"])
    return {v: np.asarray(c["center"], dtype=np.float64) * s_m for v, c in load_cameras(base).items()}
