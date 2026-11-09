"""Đo chiều dài trên point cloud của một biến thể (ĐC §8.3, §20.1; kế hoạch §4.8).

Hai chế độ cùng đo `‖B̂ − Â‖` theo (30) trên cùng cặp điểm vật lý:
  * `manual`: đầu mút do người chọn trực tiếp trên point cloud của biến thể (`evaluation/logs/endpoints_<variant>.json`);
  * `auto`: đầu mút GT (hệ scene/ARKit, mét) đưa vào hệ biến thể bằng phép CỨNG scale = 1 (Kabsch trên tâm camera), rồi snap vào
    điểm gần nhất trong bán kính `eval.snap_radius_m`. GT chỉ định vị, không cho scale. Đầu mút không snap được thì đoạn không hợp lệ.
Mốc scale (`used_as_anchor = 1`) bị loại khỏi chỉ số test (ĐC §8.1).
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.spatial import cKDTree

from ..export.measure import CLOUD_FRAME, MODEL_FRAME, distance
from .metrics import mae_cm, mape_percent, median_cm, percent_under_cm

_ENDPOINTS = re.compile(r"A=\(([^)]*)\)\s*B=\(([^)]*)\)")


def _xyz(text: str) -> np.ndarray:
    v = np.array([float(s) for s in text.split(",")], dtype=np.float64)
    if v.shape != (3,):
        raise ValueError(f"cần 3 số, nhận {text!r}")
    return v


def read_measurements(path) -> List[Dict]:
    """`ground_truth/measurements.csv` → [{id, type, gt_m, anchor, a, b}]; a, b là đầu mút GT (hệ scene, mét) lấy từ cột `endpoints/notes`."""
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m = _ENDPOINTS.search(row["endpoints/notes"])
            if not m:
                raise ValueError(f"{path}: đoạn {row['id']} không có 'A=(x, y, z) B=(x, y, z)' trong cột endpoints/notes")
            out.append({"id": row["id"], "type": row["type"], "gt_m": float(row["ground_truth_m"]), "anchor": int(row["used_as_anchor"]) == 1,
                        "a": _xyz(m.group(1)), "b": _xyz(m.group(2))})
    return out


def test_segments(segments: Sequence[Dict]) -> List[Dict]:
    """Chỉ các đoạn test: bỏ đoạn mốc scale."""
    return [s for s in segments if not s["anchor"]]


def kabsch_rigid(src: np.ndarray, dst: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
    """Phép cứng (scale = 1) dst ≈ R·src + t, trả về (R, t, rms). Cần ≥ 3 cặp không thẳng hàng."""
    x, y = np.asarray(src, dtype=np.float64), np.asarray(dst, dtype=np.float64)
    if x.shape != y.shape or x.ndim != 2 or x.shape[1] != 3 or len(x) < 3:
        raise ValueError(f"cần ≥ 3 cặp điểm (n, 3) cùng shape; nhận {x.shape} và {y.shape}")
    mx, my = x.mean(axis=0), y.mean(axis=0)
    u, _, vt = np.linalg.svd((y - my).T @ (x - mx))
    r = u @ np.diag([1.0, 1.0, np.sign(np.linalg.det(u @ vt))]) @ vt
    t = my - r @ mx
    return r, t, float(np.sqrt(np.mean(np.sum((x @ r.T + t - y) ** 2, axis=1))))


def kabsch_rigid_trimmed(src: np.ndarray, dst: np.ndarray, k: float, max_iters: int = 5) -> Tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    """Kabsch cắt tỉa lặp: căn trên mọi cặp, bỏ cặp có residual > `k` × trung vị residual của các cặp đang giữ, căn lại trên phần còn lại;
    lặp tới khi tập giữ lại không đổi hoặc hết `max_iters` lượt. Residual tính trên MỌI cặp mỗi lượt (cặp bị loại có thể quay lại).
    Trả về (R, t, rms trên cặp giữ lại, mask giữ lại). Lượt nào làm còn < 3 cặp thì dừng, giữ phép căn của lượt trước.
    Một lượt chưa đủ khi nhiều camera lệch quá xa (42445022: pose ARKit ~7 camera lệch tới 6,9 m làm trung vị lượt đầu vẫn bị nhiễm)."""
    x, y = np.asarray(src, dtype=np.float64), np.asarray(dst, dtype=np.float64)
    keep = np.ones(len(x), dtype=bool)
    r, t, rms = kabsch_rigid(x, y)
    for _ in range(max_iters):
        res = np.linalg.norm(x @ r.T + t - y, axis=1)
        new = res <= k * np.median(res[keep]) + 1e-12
        if (new == keep).all() or new.sum() < 3:
            break
        keep = new
        r, t, rms = kabsch_rigid(x[keep], y[keep])
    return r, t, rms, keep


def _row(seg: Dict, a: Optional[np.ndarray], b: Optional[np.ndarray], mode: str, extra: Optional[Dict] = None) -> Dict:
    ok = a is not None and b is not None
    pred = distance(a, b) if ok else None
    row = {"id": seg["id"], "type": seg["type"], "gt_m": seg["gt_m"], "pred_m": pred, "err_m": abs(pred - seg["gt_m"]) if ok else None, "valid": ok, "mode": mode}
    row.update(extra or {})
    return row


def measure_auto(segments: Sequence[Dict], r_gt_to_model: np.ndarray, t_gt_to_model: np.ndarray, cloud: np.ndarray, radius_m: float,
                 mode: str = "auto") -> List[Dict]:
    """Đầu mút GT → hệ biến thể (`R·p + t`) → snap điểm gần nhất trong `radius_m`. Ghi cả khoảng cách điểm gần nhất khi không snap được."""
    tree = cKDTree(np.asarray(cloud, dtype=np.float64))
    rows = []
    for seg in segments:
        snapped, nn = [], []
        for key in ("a", "b"):
            q = r_gt_to_model @ seg[key] + t_gt_to_model
            d, i = tree.query(q)
            nn.append(float(d))
            snapped.append(np.asarray(tree.data[i]) if d <= radius_m else None)
        rows.append(_row(seg, snapped[0], snapped[1], mode, {"nn_a_m": nn[0], "nn_b_m": nn[1], "snapped_a": snapped[0] is not None, "snapped_b": snapped[1] is not None}))
    return rows


def model_to_colmap_metric(frame: Dict):
    """`proposed/export/measurements.json["frame"]` (`x_model = R·x_cm + t`) → hàm đưa điểm hệ `model.glb` về hệ COLMAP × `s_m`: `x_cm = Rᵀ(x_model − t)`."""
    r, t = np.asarray(frame["rotation_from_colmap_metric"], dtype=np.float64), np.asarray(frame["translation"], dtype=np.float64)
    return lambda p: r.T @ (np.asarray(p, dtype=np.float64) - t)


def read_endpoints_json(path, scene: Optional[str] = None, model_frame: Optional[Dict] = None) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """`endpoints_<variant>.json` → {id: (a, b)} (mét).

    Nhận hai dạng: `endpoints` (dict `{id: {a, b}}`, dạng ban đầu của `eval`) và `segments` (list `{id, a, b, ...}`, dạng do `scripts/pick_endpoints.py` ghi).
    `frame`: `variant_cloud` = toạ độ trong đúng file point cloud của biến thể, giữ nguyên; `MODEL_FRAME` (chọn trên `model.glb` / `model_points.ply`) được đổi về hệ
    COLMAP × `s_m` bằng `model_frame` (= `proposed/export/measurements.json["frame"]`), nên chỉ đúng cho biến thể dùng hệ đó (B0, B3, proposed, abl_quality), không cho B1."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    frame = d.get("frame", CLOUD_FRAME)
    if d.get("unit", "m") != "m":
        raise ValueError(f"{path}: chỉ nhận unit=m")
    if scene is not None and d.get("scene") not in (None, scene):
        raise ValueError(f"{path}: scene {d.get('scene')!r} khác {scene!r}")
    if "endpoints" in d:
        pairs = {k: (v["a"], v["b"]) for k, v in d["endpoints"].items()}
    elif "segments" in d:
        pairs = {s["id"]: (s["a"], s["b"]) for s in d["segments"]}
    else:
        raise ValueError(f"{path}: không có 'endpoints' hay 'segments'")
    if frame == CLOUD_FRAME:
        conv = np.asarray
    elif frame == MODEL_FRAME:
        if model_frame is None:
            raise ValueError(f"{path}: toạ độ ở hệ model.glb; không đổi được sang hệ point cloud của biến thể này (cần proposed/export/measurements.json "
                             f"và biến thể dùng hệ COLMAP mét; B1 thì chọn trực tiếp trên points_metric.ply với frame={CLOUD_FRAME})")
        conv = model_to_colmap_metric(model_frame)
    else:
        raise ValueError(f"{path}: frame {frame!r} không nhận (chỉ {CLOUD_FRAME!r} hoặc {MODEL_FRAME!r})")
    return {k: (np.asarray(conv(a), dtype=np.float64), np.asarray(conv(b), dtype=np.float64)) for k, (a, b) in pairs.items()}


