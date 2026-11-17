#!/usr/bin/env python3
"""
arkit_to_capture.py — đóng gói một scene ARKitScenes đã chạy stage keyframe thành gói quay của app (capture.json + frames/*.jpg, zip) để kiểm
backend M6 mà không cần điện thoại. CHỈ KIỂM CHỨC NĂNG: dùng pose ARKit (vai trò của ARCore trong app); không phải kết quả đánh giá.

Ảnh lấy từ `frames/candidates/` (đã xoay đứng, KHÔNG đụng dữ liệu raw); pose world→camera từ `lowres_wide.traj` tại `frame_ts`, xoay cùng ảnh.
`--tape S06` thêm mốc thước dây: đầu mút A, B (hệ scene ARKit) và L_real lấy từ `ground_truth/measurements.csv`.

    python scripts/arkit_to_capture.py --scene 42444738 --mode ar --out capture_ar.zip
    python scripts/arkit_to_capture.py --scene 42444738 --mode tape --tape S06 --out capture_tape.zip
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

from pipeline.common.adapters import Trajectory  # noqa: E402
from pipeline.common.io import read_json  # noqa: E402

# camera mới = R_ROT · camera cũ khi ảnh đã xoay (khớp `rotate_intrinsics`): cw90 u'=h−v, v'=u ⇒ x'=−y, y'=x
R_ROT = {"none": np.eye(3), "cw90": np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1.0]]),
         "ccw90": np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1.0]]), "rot180": np.diag([-1.0, -1.0, 1.0])}


def tape_anchor(scene_dir: Path, seg_id: str) -> dict:
    for r in csv.DictReader(open(scene_dir / "ground_truth" / "measurements.csv", encoding="utf-8")):
        if r["id"] == seg_id:
            a, b = (list(map(float, m)) for m in re.findall(r"[AB]=\(([-\d.]+), ([-\d.]+), ([-\d.]+)\)", r["endpoints/notes"]))
            return {"id": seg_id, "L_real": float(r["ground_truth_m"]), "A": a, "B": b}
    raise SystemExit(f"không thấy đoạn {seg_id}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--mode", choices=["ar", "tape"], required=True)
    ap.add_argument("--tape", help="id đoạn làm mốc (chế độ tape)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    sd = REPO / "data" / "scenes" / "arkitscenes" / a.scene
    traj = Trajectory.from_file(Path(read_json(sd / "raw" / "source.json")["raw_dir"]) / "lowres_wide.traj")
    frames, buf = [], io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for r in csv.DictReader(open(sd / "metadata" / "candidates.csv", encoding="utf-8")):
            try:
                r_cw, t_cw = traj.pose_cw(float(r["frame_ts"]), True, 0.2)
            except ValueError:
                continue
            rot = R_ROT[r["rot_applied"]]
            m = np.eye(4)
            m[:3, :3], m[:3, 3] = rot @ r_cw, rot @ t_cw
            name = f"{int(r['view_id']):06d}.jpg"
            z.write(sd / "frames" / "candidates" / f"{int(r['view_id']):04d}.jpg", f"frames/{name}")
            frames.append({"name": name, "t": float(r["frame_ts"]), "w": int(r["w"]), "h": int(r["h"]),
                           "fx": float(r["fx"]), "fy": float(r["fy"]), "cx": float(r["cx"]), "cy": float(r["cy"]), "T_cam_world": m.tolist()})
        doc = {"device": f"ARKitScenes {a.scene} (kiểm chức năng)", "scale_mode": a.mode, "frames": frames}
        if a.mode == "tape":
            doc["anchor"] = tape_anchor(sd, a.tape)
        z.writestr("capture.json", json.dumps(doc, indent=1))
    Path(a.out).write_bytes(buf.getvalue())
    print(f"{len(frames)} khung, scale_mode {a.mode} → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
