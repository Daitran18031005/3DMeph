#!/usr/bin/env python3
"""
pick_endpoints.py — chọn hai điểm trên point cloud/mesh mô hình, đo theo (30), so với thước dây (ĐC §8.3, §19.1; kế hoạch §4.8).

Lưu đầu mút vào `<scene>/evaluation/logs/endpoints_<variant>.json` (định dạng ở pipeline/export/README.md; luồng eval đọc file này).
`id` mỗi đoạn là `id` của đoạn tương ứng trong `ground_truth/measurements.csv` (S01, ...). Mốc scale (`used_as_anchor=1`) bị loại
khỏi chỉ số test. Dữ liệu và scene: đọc `paths.data_root` của `--config`; scene held-out bị chặn.

Cách dùng (từ thư mục gốc repo, env 3d_metric):
    python scripts/pick_endpoints.py pick    --scene arkitscenes/42444738 [--variant proposed] [--points FILE | --glb FILE] [--height] [--blind]   # GUI Open3D, màu RGB video (--height: theo độ cao; --blind: ẩn GT và độ lệch)
    python scripts/pick_endpoints.py add     --scene arkitscenes/42444738 --id S01 --a X Y Z --b X Y Z [--replace]            # không GUI
    python scripts/pick_endpoints.py tape    --scene arkitscenes/42444738 --id S01 --readings 1.234 1.236 1.235 [--anchor]    # GT thước dây
    python scripts/pick_endpoints.py tape    --scene arkitscenes/42444738 --write-csv [--overwrite]                           # → measurements.csv
    python scripts/pick_endpoints.py compare --scene arkitscenes/42444738 [--gt tape|csv] [--out FILE.csv]

Mã thoát: 0 ok; 1 lỗi đầu vào (held-out, thiếu file, dữ liệu sai).
"""

from __future__ import annotations

import argparse
import csv
import functools
import re
import sys
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pipeline  # noqa: E402,F401  (import torch trước cv2/open3d/pycolmap)

# isort: split
import numpy as np  # noqa: E402

from pipeline.common import config as cfgmod  # noqa: E402
from pipeline.common import splits as sp  # noqa: E402
from pipeline.common.ply import read_ply  # noqa: E402
from pipeline.export import measure as ms  # noqa: E402
from pipeline.run import resolve_scene  # noqa: E402

DEFAULT_POINTS = "proposed/export/model_points.ply"
TAPE_NAME = "tape_measurements.json"
GT_CSV_NAME = "measurements.csv"


# ---------------------------------------------------------------------------
# Điểm hiển thị, gợi ý GT
# ---------------------------------------------------------------------------


def load_points(path: Path) -> np.ndarray:
    """Điểm (N, 3) float64 từ PLY (`model_points.ply`) hoặc đỉnh mesh của GLB."""
    path = Path(path)
    if path.suffix.lower() == ".glb":
        import trimesh

        scene = trimesh.load(str(path))
        mesh = scene.dump(concatenate=True) if hasattr(scene, "dump") else scene
        return np.asarray(mesh.vertices, dtype=np.float64)
    d = read_ply(path)
    return np.stack([d["x"], d["y"], d["z"]], axis=1).astype(np.float64)


def gt_hints(scene_root: Path) -> Dict[str, Dict]:
    """id → {gt_m, anchor, label} từ GT thước dây (nếu có) hoặc `measurements.csv`; rỗng nếu chưa có GT."""
    gt_dir = scene_root / "ground_truth"
    tape = ms.read_json_if_exists(gt_dir / TAPE_NAME)
    if tape is not None:
        return {s["id"]: {"gt_m": s["median_m"], "anchor": bool(s["used_as_anchor"]), "label": f"{s['type']} {s['notes']}".strip()}
                for s in tape["segments"]}
    if not (gt_dir / GT_CSV_NAME).is_file():
        return {}
    with open(gt_dir / GT_CSV_NAME, newline="", encoding="utf-8") as f:
        # cột notes có dạng "A=(...) B=(...); nhãn": bỏ phần toạ độ Faro (hệ scene, vô nghĩa trên mô hình)
        return {r["id"]: {"gt_m": float(r["ground_truth_m"]), "anchor": r["used_as_anchor"].strip() == "1",
                          "label": re.sub(r"^A=\(.*?\) B=\(.*?\);?\s*", "", r["endpoints/notes"])} for r in csv.DictReader(f)}