def measure_manual(segments: Sequence[Dict], endpoints: Dict[str, Tuple[np.ndarray, np.ndarray]]) -> List[Dict]:
    """Đoạn thiếu trong file endpoints = chưa chấm (không hợp lệ)."""
    return [_row(seg, *(endpoints.get(seg["id"]) or (None, None)), "manual") for seg in segments]


def measure_transfer(segments: Sequence[Dict], endpoints: Dict[str, Tuple[np.ndarray, np.ndarray]], r_src_to_model: np.ndarray, t_src_to_model: np.ndarray,
                     cloud: np.ndarray, radius_m: float) -> List[Dict]:
    """Truyền cặp điểm đã chấm trên một biến thể (hệ nguồn) sang biến thể khác (PLAN §4.8 mục 3): `R·p + t` rồi snap trong `radius_m`, nhãn `manual_transfer`.
    Đoạn chưa chấm ở nguồn thì không hợp lệ."""
    present = [dict(seg, a=endpoints[seg["id"]][0], b=endpoints[seg["id"]][1]) for seg in segments if seg["id"] in endpoints]
    done = {r["id"]: r for r in measure_auto(present, r_src_to_model, t_src_to_model, cloud, radius_m, "manual_transfer")}
    return [done.get(seg["id"]) or _row(seg, None, None, "manual_transfer") for seg in segments]


