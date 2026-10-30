"""Đo khoảng cách hai điểm trên mô hình đã ở mét: ‖B − A‖₂  (30), ĐC §19.1, và so với thước dây (ĐC §8.3).

Thay cho thao tác chạm hai điểm trong Unity (mốc đầu chưa làm Unity). Mô hình đã ở mét nên không đổi
đơn vị gì thêm.

Phần thư viện (không cần GUI) của `scripts/pick_endpoints.py`:
  - `evaluation/logs/endpoints_<variant>.json`: đầu mút chọn tay trên point cloud mô hình (luồng eval đọc file này);
  - `ground_truth/tape_measurements.json`: GT thước dây, mỗi đoạn đo `measure.tape_readings` lần lấy trung vị;
  - `compare`: sai số từng đoạn và MAE/median/MAPE/%<ngưỡng, mốc scale (`used_as_anchor=1`) bị loại.

Cách chạy:
    python -m pipeline.export.measure --a 0.52 0.75 1.20 --b 1.90 0.75 1.20
    python -m pipeline.export.measure --glb model.glb --a ... --b ...   # kiểm tra thêm file GLB mở được
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from ..common.geometry import euclid
from ..eval import metrics

ENDPOINTS_VERSION = 1
MODEL_FRAME = "model: mét, +Y lên, sàn y=0"    # hệ của model.glb / model_points.ply (đã xoay, sàn y=0)
CLOUD_FRAME = "variant_cloud"                  # đúng hệ file point cloud của biến thể (B0, B1, B3, proposed, abl_quality); `eval` đọc cả hai
MODEL_FILES = ("model_points.ply", "model.glb")


def frame_of_points_file(points_file) -> str:
    """Hệ toạ độ của file điểm đã chọn: `model_points.ply` / `model.glb` ở hệ model, file khác (cloud của biến thể) ở hệ `CLOUD_FRAME`."""
    return MODEL_FRAME if Path(points_file).name in MODEL_FILES else CLOUD_FRAME
CSV_COLUMNS = ["id", "type", "ground_truth_m", "used_as_anchor", "endpoints/notes"]   # ĐC §9


class MeasureError(ValueError):
    """Dữ liệu đầu mút / thước dây không hợp lệ."""


def distance(a, b) -> float:
    """‖B − A‖₂ (m)  (30)."""
    return euclid(a, b)


# ---------------------------------------------------------------------------
# JSON dùng chung
# ---------------------------------------------------------------------------


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def write_json_atomic(path: Path, obj: Dict) -> None:
    """Ghi file tạm rồi thay, để đóng ngang không làm hỏng file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def read_json_if_exists(path: Path) -> Optional[Dict]:
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _xyz(p, name: str) -> List[float]:
    v = [float(x) for x in p]
    if len(v) != 3 or not all(np.isfinite(v)):
        raise MeasureError(f"{name} phải là [x, y, z] hữu hạn, nhận {p!r}")
    return v


# ---------------------------------------------------------------------------
# Đầu mút chọn trên mô hình
# ---------------------------------------------------------------------------


def endpoints_path(scene_root, variant: str) -> Path:
    return Path(scene_root) / "evaluation" / "logs" / f"endpoints_{variant}.json"


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def new_endpoints(scene: str, variant: str, points_file: str, points_sha256: str, frame: str = MODEL_FRAME) -> Dict:
    """`points_file`: đường dẫn tương đối so với thư mục scene (hoặc tuyệt đối nếu nằm ngoài)."""
    return {"version": ENDPOINTS_VERSION, "scene": scene, "variant": variant, "frame": frame, "points_file": points_file,
            "points_sha256": points_sha256, "created": _now(), "updated": _now(), "segments": []}


def load_endpoints(path) -> Optional[Dict]:
    doc = read_json_if_exists(Path(path))
    if doc is not None and doc.get("version") != ENDPOINTS_VERSION:
        raise MeasureError(f"{path}: version {doc.get('version')!r}, mong {ENDPOINTS_VERSION}")
    return doc


def save_endpoints(path, doc: Dict) -> None:
    doc["updated"] = _now()
    write_json_atomic(Path(path), doc)


def check_points_hash(doc: Dict, points_sha256: str) -> None:
    """Toạ độ đã chọn chỉ đúng với đúng file điểm đã dùng; dựng lại mô hình thì phải chọn lại."""
    if doc.get("points_sha256") != points_sha256:
        raise MeasureError(f"file điểm {doc.get('points_file')} đã đổi sau khi chọn (hash khác): toạ độ cũ có thể sai, chọn lại hoặc xoá "
                           f"endpoints_{doc.get('variant')}.json")


def add_segment(doc: Dict, seg_id: str, a, b, note: str = "", a_index: Optional[int] = None, b_index: Optional[int] = None,
                replace: bool = False) -> Dict:
    """Thêm đoạn {id, a, b, length_m, ...}. `seg_id` phải là id của đoạn tương ứng trong measurements.csv."""
    a, b = _xyz(a, "a"), _xyz(b, "b")
    length = distance(a, b)
    if length <= 1e-9:
        raise MeasureError(f"{seg_id}: hai đầu mút trùng nhau")
    segs = doc["segments"]
    old = next((s for s in segs if s["id"] == seg_id), None)
    if old is not None and not replace:
        raise MeasureError(f"id {seg_id} đã có")
    seg = {"id": seg_id, "a": a, "b": b, "length_m": round(length, 4), "variant": doc["variant"], "source": "manual",
           "a_index": a_index, "b_index": b_index, "note": note}
    if old is not None:
        segs[segs.index(old)] = seg
    else:
        segs.append(seg)
    return seg