def next_free_id(doc: Dict, hints: Dict[str, Dict]) -> str:
    """Id GT đầu tiên chưa chọn; hết GT thì S## kế tiếp."""
    done = {s["id"] for s in doc["segments"]}
    for i in hints:
        if i not in done:
            return i
    nums = [int(i[1:]) for i in done if i[:1] == "S" and i[1:].isdigit()]
    return f"S{(max(nums) if nums else 0) + 1:02d}"


# ---------------------------------------------------------------------------
# Vòng chọn (GUI)
# ---------------------------------------------------------------------------

HELP_TEXT = """\
  Cửa sổ Open3D:  chuột trái kéo = xoay · Ctrl + chuột trái kéo = dịch · cuộn chuột = phóng to/thu nhỏ · + / - = đổi cỡ điểm · R = góc nhìn ban đầu
                  SHIFT + chuột trái = chọn điểm (đúng 2 điểm: A rồi B) · SHIFT + chuột phải = bỏ điểm vừa chọn · Q = đóng cửa sổ
                  Đừng bấm K, C, S. Chọn đúng vị trí vật lý đã đo thước dây / chấm trên Faro (góc, cạnh rõ nét)."""


def rgb_colors(scene_root: Path, points: np.ndarray, points_file: Path) -> Optional[np.ndarray]:
    """Màu RGB (N, 3 trong [0, 1]) của điểm mô hình, lấy từ điểm MVS gần nhất (`baselines/colmap/metric/fused_metric.ply`, hệ COLMAP × `s_m`).
    Chỉ để nhìn cho dễ chọn, không đổi toạ độ. `None` nếu thiếu file hoặc hai đám mây không cùng hệ (ví dụ B1 ở hệ VGGT)."""
    from scipy.spatial import cKDTree

    sys.path.insert(0, str(REPO / "scripts"))
    import annotate_segments as an

    from pipeline.eval.lengths import model_to_colmap_metric

    ply = scene_root / "baselines" / "colmap" / "metric" / "fused_metric.ply"
    if not ply.is_file():
        return None
    p = points
    if ms.frame_of_points_file(points_file) == ms.MODEL_FRAME:
        frame = ms.read_json_if_exists(scene_root / "proposed" / "export" / "measurements.json")
        if frame is None:
            return None
        p = np.apply_along_axis(model_to_colmap_metric(frame["frame"]), 1, points)
    xyz, rgb = an.read_ply_xyz_rgb(ply)
    dist, idx = cKDTree(xyz).query(p)
    return rgb[idx] if np.median(dist) < 0.10 else None


def gui_pick(points: np.ndarray, title: str, colors: Optional[np.ndarray] = None) -> Optional[Tuple[int, int]]:
    """Cửa sổ Open3D của annotate_segments (tái dùng); màu RGB nếu có `colors`, không thì theo độ cao y (mô hình có +Y lên)."""
    sys.path.insert(0, str(REPO / "scripts"))
    import annotate_segments as an

    return an.pick_two_points(points, title, colors=an.height_colors(points[:, 1]) if colors is None else colors)


