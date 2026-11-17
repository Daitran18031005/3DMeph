"""Scale mét cho gói quay của app (M6): quỹ đạo AR (ARCore) hoặc mốc thước dây định vị bằng AR.

Gói quay nằm ở `raw/capture/capture.json` (xem app/README.md): mỗi khung có intrinsics và `T_cam_world` (4×4, world→camera, quy ước OpenCV,
mét, hệ AR). Hai chế độ (`scale_mode`):
- `ar`: `s_m` = scale Umeyama bền giữa tâm camera COLMAP và tâm camera AR [Suy luận; lệch ĐC §8.1, không phải mốc (4)].
- `tape`: đầu mút A, B (hệ AR) được chiếu vào các keyframe đã đăng ký → quan sát pixel → tam giác hoá bằng camera COLMAP (`anchor_from_clicks`)
  → `L_model`; `s_m = L_real / L_model` theo (4). AR chỉ định vị đầu mút, không quyết định scale.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..common.geometry import umeyama_sim3
from ..common.io import SceneLayout, read_json
from ..common.schema import read_keyframes_csv

MIN_CAMERAS = 5


def capture_path(layout: SceneLayout) -> Path:
    return layout.raw / "capture" / "capture.json"


def load_capture(layout: SceneLayout) -> Optional[Dict]:
    p = capture_path(layout)
    return read_json(p) if p.is_file() else None


def ar_cameras(layout: SceneLayout, capture: Dict) -> Dict[int, Dict]:
    """view_id (keyframes.csv) → {K, R, t, center} theo pose AR của đúng khung nguồn (`src_name`); K lấy từ keyframes.csv (đã theo kích thước ảnh ứng viên)."""
    frames = {f["name"]: f for f in capture["frames"]}
    out: Dict[int, Dict] = {}
    for r in read_keyframes_csv(layout.metadata / "keyframes.csv"):
        f = frames.get(r["src_name"])
        if f is None:
            continue
        t_cw = np.asarray(f["T_cam_world"], dtype=np.float64)
        rot, t = t_cw[:3, :3], t_cw[:3, 3]
        k = np.array([[float(r["fx"]), 0, float(r["cx"])], [0, float(r["fy"]), float(r["cy"])], [0, 0, 1]])
        out[int(r["view_id"])] = {"K": k, "R": rot, "t": t, "center": -rot.T @ t, "w": int(r["w"]), "h": int(r["h"])}
    return out


def robust_trajectory_scale(src: np.ndarray, dst: np.ndarray, rounds: int = 4) -> Tuple[float, int, float]:
    """Scale Umeyama dst ≈ s·R·src + t, bỏ dần camera lệch (> max(0,25 m, 3 × trung vị)). Trả về (s, số camera giữ, residual trung vị m)."""
    if len(src) < MIN_CAMERAS:
        raise ValueError(f"cần ≥ {MIN_CAMERAS} camera chung giữa COLMAP và AR, có {len(src)}")
    keep = np.ones(len(src), bool)
    for _ in range(rounds):
        s, r, t = umeyama_sim3(src[keep], dst[keep])[:3]
        res = np.linalg.norm(s * (src @ r.T) + t - dst, axis=1)
        keep = res < max(0.25, 3 * float(np.median(res[keep])))
        if keep.sum() < MIN_CAMERAS:
            raise ValueError("quá ít camera còn lại sau khi bỏ camera lệch")
    s, r, t = umeyama_sim3(src[keep], dst[keep])[:3]
    res = np.linalg.norm(s * (src @ r.T) + t - dst, axis=1)
    return float(s), int(keep.sum()), float(np.median(res[keep]))


def project_anchor(ar_cams: Dict[int, Dict], registered: set, a: List[float], b: List[float], margin: int = 2) -> List[Dict]:
    """Chiếu A, B (hệ AR) vào các keyframe đã đăng ký; bỏ điểm sau camera hoặc ngoài ảnh. Trả về quan sát {view, endpoint, uv}."""
    obs = []
    for v, c in sorted(ar_cams.items()):
        if v not in registered:
            continue
        for key, p in (("a", a), ("b", b)):
            xc = c["R"] @ np.asarray(p, dtype=np.float64) + c["t"]
            if xc[2] <= 0.05:
                continue
            uvw = c["K"] @ xc
            u, w = uvw[0] / uvw[2], uvw[1] / uvw[2]
            if margin <= u < c["w"] - margin and margin <= w < c["h"] - margin:
                obs.append({"view": v, "endpoint": key, "uv": [float(u), float(w)]})
    return obs
