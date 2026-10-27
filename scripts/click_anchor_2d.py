#!/usr/bin/env python3
"""
click_anchor_2d.py — click hai đầu mút của mốc scale, tam giác hoá từng đầu mút bằng camera COLMAP (kế hoạch M1c, ĐC §15.2, (4)).

Mỗi đầu mút (A, B) được click ở ≥ 2 keyframe khác nhau và tam giác hoá ĐỘC LẬP; hai đầu mút KHÔNG cần xuất hiện trong cùng một ảnh
(với mốc cao cánh cửa S05 của 42444738 không keyframe nào thấy cả hai). Mốc (id, nhãn, `L_real`) lấy từ `ground_truth/scale_anchor.json`.
Ảnh hiển thị là keyframe thường: không vẽ gợi ý nào từ pose GT hay Faro. Kết quả `L_model` (đv COLMAP), toạ độ 3D hai đầu mút, quan sát pixel,
sai số chiếu lại và góc tia ghi vào chính `scale_anchor.json`. Script chỉ in số, không có ngưỡng chấp nhận; người dùng đọc số rồi quyết định.

Cách chạy (từ thư mục gốc repo, env 3d_metric; cần stage sfm đã chạy):
    python scripts/click_anchor_2d.py --scene arkitscenes/42444738            # mở cửa sổ OpenCV (duyệt mọi ảnh đã đăng ký)
    python scripts/click_anchor_2d.py --scene arkitscenes/42444738 --views 12 13 14 15 16 17   # chỉ duyệt các ảnh này
    python scripts/click_anchor_2d.py --scene arkitscenes/42444738 --check    # in kết quả đã lưu, không GUI
    python scripts/click_anchor_2d.py --scene arkitscenes/42444738 --from-json obs.json   # nạp quan sát, không GUI

Phím trong cửa sổ: 1 chọn đầu mút A, 2 chọn B (hoặc Tab đổi); chuột trái đặt (hoặc đặt lại) điểm của đầu mút đang chọn trong ảnh đang xem;
Enter/Space lưu các điểm đã click của ảnh này; Backspace huỷ điểm chưa lưu của đầu mút đang chọn; x xoá điểm đã lưu của đầu mút đang chọn ở ảnh này;
a/d (hoặc ←/→) ảnh trước/sau; + / - đổi tỉ lệ ảnh (mặc định tự vừa màn hình); s tam giác hoá và ghi file (mỗi đầu mút cần ≥ 2 ảnh đã lưu); q/Esc thoát không ghi.

Mã thoát: 0 ok; 1 lỗi đầu vào; 2 người dùng thoát không ghi.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pipeline  # noqa: E402,F401  (import torch trước cv2/open3d/pycolmap)

# isort: split
import numpy as np  # noqa: E402

from pipeline import run as pr  # noqa: E402
from pipeline.alignment.anchor import anchor_from_clicks, normalize_obs  # noqa: E402
from pipeline.alignment.stage import load_colmap_cameras  # noqa: E402
from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402
from pipeline.common.io import read_json, write_json  # noqa: E402


def validate_obs(obs: List[Dict]) -> List[Dict]:
    """Chuẩn hoá quan sát (mỗi cặp view, đầu mút tối đa một lần); nhận cả dạng cũ {view, a, b}."""
    return normalize_obs(obs)


def summarize(res: Dict) -> str:
    parts = []
    for k in ("a", "b"):
        e = res[k]["reproj_px"]
        parts.append(f"{k.upper()}: {len(res[k]['views'])} ảnh {res[k]['views']}, chiếu lại trung bình {np.mean(e):.2f} px / lớn nhất {np.max(e):.2f} px, "
                     f"góc tia lớn nhất {res[k]['max_ray_angle_deg']:.1f}°")
    return f"L_model = {res['L_model']:.5f} đv COLMAP; " + "; ".join(parts)


def save_anchor(path: Path, obs: List[Dict], res: Dict, n_registered: int, overwrite: bool = False) -> Dict:
    """Ghi L_model và chi tiết vào scale_anchor.json (giữ nguyên các khoá cũ). Có sẵn L_model thì cần overwrite."""
    anchor = read_json(path)
    if "L_model" in anchor and not overwrite:
        raise FileExistsError(f"{path} đã có L_model = {anchor['L_model']}; thêm --overwrite để thay")
    anchor.update(L_model=res["L_model"], L_model_unit="đv COLMAP (chưa mét)", observations_2d=obs,
                  triangulated_endpoints_colmap={"a": res["a"]["xyz"], "b": res["b"]["xyz"]},
                  reproj_px={"a": res["a"]["reproj_px"], "b": res["b"]["reproj_px"]},
                  max_ray_angle_deg={"a": res["a"]["max_ray_angle_deg"], "b": res["b"]["max_ray_angle_deg"]},
                  views_per_endpoint={"a": res["a"]["views"], "b": res["b"]["views"]},
                  colmap_registered_images=n_registered, clicked_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    anchor["note"] = "L_real đo trên Faro; L_model do scripts/click_anchor_2d.py (click 2D + tam giác hoá bằng camera COLMAP)"
    write_json(path, anchor)
    return anchor


BAR_H = 26                      # dải trạng thái nằm TRÊN ảnh (không che điểm gần mép trên)
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 0.5, 2.5, 0.1


def screen_height() -> Optional[int]:
    """Chiều cao màn hình chính (px) trên Windows; nơi khác hoặc lỗi thì None."""
    try:
        import ctypes
        return int(ctypes.windll.user32.GetSystemMetrics(1))
    except (AttributeError, OSError, ImportError):
        return None


def fit_zoom(screen_h: Optional[int], img_h: int = 640, reserve: int = 170) -> float:
    """Tỉ lệ phóng để ảnh + thanh tiêu đề + thanh tác vụ + dải trạng thái vừa chiều cao màn hình; không rõ màn hình thì 1,0; trần 1,5."""
    if not screen_h:
        return 1.0
    return round(max(ZOOM_MIN, min(1.5, (screen_h - reserve) / img_h)), 2)


def run_gui(layout, cams, anchor: Dict, zoom: float, views: List[int]) -> Optional[List[Dict]]:
    import cv2
    saved: Dict[tuple, List[float]] = {}                       # (view, "a"|"b") → [u, v] đã lưu
    clicks: Dict[tuple, List[float]] = {}                      # (view, "a"|"b") → [u, v] chưa lưu
    state = {"i": 0, "ep": "a", "zoom": zoom}
    colors = {"a": (0, 0, 255), "b": (255, 128, 0)}
    win = f"Click mốc {anchor.get('id', '?')} ({anchor.get('label', '')})"

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and y >= BAR_H:
            z = state["zoom"]
            clicks[(views[state["i"]], state["ep"])] = [(x + 0.5) / z, (y - BAR_H + 0.5) / z]

    def n_saved(ep):
        return len({v for (v, e) in saved if e == ep})

    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)
    cv2.moveWindow(win, 20, 0)                                  # sát mép trên để thanh tiêu đề không đẩy ảnh xuống dưới
    cv2.setMouseCallback(win, on_mouse)
    while True:
        v = views[state["i"]]
        img = cv2.imread(str(layout.keyframes / f"{v:04d}.jpg"))
        if img is None:
            print(f"[LỖI] không đọc được keyframe {v:04d}.jpg")
            return None
        zoom = state["zoom"]
        img = cv2.resize(img, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_LINEAR)
        for ep in ("a", "b"):
            for pts, thick in ((saved.get((v, ep)), 1), (clicks.get((v, ep)), 2)):
                if pts is None:
                    continue
                p = (int(pts[0] * zoom), int(pts[1] * zoom))
                col = (0, 200, 0) if thick == 1 else colors[ep]
                cv2.drawMarker(img, p, col, cv2.MARKER_CROSS, 20, thick)
                cv2.putText(img, ep.upper(), (p[0] + 8, p[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 1)
        status = (f"anh {v:04d} ({state['i'] + 1}/{len(views)}) | dang chon {state['ep'].upper()} | luu A:{n_saved('a')} B:{n_saved('b')} (can >=2) | "
                  f"zoom {zoom:.1f} (+/-)")
        bar = np.zeros((BAR_H, img.shape[1], 3), dtype=np.uint8)
        cv2.putText(bar, status, (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)
        cv2.imshow(win, np.vstack([bar, img]))
        k = cv2.waitKeyEx(30)
        if k == -1:
            continue
        if k in (27, ord("q")):
            cv2.destroyAllWindows()
            return None
        if k in (ord("d"), 2555904):
            state["i"] = (state["i"] + 1) % len(views)
        elif k in (ord("a"), 2424832):
            state["i"] = (state["i"] - 1) % len(views)
        elif k in (ord("+"), ord("=")):
            state["zoom"] = round(min(ZOOM_MAX, state["zoom"] + ZOOM_STEP), 2)
        elif k in (ord("-"), ord("_")):
            state["zoom"] = round(max(ZOOM_MIN, state["zoom"] - ZOOM_STEP), 2)
        elif k == ord("1"):
            state["ep"] = "a"
        elif k == ord("2"):
            state["ep"] = "b"
        elif k == 9:
            state["ep"] = "b" if state["ep"] == "a" else "a"
        elif k in (13, 32):
            for ep in ("a", "b"):
                if (v, ep) in clicks:
                    saved[(v, ep)] = clicks.pop((v, ep))
                    print(f"[click] lưu ảnh {v:04d} đầu mút {ep.upper()}: {np.round(saved[(v, ep)], 1).tolist()}")
        elif k == 8:
            clicks.pop((v, state["ep"]), None)
        elif k == ord("x"):
            saved.pop((v, state["ep"]), None)
            clicks.pop((v, state["ep"]), None)
        elif k == ord("s"):
            if n_saved("a") < 2 or n_saved("b") < 2:
                print(f"[click] mỗi đầu mút cần ≥ 2 ảnh đã lưu (A: {n_saved('a')}, B: {n_saved('b')})")
                continue
            cv2.destroyAllWindows()
            return [{"view": vv, "endpoint": ep, "uv": uv} for (vv, ep), uv in sorted(saved.items())]


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Click mốc scale 2D và tam giác hoá bằng camera COLMAP")
    ap.add_argument("--scene", required=True, help="arkitscenes/<video_id>")
    ap.add_argument("--root", default=str(REPO))
    ap.add_argument("--zoom", type=float, default=None,
                    help="phóng ảnh hiển thị; mặc định tự vừa chiều cao màn hình (tối đa 1,5); trong cửa sổ: phím + / - đổi tỉ lệ")
    ap.add_argument("--views", type=int, nargs="+", metavar="ID", help="chỉ duyệt các keyframe này (phải đã đăng ký COLMAP); mặc định: mọi ảnh đã đăng ký")
    ap.add_argument("--check", action="store_true", help="in kết quả đã lưu, không GUI")
    ap.add_argument("--from-json", metavar="FILE", help="nạp danh sách quan sát [{view,a,b}] từ JSON (không GUI) rồi tam giác hoá")
    ap.add_argument("--overwrite", action="store_true", help="cho phép ghi đè L_model đã có")
    args = ap.parse_args(argv)

    root = Path(args.root)
    try:
        cfg = cfgmod.load_config(root / "configs" / "default.yaml")
        info = pr.resolve_scene(root, args.scene, cfg)
    except (sp.HeldoutError, sp.LockError, ValueError, FileNotFoundError) as e:
        print(f"[LỖI] {type(e).__name__}: {e}")
        return 1
    layout = info["layout"]
    path = layout.root / str(cfgmod.require(cfg, "align.anchor_file"))
    if not path.is_file():
        print(f"[LỖI] thiếu {path}: chạy annotate_segments.py --finalize trước")
        return 1
    anchor = read_json(path)
    if args.check:
        print(json.dumps({k: anchor.get(k) for k in ("id", "label", "L_real", "L_model", "observations_2d", "reproj_px", "max_ray_angle_deg")}, ensure_ascii=False, indent=1))
        return 0
    try:
        cams = load_colmap_cameras(layout)
    except Exception as e:  # noqa: BLE001 — báo lỗi đọc model rồi thoát mã 1
        print(f"[LỖI] {type(e).__name__}: {e}")
        return 1
    if "L_model" in anchor and not args.overwrite:
        print(f"[LỖI] {path.name} đã có L_model = {anchor['L_model']}; thêm --overwrite để click lại")
        return 1
    print(f"[click] mốc {anchor.get('id')} «{anchor.get('label')}», L_real {anchor.get('L_real')} m; {len(cams)} ảnh đã đăng ký COLMAP")
    if args.from_json:
        obs = validate_obs(read_json(args.from_json))
    else:
        views = sorted(set(args.views)) if args.views else sorted(cams)
        bad = [v for v in views if v not in cams]
        if bad:
            print(f"[LỖI] keyframe {bad} chưa đăng ký COLMAP; ảnh khả dụng: {sorted(cams)}")
            return 1
        zoom = args.zoom or fit_zoom(screen_height())
        print(f"[click] tỉ lệ hiển thị {zoom} (ảnh {int(480 * zoom)}×{int(640 * zoom)} px); phím + / - để đổi nếu ảnh vẫn bị khuất")
        obs = run_gui(layout, cams, anchor, zoom, views)
        if obs is None:
            print("[click] thoát, không ghi")
            return 2
    try:
        res = anchor_from_clicks(cams, obs)
    except ValueError as e:
        print(f"[LỖI] {e}")
        return 1
    print("[click] " + summarize(res))
    save_anchor(path, obs, res, len(cams), overwrite=args.overwrite)
    print(f"[click] đã ghi L_model vào {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