# ---------------------------------------------------------------------------
# GT thước dây
# ---------------------------------------------------------------------------


def tape_median(readings: Sequence[float], n_required: int) -> float:
    r = [float(x) for x in readings]
    if len(r) != n_required:
        raise MeasureError(f"cần đúng {n_required} lần đo (ĐC §8.3), nhận {len(r)}")
    if not all(np.isfinite(r)) or min(r) <= 0:
        raise MeasureError(f"số đo phải > 0 (mét), nhận {r}")
    return float(np.median(r))


def new_tape(scene: str) -> Dict:
    return {"version": 1, "scene": scene, "unit": "m", "created": _now(), "updated": _now(), "segments": []}


def add_tape(doc: Dict, seg_id: str, readings: Sequence[float], n_required: int, anchor_range: Sequence[float], anchor: bool = False,
             seg_type: str = "other", notes: str = "") -> Dict:
    """Thêm/ghi đè đoạn thước dây. Mốc scale (`anchor`) phải dài trong `anchor_range` (ĐC §8.1) và chỉ được có một."""
    med = tape_median(readings, n_required)
    if anchor:
        lo, hi = anchor_range
        if not lo <= med <= hi:
            raise MeasureError(f"{seg_id}: mốc dài {med:.3f} m, ngoài {lo}–{hi} m [ĐC §8.1]")
        other = [s["id"] for s in doc["segments"] if s["used_as_anchor"] and s["id"] != seg_id]
        if other:
            raise MeasureError(f"đã có mốc {other[0]}; chỉ được một mốc scale")
    seg = {"id": seg_id, "type": seg_type, "readings_m": [float(x) for x in readings], "median_m": round(med, 4),
           "used_as_anchor": 1 if anchor else 0, "notes": notes}
    segs = doc["segments"]
    i = next((k for k, s in enumerate(segs) if s["id"] == seg_id), None)
    if i is None:
        segs.append(seg)
    else:
        segs[i] = seg
    doc["updated"] = _now()
    return seg


def tape_to_rows(doc: Dict) -> List[Dict]:
    """Hàng của `measurements.csv` [ĐC §9] từ GT thước dây."""
    return [{"id": s["id"], "type": s["type"], "ground_truth_m": f"{s['median_m']:.4f}", "used_as_anchor": s["used_as_anchor"],
             "endpoints/notes": "; ".join(["tape " + "/".join(f"{x:g}" for x in s["readings_m"])] + ([s["notes"]] if s["notes"] else []))}
            for s in doc["segments"]]


def write_csv(path, rows: List[Dict], overwrite: bool = False) -> None:
    path = Path(path)
    if path.exists() and not overwrite:
        raise MeasureError(f"{path.name} đã có; dùng --overwrite nếu muốn ghi đè")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# So sánh với GT
# ---------------------------------------------------------------------------


def gt_from_tape(doc: Dict) -> Dict[str, Dict]:
    return {s["id"]: {"gt_m": float(s["median_m"]), "anchor": bool(s["used_as_anchor"])} for s in doc["segments"]}


def gt_from_csv(path) -> Dict[str, Dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return {r["id"]: {"gt_m": float(r["ground_truth_m"]), "anchor": str(r["used_as_anchor"]).strip() == "1"} for r in csv.DictReader(f)}


def compare(endpoints: Dict, gt: Dict[str, Dict], under_cm: float) -> Dict:
    """Sai số từng đoạn (ghép theo id) và chỉ số tổng hợp. Đoạn mốc (`anchor`) bị loại khỏi chỉ số [ĐC §8.1].

    Trả về {"rows": [{id, gt_m, model_m, err_cm}], "metrics": {n, mae_cm, median_cm, mape_percent, under_pct}, "excluded_anchor": [...],
    "missing_gt": [...], "missing_model": [...]}. Chỉ số theo (32)(33) trong `pipeline.eval.metrics`.
    """
    model = {s["id"]: float(s["length_m"]) for s in endpoints["segments"]}
    anchors = [i for i in model if gt.get(i, {}).get("anchor")]
    rows = [{"id": i, "gt_m": gt[i]["gt_m"], "model_m": m, "err_cm": (m - gt[i]["gt_m"]) * 100.0}
            for i, m in model.items() if i in gt and i not in anchors]
    if not rows:
        raise MeasureError("không có đoạn test nào ghép được (id khớp GT, không phải mốc)")
    pred = [r["model_m"] for r in rows]
    true = [r["gt_m"] for r in rows]
    return {"rows": rows,
            "metrics": {"n": len(rows), "mae_cm": metrics.mae_cm(pred, true), "median_cm": metrics.median_cm(pred, true),
                        "mape_percent": metrics.mape_percent(pred, true), "under_pct": metrics.percent_under_cm(pred, true, under_cm),
                        "under_cm": under_cm},
            "excluded_anchor": anchors, "missing_gt": [i for i in model if i not in gt],
            "missing_model": [i for i, g in gt.items() if i not in model and not g["anchor"]]}


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Đo khoảng cách hai điểm trên mô hình (mét)")
    ap.add_argument("--a", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"))
    ap.add_argument("--b", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"))
    ap.add_argument("--glb", help="tuỳ chọn: file GLB để kiểm tra mở được và in kích thước hộp bao")
    args = ap.parse_args(argv)

    if args.glb:
        import trimesh

        scene = trimesh.load(args.glb)
        ext = scene.extents if hasattr(scene, "extents") else None
        print(f"GLB: {args.glb}, kích thước hộp bao (m): {None if ext is None else [round(float(v), 3) for v in ext]}")
    print(f"‖B − A‖ = {distance(args.a, args.b):.3f} m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
