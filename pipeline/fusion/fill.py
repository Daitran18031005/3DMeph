"""Lấp lỗ MVS bằng điểm VGGT (M4 đợt 2, hướng A). Không thuộc đề cương [Suy luận].

Ý tưởng: `fuse` chỉ trả điểm tại vị trí điểm MVS nên không phủ hơn MVS. Ở đây thêm điểm VGGT vào những ô voxel MVS không có điểm, chỉ nhận khi
VGGT tin cậy (c_model ≥ ngưỡng) và nhất quán giữa ≥ N view (điểm của ≥ N view khác nhau rơi vào cùng ô). Ô nằm trong lân cận 1 ô quanh điểm MVS bị bỏ để không
sinh mặt kép cạnh bề mặt MVS đã có.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

_B = 1 << 16                                                    # số ô tối đa mỗi trục sau khi dịch gốc (voxel 0,1 m → 6,5 km)
_NEIGH = np.array([(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)], dtype=np.int64)


def _keys(ijk: np.ndarray) -> np.ndarray:
    return (ijk[:, 0] * _B + ijk[:, 1]) * _B + ijk[:, 2]


def fill_points(cand_xyz: np.ndarray, cand_view: np.ndarray, cand_conf: np.ndarray, mvs_xyz: np.ndarray, voxel: float,
                min_views: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Điểm lấp lỗ. Vào: ứng viên VGGT (N, 3) mét với view (N,) và độ tin cậy (N,) đã lọc c_model; điểm MVS (M, 3) mét.
    Ra: (xyz (F, 3) = trọng tâm ô, conf (F,) = c_model trung bình, n_views (F,) số view khác nhau trong ô), chỉ các ô có ≥ min_views view
    và không nằm trong lân cận 1 ô của điểm MVS."""
    if voxel <= 0 or min_views < 1:
        raise ValueError("voxel phải > 0 và min_views ≥ 1")
    if len(cand_xyz) == 0:
        return np.zeros((0, 3)), np.zeros(0), np.zeros(0, int)
    lo = np.floor(np.vstack([cand_xyz, mvs_xyz]).min(axis=0) / voxel).astype(np.int64) - 2
    cij = np.floor(cand_xyz / voxel).astype(np.int64) - lo
    ck = _keys(cij)
    mi = np.unique(np.floor(mvs_xyz / voxel).astype(np.int64) - lo, axis=0)                  # ô có điểm MVS
    near = np.unique(_keys((mi[:, None, :] + _NEIGH[None, :, :]).reshape(-1, 3)))            # cùng 26 ô lân cận
    free = ~np.isin(ck, near)
    ck, xyz, conf, view = ck[free], cand_xyz[free], cand_conf[free], cand_view[free]
    if len(ck) == 0:
        return np.zeros((0, 3)), np.zeros(0), np.zeros(0, int)
    uniq, inv = np.unique(ck, return_inverse=True)
    pair = np.unique(np.stack([inv, view.astype(np.int64)], axis=1), axis=0)                 # (ô, view) khác nhau
    n_views = np.bincount(pair[:, 0], minlength=len(uniq))
    cnt = np.bincount(inv, minlength=len(uniq))
    good = n_views >= min_views
    out_xyz = np.stack([np.bincount(inv, weights=xyz[:, a], minlength=len(uniq)) / np.maximum(cnt, 1) for a in range(3)], axis=1)
    out_conf = np.bincount(inv, weights=conf, minlength=len(uniq)) / np.maximum(cnt, 1)
    return out_xyz[good], out_conf[good], n_views[good]
