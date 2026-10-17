"""Hợp đồng I/O giữa các stage (xem README gốc, mục "Luồng dữ liệu").

Mỗi mũi tên của dataflow là một file; tên cột/trường được định nghĩa một chỗ ở đây.
Đơn vị: px, mét hoặc "đv" (đơn vị mô hình, chưa mét). Chỉ số: i = view, k = điểm.
"""

from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from .io import ensure_dir, read_json, write_json

# metadata/keyframes.csv — một dòng cho mỗi view i
KEYFRAME_COLUMNS = [
    "view_id", "frame_ts", "src_name", "V", "q_blur", "q_exposure",
    "sky_direction", "rot_applied", "w", "h", "fx", "fy", "cx", "cy",
]

# baselines/colmap/sfm/observations.npz — một phần tử cho mỗi quan sát (i, điểm 3D)
OBSERVATION_FIELDS = ("image_id", "point3d_id", "xy", "e_reproj")  # e_reproj: px

# proposed/fusion/fusion_log.npz — một phần tử cho mỗi (i, k)
FUSION_LOG_FIELDS = ("view", "point", "c_model", "f_e", "f_sigma",
                     "q_blur", "q_texture", "q_exposure", "w", "w_tilde")

# proposed/plane_refinement/refined_points.ply — thuộc tính cho mỗi điểm k
REFINED_FIELDS = ("x", "y", "z", "g_k", "s_k", "r_k", "theta_k")


@dataclass
class Sim3Result:
    """proposed/alignment/chunk_XX_sim3.json. s: đv COLMAP trên mỗi đv VGGT."""

    s: float
    R: List[List[float]]
    t: List[float]
    n_pairs: int
    n_inliers: int
    rmse: float

    def to_json(self, path: os.PathLike) -> None:
        write_json(path, asdict(self))

    @staticmethod
    def from_json(path: os.PathLike) -> "Sim3Result":
        return Sim3Result(**read_json(path))

    def matrices(self):
        return float(self.s), np.asarray(self.R, dtype=np.float64), np.asarray(self.t, dtype=np.float64)


@dataclass
class ScaleInfo:
    """proposed/alignment/scale.json. s_m = L_real / L_model  (4), đơn vị m/đv COLMAP."""

    s_m: float
    L_real: float
    L_model: float
    anchor_id: str

    def to_json(self, path: os.PathLike) -> None:
        write_json(path, asdict(self))

    @staticmethod
    def from_json(path: os.PathLike) -> "ScaleInfo":
        return ScaleInfo(**read_json(path))


def write_keyframes_csv(rows: List[Dict[str, Any]], path: os.PathLike) -> None:
    ensure_dir(Path(path).parent)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=KEYFRAME_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in KEYFRAME_COLUMNS})


def read_keyframes_csv(path: os.PathLike) -> List[Dict[str, str]]:
    with open(path, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if rows and list(rows[0].keys()) != KEYFRAME_COLUMNS:
        raise ValueError(f"{path}: cột không khớp KEYFRAME_COLUMNS: {list(rows[0].keys())}")
    return rows
