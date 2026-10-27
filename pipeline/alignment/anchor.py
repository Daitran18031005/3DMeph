"""Mốc scale từ click 2D (ĐC §15.2, công thức (4); kế hoạch M1c).

Người dùng click hai đầu mút của mốc (ví dụ cao cánh cửa); mỗi đầu mút được tam giác hoá (DLT) ĐỘC LẬP bằng camera COLMAP từ ≥ 2 keyframe
khác nhau (hai đầu mút không cần xuất hiện trong cùng một ảnh).
`L_model = ‖B − A‖` (đv COLMAP); `s_m = L_real / L_model` ((4), `ransac.metric_scale`). Không dùng pose GT của ARKit nên không rò rỉ scale.
"""

from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np

from ..common.geometry import project


def projection_matrix(k: np.ndarray, r: np.ndarray, t: np.ndarray) -> np.ndarray:
    return np.asarray(k, dtype=np.float64) @ np.hstack([np.asarray(r, dtype=np.float64), np.asarray(t, dtype=np.float64).reshape(3, 1)])


def triangulate_dlt(ps: Sequence[np.ndarray], uvs: Sequence[Sequence[float]]) -> np.ndarray:
    """Điểm 3D từ ≥ 2 quan sát (P_j 3×4, (u, v) px) bằng DLT."""
    if len(ps) < 2 or len(ps) != len(uvs):
        raise ValueError("cần ít nhất 2 quan sát, số P và số (u, v) phải bằng nhau")
    rows = []
    for p, (u, v) in zip(ps, uvs):
        rows.append(u * p[2] - p[0])
        rows.append(v * p[2] - p[1])
    _, _, vt = np.linalg.svd(np.asarray(rows, dtype=np.float64))
    x = vt[-1]
    if abs(x[3]) < 1e-12:
        raise ValueError("tam giác hoá suy biến (điểm ở vô cực)")
    return x[:3] / x[3]


def max_ray_angle_deg(centers: np.ndarray, point: np.ndarray) -> float:
    """Góc lớn nhất giữa hai tia từ các camera tới điểm; nhỏ (< vài độ) thì độ sâu tam giác hoá rất nhiễu."""
    d = np.asarray(point, dtype=np.float64) - np.asarray(centers, dtype=np.float64)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    c = np.clip(d @ d.T, -1.0, 1.0)
    return float(np.degrees(np.arccos(c.min())))


def normalize_obs(obs: List[Dict]) -> List[Dict]:
    """Quan sát theo từng đầu mút: [{view, endpoint: "a"|"b", uv: [u, v]}]. Nhận thêm dạng cũ {view, a, b} (cả hai đầu mút trong một ảnh).
    Mỗi cặp (view, endpoint) tối đa một lần."""
    out, seen = [], set()
    for o in obs:
        v = int(o["view"])
        items = [(o["endpoint"], o["uv"])] if "endpoint" in o else [(k, o[k]) for k in ("a", "b") if k in o]
        if not items:
            raise ValueError(f"quan sát view {v} không có endpoint/uv hoặc a/b")
        for k, uv in items:
            if k not in ("a", "b"):
                raise ValueError(f"endpoint phải là 'a' hoặc 'b', nhận {k!r}")
            if (v, k) in seen:
                raise ValueError(f"view {v} đầu mút {k} xuất hiện hai lần")
            seen.add((v, k))
            out.append({"view": v, "endpoint": k, "uv": [float(uv[0]), float(uv[1])]})
    return out


def anchor_from_clicks(cams: Dict[int, Dict], obs: List[Dict]) -> Dict:
    """cams: view_id → {K, R, t, center}; obs: quan sát theo từng đầu mút (xem `normalize_obs`).

    Mỗi đầu mút được tam giác hoá ĐỘC LẬP từ ≥ 2 keyframe khác nhau (không cần thấy cả hai đầu mút trong cùng một ảnh).
    Trả về A, B (đv COLMAP), L_model, sai số chiếu lại từng quan sát (px), số view và góc tia lớn nhất của mỗi đầu mút.
    """
    obs = normalize_obs(obs)
    out: Dict = {}
    for key in ("a", "b"):
        sel = [o for o in obs if o["endpoint"] == key]
        views = [o["view"] for o in sel]
        if len(set(views)) < 2:
            raise ValueError(f"đầu mút {key.upper()} cần click ở ít nhất 2 keyframe khác nhau (có {len(set(views))})")
        missing = [v for v in views if v not in cams]
        if missing:
            raise ValueError(f"keyframe {missing} không có trong model COLMAP (chưa đăng ký)")
        ps = [projection_matrix(cams[v]["K"], cams[v]["R"], cams[v]["t"]) for v in views]
        centers = np.array([cams[v]["center"] for v in views])
        x = triangulate_dlt(ps, [o["uv"] for o in sel])
        err = [float(np.linalg.norm(project(cams[v]["K"], cams[v]["R"], cams[v]["t"], x[None, :])[0] - np.asarray(o["uv"]))) for v, o in zip(views, sel)]
        out[key] = {"xyz": x.tolist(), "views": views, "reproj_px": err, "max_ray_angle_deg": max_ray_angle_deg(centers, x)}
    a, b = np.asarray(out["a"]["xyz"]), np.asarray(out["b"]["xyz"])
    out["L_model"] = float(np.linalg.norm(b - a))
    return out