def length_metrics(rows: Sequence[Dict], ids: Optional[Sequence[str]] = None) -> Dict:
    """MAE, median, MAPE, %<5 cm (32)(33) trên các đoạn hợp lệ (hoặc chỉ các `ids`). Không có đoạn nào thì các giá trị là None."""
    sel = [r for r in rows if r["valid"] and (ids is None or r["id"] in ids)]
    out = {"n_valid": len(sel), "mae_cm": None, "median_cm": None, "mape_pct": None, "pct_lt5cm": None}
    if sel:
        p, g = [r["pred_m"] for r in sel], [r["gt_m"] for r in sel]
        out.update(mae_cm=mae_cm(p, g), median_cm=median_cm(p, g), mape_pct=mape_percent(p, g), pct_lt5cm=percent_under_cm(p, g, 5.0))
    return out


def snap_summary(rows: Sequence[Dict]) -> Dict:
    """Chỉ cho chế độ auto: số đầu mút không snap, khoảng snap (khoảng tới điểm gần nhất khi đã snap), khoảng tới điểm gần nhất của mọi đầu mút."""
    nn = np.array([r[k] for r in rows for k in ("nn_a_m", "nn_b_m")])
    sn = np.array([r[k] for r in rows for k in ("snapped_a", "snapped_b")])
    return {"n_endpoints": int(len(nn)), "n_unsnapped": int((~sn).sum()),
            "snap_mean_cm": float(nn[sn].mean() * 100) if sn.any() else None,
            "nn_median_cm": float(np.median(nn) * 100), "nn_max_cm": float(nn.max() * 100)}


def write_lengths_csv(path, rows: Sequence[Dict]) -> None:
    keys = ["id", "type", "gt_m", "pred_m", "err_m", "valid", "mode", "nn_a_m", "nn_b_m", "snapped_a", "snapped_b"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r[k]) for k in keys})
