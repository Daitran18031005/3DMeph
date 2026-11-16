"""Áp quy tắc đặt trước (PLAN.md) lên data/sweeps/m4_tauw/gate_variants.csv: chọn τ_w trên toàn bộ và leave-one-scene-out.

    python docs/evidence/m4_improve/tau_w/loso.py data/sweeps/m4_tauw/gate_variants.csv
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "scripts"))
import gate_variants as gv  # noqa: E402

BASE, GRID = "tw050", ["tw020", "tw030", "tw040"]          # nhỏ → lớn: chọn giá trị nhỏ nhất đạt


def ok(tab, name, scenes):
    r = gv.check(tab, name, base=BASE, scenes=scenes)
    return r["pass_frac_ratio"] >= 1.5 and r["A2"] and r["A3"] and r["A4"], r


def pick(tab, scenes):
    return next((n for n in GRID if ok(tab, n, scenes)[0]), None)


def main(csv_path):
    sys.stdout.reconfigure(encoding="utf-8")
    tab = gv._tab(gv.read_rows(Path(csv_path)))
    sc = gv.SCENES
    for n in GRID:
        good, r = ok(tab, n, sc)
        print(f"{n}: qua cổng ×{r['pass_frac_ratio']:.2f}, Δchính xác {r['A2_acc_passed_d']:+.3f}, scene cải thiện {r['A3_scenes_improved']}, "
              f"Δtỉ lệ cải thiện {r['A3_frac_improved_d']:+.3f}, ΔF {r['A4_dF']:+.4f}, ΔChamfer {r['A4_dChamfer_rel']:+.1%}, ΔF xấu nhất {r['A4_worst_scene_dF']:+.3f} → {'ĐẠT' if good else 'không'}")
    print(f"Chọn trên 6 scene: {pick(tab, sc)}")
    chosen, passed = [], 0
    for x in sc:
        p = pick(tab, [s for s in sc if s != x])
        chosen.append(p)
        if p:
            d_acc = tab[p][x]["acc_passed"] - tab[BASE][x]["acc_passed"]
            d_f = tab[p][x]["f_score"] - tab[BASE][x]["f_score"]
            hold = d_acc >= -0.02 and d_f >= -0.010
            passed += hold
            print(f"  bỏ {x}: chọn {p}; trên {x}: Δchính xác {d_acc:+.3f}, ΔF {d_f:+.4f} → {'giữ' if hold else 'HỎNG'}")
        else:
            print(f"  bỏ {x}: không giá trị nào đạt")
    top = max(set(chosen), key=chosen.count)
    accept = top is not None and chosen.count(top) >= 5 and passed >= 5
    print(f"Kết luận: {'NHẬN τ_w = ' + top if accept else 'GIỮ 0,5'} (chọn {top} ở {chosen.count(top)}/6 lần, qua kiểm {passed}/6)")


if __name__ == "__main__":
    main(sys.argv[1])
