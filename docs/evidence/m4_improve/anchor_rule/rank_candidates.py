"""Áp dụng quy tắc R1–R4 (PLAN.md): xếp hạng đoạn ứng viên làm mốc theo độ nhìn thấy. Chỉ đọc."""
import json, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / "scripts"))
import pipeline  # noqa
import annotate_segments as an
import faro_align
from pipeline.common.visibility import point_visibility

out = []
for sc in sys.argv[1:]:
    info = faro_align.resolve_scene(REPO, f"arkitscenes/{sc}")
    gt = REPO / "data" / "scenes" / "arkitscenes" / sc / "ground_truth"
    paths = an.Paths(gt)
    sess = json.loads(paths.session.read_text(encoding="utf-8"))
    f2s = json.loads(paths.f2s.read_text(encoding="utf-8"))
    pts, _ = an.load_rgb_display(paths, an.sha256_file(paths.f2s))
    cams, size = an.load_visibility_cams(gt.parent / "metadata" / "keyframes.csv", info["raw_dir"] / "lowres_wide.traj")
    nvis, spread = point_visibility(pts, cams, size)
    anchor = next(s for s in sess["segments"] if s["role"] == "anchor")
    print(f"== {sc}: mốc hiện tại {anchor['id']} {anchor['length_m']} m")
    rows = []
    for s in sess["segments"]:
        if s["role"] != "test" or not (1.8 <= s["length_m"] <= 2.5):
            continue
        ia, ib = s["a_index"], s["b_index"]
        r = {"id": s["id"], "L": s["length_m"], "label": s["label"], "n_a": int(nvis[ia]), "n_b": int(nvis[ib]), "ang_a": float(spread[ia]), "ang_b": float(spread[ib])}
        r["min_view"] = min(r["n_a"], r["n_b"]); r["min_ang"] = min(r["ang_a"], r["ang_b"])
        r["ok_R4"] = r["min_view"] >= an.VIS_MID[0] and r["min_ang"] >= an.VIS_MID[1]
        rows.append(r)
    rows.sort(key=lambda r: (-r["min_view"], -r["min_ang"], -r["L"]))
    for r in rows:
        print({k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items()})
    out.append({"scene": sc, "anchor": anchor["id"], "L_anchor": anchor["length_m"], "candidates": rows})
json.dump(out, open(Path(__file__).with_name("candidates.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