def pick_loop(doc: Dict, save: Callable[[], None], points: np.ndarray, hints: Dict[str, Dict],
              pick: Callable[[np.ndarray, str], Optional[Tuple[int, int]]] = gui_pick,
              ask: Callable[[str], str] = input, out: Callable[[str], None] = print, blind: bool = False) -> None:
    """Vòng chọn tương tác; `pick`, `ask` thay được bằng bản giả để test. Lưu (`save`) sau mỗi đoạn.
    `blind=True`: không in số GT và độ lệch (chỉ id, nhãn, mốc), để chọn đầu mút không biết sai số; thấy sai số rồi chọn lại làm lệch kết quả."""
    segs = doc["segments"]
    while True:
        out(f"\n[phiên] {len(segs)} đoạn đã chọn" + (f" / {len(hints)} đoạn GT" if hints else " (chưa có GT để gợi ý id)"))
        cmd = ask("Enter = chọn đoạn mới · l = liệt kê · u = xoá đoạn cuối · q = dừng: ").strip().lower()
        if cmd == "q":
            return
        if cmd == "l":
            for i, h in hints.items():
                mine = next((s for s in segs if s["id"] == i), None)
                out(f"  {i:<5} {'' if blind else f'GT {h['gt_m']:.4f} m'}{' (mốc)' if h['anchor'] else ''}  {h['label'][:50]:<50}  "
                    + (f"đã chọn: {mine['length_m']:.4f} m" if mine else "chưa chọn"))
            continue
        if cmd == "u":
            if segs:
                gone = segs.pop()
                save()
                out(f"  đã xoá {gone['id']} ({gone['length_m']:.4f} m)")
            else:
                out("  chưa có đoạn nào")
            continue
        default = next_free_id(doc, hints)
        seg_id = ask(f"  id đoạn (trùng id trong {GT_CSV_NAME}) [Enter = {default}]: ").strip() or default
        replace = False
        if any(s["id"] == seg_id for s in segs):
            if ask(f"  {seg_id} đã có; ghi đè? (y/n): ").strip().lower() != "y":
                continue
            replace = True
        if hints and seg_id not in hints:
            out(f"  [cảnh báo] {seg_id} không có trong GT: sẽ không ghép được khi so sánh")
        if hints.get(seg_id):
            h = hints[seg_id]
            out(f"  {'' if blind else f'GT {h['gt_m']:.4f} m'}{' (MỐC SCALE)' if h['anchor'] else ''}: {h['label']}")
        out(HELP_TEXT)
        picked = pick(points, f"Chọn 2 đầu mút của {seg_id} bằng SHIFT+chuột trái, rồi bấm Q")
        if picked is None:
            out("  [!] cần đúng 2 điểm; không lưu. Thử lại.")
            continue
        ia, ib = picked
        a, b = points[ia], points[ib]
        length = ms.distance(a, b)
        out(f"  A = {np.round(a, 3).tolist()}\n  B = {np.round(b, 3).tolist()}\n  ‖B − A‖ = {length:.4f} m" +
            (f"  (GT {hints[seg_id]['gt_m']:.4f} m, lệch {(length - hints[seg_id]['gt_m']) * 100:+.1f} cm)" if seg_id in hints and not blind else ""))
        note = ask("  Ghi chú (Enter bỏ qua): ").strip()
        if ask("  Lưu đoạn này? (y/n): ").strip().lower() != "y":
            out("  bỏ qua.")
            continue
        try:
            ms.add_segment(doc, seg_id, a, b, note=note, a_index=int(ia), b_index=int(ib), replace=replace)
        except ms.MeasureError as e:
            out(f"  [lỗi] {e}")
            continue
        save()
        out(f"  đã lưu {seg_id}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _points_arg(args, scene_root: Path) -> Path:
    given = getattr(args, "glb", None) or getattr(args, "points", None) or DEFAULT_POINTS
    p = Path(given)
    return p if p.is_absolute() else scene_root / p


def _rel(p: Path, scene_root: Path) -> str:
    try:
        return p.resolve().relative_to(scene_root.resolve()).as_posix()
    except ValueError:
        return str(p)


def _open_endpoints(args, scene_root: Path, points_file: Path) -> Tuple[Dict, Path]:
    """Nạp (hoặc tạo) endpoints_<variant>.json; từ chối nếu file điểm đã đổi so với lần chọn trước."""
    if not points_file.is_file():
        raise ms.MeasureError(f"không thấy file điểm {points_file}")
    sha = ms.sha256_file(points_file)
    path = ms.endpoints_path(scene_root, args.variant)
    doc = ms.load_endpoints(path)
    if doc is None:
        doc = ms.new_endpoints(args.scene, args.variant, _rel(points_file, scene_root), sha, ms.frame_of_points_file(points_file))
    else:
        ms.check_points_hash(doc, sha)
    return doc, path


def _print_compare(res: Dict) -> None:
    print(f"{'id':<6}{'GT (m)':>9}{'mô hình (m)':>13}{'lệch (cm)':>11}")
    for r in res["rows"]:
        print(f"{r['id']:<6}{r['gt_m']:>9.4f}{r['model_m']:>13.4f}{r['err_cm']:>+11.2f}")
    m = res["metrics"]
    print(f"\n{m['n']} đoạn test: MAE {m['mae_cm']:.2f} cm · median {m['median_cm']:.2f} cm · MAPE {m['mape_percent']:.2f}% · "
          f"%<{m['under_cm']:g} cm {m['under_pct']:.1f}%")
    if res["excluded_anchor"]:
        print(f"[loại khỏi chỉ số] mốc scale: {', '.join(res['excluded_anchor'])}")
    if res["missing_gt"]:
        print(f"[cảnh báo] có đầu mút nhưng không có GT: {', '.join(res['missing_gt'])}")
    if res["missing_model"]:
        print(f"[cảnh báo] có GT nhưng chưa chọn đầu mút: {', '.join(res['missing_model'])}")


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--scene", required=True, help="arkitscenes/<video_id>")
    common.add_argument("--root", default=str(REPO), help="gốc repo (chứa data/splits.csv)")
    common.add_argument("--config", default=str(REPO / "configs" / "default.yaml"))
    common.add_argument("--variant", default="proposed", help="proposed | B0 | B1 | B3 | abl_quality | abl_gate")
    ap = argparse.ArgumentParser(description="Chọn đầu mút trên mô hình, đo theo (30), so với thước dây")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pk = sub.add_parser("pick", parents=[common], help="chọn 2 điểm bằng cửa sổ Open3D")
    pk.add_argument("--points", help=f"PLY điểm (mặc định {DEFAULT_POINTS}); tương đối so với thư mục scene")
    pk.add_argument("--glb", help="dùng đỉnh mesh của GLB thay cho PLY (mesh Poisson có thể bịa mặt ở vùng thiếu điểm)")
    pk.add_argument("--height", action="store_true", help="tô màu theo độ cao y thay cho RGB của video")
    pk.add_argument("--blind", action="store_true", help="ẩn số GT và độ lệch khi chọn (đo mù); mặc định in GT và lệch sau mỗi lần chọn")
    ad = sub.add_parser("add", parents=[common], help="nhập toạ độ đầu mút không GUI")
    ad.add_argument("--id", required=True)
    ad.add_argument("--a", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"))
    ad.add_argument("--b", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"))
    ad.add_argument("--points")
    ad.add_argument("--note", default="")
    ad.add_argument("--replace", action="store_true")
    tp = sub.add_parser("tape", parents=[common], help="nhập GT thước dây (3 lần đo, trung vị)")
    tp.add_argument("--id")
    tp.add_argument("--readings", nargs="+", type=float, metavar="M", help="số đo (m); đúng measure.tape_readings giá trị")
    tp.add_argument("--anchor", action="store_true", help="đoạn này là mốc scale (used_as_anchor=1, dài 1–2 m)")
    tp.add_argument("--type", default="other")
    tp.add_argument("--notes", default="")
    tp.add_argument("--write-csv", action="store_true", help=f"ghi {GT_CSV_NAME} [ĐC §9] từ GT thước dây")
    tp.add_argument("--overwrite", action="store_true")
    cp = sub.add_parser("compare", parents=[common], help="sai số so với GT")
    cp.add_argument("--gt", choices=("tape", "csv"), help=f"nguồn GT; mặc định {TAPE_NAME} nếu có, không thì {GT_CSV_NAME}")
    cp.add_argument("--out", help="ghi bảng từng đoạn ra CSV")
    args = ap.parse_args(argv)

    try:
        cfg = cfgmod.load_config(Path(args.config))
        info = resolve_scene(Path(args.root), args.scene, cfg)
        scene_root = info["layout"].root
        n_tape = int(cfgmod.require(cfg, "measure.tape_readings"))
        anchor_range = (float(cfgmod.require(cfg, "measure.anchor_min_m")), float(cfgmod.require(cfg, "measure.anchor_max_m")))

        if args.cmd == "pick":
            points_file = _points_arg(args, scene_root)
            doc, path = _open_endpoints(args, scene_root, points_file)
            points = load_points(points_file)
            print(f"[hiển thị] {len(points):,} điểm từ {points_file}; lưu vào {path}")
            colors = None if args.height else rgb_colors(scene_root, points, points_file)
            print("[màu] RGB lấy từ điểm MVS gần nhất" if colors is not None else "[màu] theo độ cao y")
            pick_loop(doc, lambda: ms.save_endpoints(path, doc), points, gt_hints(scene_root),
                      pick=functools.partial(gui_pick, colors=colors), blind=args.blind)
            print(f"[xong] {len(doc['segments'])} đoạn trong {path}")
            return 0

        if args.cmd == "add":
            doc, path = _open_endpoints(args, scene_root, _points_arg(args, scene_root))
            seg = ms.add_segment(doc, args.id, args.a, args.b, note=args.note, replace=args.replace)
            ms.save_endpoints(path, doc)
            print(f"[OK] {seg['id']}: ‖B − A‖ = {seg['length_m']:.4f} m → {path}")
            return 0

        if args.cmd == "tape":
            tape_path = scene_root / "ground_truth" / TAPE_NAME
            doc = ms.read_json_if_exists(tape_path) or ms.new_tape(args.scene)
            if args.id:
                if args.readings is None:
                    raise ms.MeasureError("thiếu --readings")
                seg = ms.add_tape(doc, args.id, args.readings, n_tape, anchor_range, anchor=args.anchor, seg_type=args.type, notes=args.notes)
                ms.write_json_atomic(tape_path, doc)
                print(f"[OK] {seg['id']}: trung vị {seg['median_m']:.4f} m{' (MỐC SCALE)' if seg['used_as_anchor'] else ''} → {tape_path}")
            elif not args.write_csv:
                raise ms.MeasureError("cần --id (kèm --readings) hoặc --write-csv")
            if args.write_csv:
                if not doc["segments"]:
                    raise ms.MeasureError("chưa có đoạn thước dây nào để ghi CSV")
                csv_path = scene_root / "ground_truth" / GT_CSV_NAME
                ms.write_csv(csv_path, ms.tape_to_rows(doc), overwrite=args.overwrite)
                print(f"[OK] ghi {csv_path} ({len(doc['segments'])} dòng)")
            return 0

        # compare
        doc = ms.load_endpoints(ms.endpoints_path(scene_root, args.variant))
        if doc is None:
            raise ms.MeasureError(f"chưa có {ms.endpoints_path(scene_root, args.variant)}: chạy pick hoặc add trước")
        pts = Path(doc["points_file"])
        pts = pts if pts.is_absolute() else scene_root / pts
        if pts.is_file():
            ms.check_points_hash(doc, ms.sha256_file(pts))
        else:
            print(f"[cảnh báo] không thấy {pts}: không kiểm được đầu mút còn khớp mô hình")
        tape_path = scene_root / "ground_truth" / TAPE_NAME
        use = args.gt or ("tape" if tape_path.is_file() else "csv")
        gt = ms.gt_from_tape(ms.read_json_if_exists(tape_path)) if use == "tape" else ms.gt_from_csv(scene_root / "ground_truth" / GT_CSV_NAME)
        print(f"[GT] {'thước dây (' + TAPE_NAME + ')' if use == 'tape' else GT_CSV_NAME}, biến thể {args.variant}")
        res = ms.compare(doc, gt, float(cfgmod.require(cfg, "measure.under_cm")))
        _print_compare(res)
        if args.out:
            with open(args.out, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["id", "gt_m", "model_m", "err_cm"])
                w.writeheader()
                w.writerows(res["rows"])
            print(f"[OK] ghi {args.out}")
        return 0
    except (ms.MeasureError, sp.HeldoutError, sp.LockError, ValueError, FileNotFoundError, KeyError) as e:
        print(f"[LỖI] {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
