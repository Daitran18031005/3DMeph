"""Đọc/ghi file và cây thư mục một scene theo Mục 9 của đề cương (ĐC §9)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np

from .geometry import rodrigues


def ensure_dir(path: os.PathLike) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_json(path: os.PathLike) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: os.PathLike, obj: Any) -> None:
    ensure_dir(Path(path).parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)


@dataclass(frozen=True)
class SceneLayout:
    """Cây thư mục một scene (ĐC §9): raw, frames, metadata, ground_truth, baselines, proposed, evaluation.

    Thư mục `alignment/` và `export/` trong `proposed/`, thư mục `faro/` trong `ground_truth/` KHÔNG có
    trong đề cương; được thêm theo kế hoạch của nhóm.
    """

    root: Path

    @property
    def raw(self) -> Path: return self.root / "raw"
    @property
    def frames(self) -> Path: return self.root / "frames"
    @property
    def candidates(self) -> Path: return self.frames / "candidates"
    @property
    def keyframes(self) -> Path: return self.frames / "keyframes"
    @property
    def metadata(self) -> Path: return self.root / "metadata"
    @property
    def ground_truth(self) -> Path: return self.root / "ground_truth"
    @property
    def faro(self) -> Path: return self.ground_truth / "faro"
    @property
    def baselines(self) -> Path: return self.root / "baselines"
    @property
    def colmap(self) -> Path: return self.baselines / "colmap"
    @property
    def colmap_sfm(self) -> Path: return self.colmap / "sfm"
    @property
    def colmap_mvs(self) -> Path: return self.colmap / "mvs"
    @property
    def colmap_metric(self) -> Path: return self.colmap / "metric"
    @property
    def vggt(self) -> Path: return self.baselines / "vggt"
    @property
    def vggt_metric(self) -> Path: return self.vggt / "metric"
    @property
    def proposed(self) -> Path: return self.root / "proposed"
    @property
    def alignment(self) -> Path: return self.proposed / "alignment"
    @property
    def fusion(self) -> Path: return self.proposed / "fusion"
    @property
    def plane_refinement(self) -> Path: return self.proposed / "plane_refinement"
    @property
    def export(self) -> Path: return self.proposed / "export"
    @property
    def evaluation(self) -> Path: return self.root / "evaluation"
    @property
    def logs(self) -> Path: return self.evaluation / "logs"
    @property
    def figures(self) -> Path: return self.evaluation / "figures"

    def make_dirs(self) -> None:
        for p in (self.raw, self.candidates, self.keyframes, self.metadata, self.faro,
                  self.colmap_sfm, self.colmap_mvs, self.colmap_metric, self.vggt_metric,
                  self.alignment, self.fusion, self.plane_refinement, self.export,
                  self.logs, self.figures):
            ensure_dir(p)


def scene_layout(data_root: os.PathLike, dataset: str, scene_id: str) -> SceneLayout:
    """data_root/<dataset>/<scene_id>, ví dụ data/scenes/arkitscenes/42444738."""
    return SceneLayout(Path(data_root) / dataset / str(scene_id))


# ---------------------------------------------------------------------------
# Định dạng ARKitScenes (ĐC §10.2)
# ---------------------------------------------------------------------------


def frame_id_from_name(name: str) -> str:
    """frame_id = phần sau dấu '_' đầu tiên của tên file bỏ đuôi: '47333462_5201.456.png' → '5201.456'."""
    stem, _ext = os.path.splitext(os.path.basename(name))
    if "_" not in stem:
        raise ValueError(f"tên file không có dạng <video_id>_<frame_id>: {name!r}")
    return stem.split("_", 1)[1]


def parse_traj_line(line: str) -> Tuple[float, np.ndarray, np.ndarray]:
    """Một dòng .traj: 'timestamp rx ry rz tx ty tz' (angle-axis rad, tịnh tiến m).

    Trả về (timestamp, R_cw, t_cw) là phép biến đổi world→camera (cần đảo theo (5) khi muốn tâm camera).
    """
    parts = line.split()
    if len(parts) != 7:
        raise ValueError(f"dòng .traj cần 7 số, nhận {len(parts)}: {line!r}")
    ts = float(parts[0])
    r = rodrigues(np.array([float(v) for v in parts[1:4]]))
    t = np.array([float(v) for v in parts[4:7]])
    return ts, r, t


def read_traj(path: os.PathLike):
    """Đọc cả file .traj thành danh sách (timestamp, R_cw, t_cw)."""
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(parse_traj_line(line))
    return out


def parse_pincam(text: str) -> Dict[str, float]:
    """File .pincam: 6 số 'width height fx fy cx cy'."""
    parts = text.split()
    if len(parts) != 6:
        raise ValueError(f".pincam cần 6 số, nhận {len(parts)}")
    w, h, fx, fy, cx, cy = (float(v) for v in parts)
    return {"w": int(w), "h": int(h), "fx": fx, "fy": fy, "cx": cx, "cy": cy}
