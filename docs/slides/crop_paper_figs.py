"""Cắt hình từ các bài báo gốc trong Papers/ (ảnh nhúng + nét vẽ) để đưa vào slide, kèm nguồn.

Mỗi mục: (file PDF, trang, số hình, tên ra). Hình nằm TRÊN caption "Fig. N"/"Figure N".
Chạy: python crop_paper_figs.py  (ảnh ra docs/slides/img/paper_*.png)
"""

import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import pymupdf  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "img"
DPI = 220
GAP = 30
PAD = 4
CAP = re.compile(r"^\s*(Fig\.|Figure)\s*(\d+)\s*[.:]")

SPECS = [
    ("COLMAP_sfm", 2, 2, "paper_sfm_fig2"),  # Incremental SfM pipeline [4]
    ("COLMAP_sfm", 1, 1, "paper_sfm_fig1"),
    ("COLMAP_mvs", 1, 1, "paper_mvs_fig1"),
    ("COLMAP_mvs", 6, 2, "paper_mvs_fig2"),
    ("VGGT", 3, 2, "paper_vggt_fig2"),  # kiến trúc VGGT [2]
    ("VGGT", 1, 1, "paper_vggt_fig1"),
    ("ARKitscenes", 2, 1, "paper_arkit_fig1"),
    ("ARKitscenes", 5, 3, "paper_arkit_fig3"),
    ("Replica", 1, 1, "paper_replica_fig1"),
    ("Replica", 7, 7, "paper_replica_fig7"),
]


def caption_rect(page, num):
    for blk in page.get_text("dict")["blocks"]:
        for line in blk.get("lines", []):
            text = "".join(s["text"] for s in line["spans"])
            m = CAP.match(text)
            if m and int(m.group(2)) == num:
                return pymupdf.Rect(line["bbox"])
    return None


def figure_rect(page, cap):
    rects = []
    for item in page.get_image_info():
        rects.append(pymupdf.Rect(item["bbox"]))
    for d in page.get_drawings():
        r = d["rect"]
        if r.width > 5 or r.height > 5:
            rects.append(r)
    rects = [r for r in rects if r.y1 <= cap.y0 + 2 and r.height > 3]
    rects.sort(key=lambda r: -r.y1)
    top, region = cap.y0, None
    for r in rects:
        if r.y1 >= top - GAP:
            region = r if region is None else region | r
            top = min(top, r.y0)
    return region


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, pno, num, out in SPECS:
        doc = pymupdf.open(ROOT / "Papers" / f"{name}.pdf")
        page = doc[pno - 1]
        cap = caption_rect(page, num)
        if cap is None:
            print(f"{out}: không thấy caption Fig {num} ở trang {pno}")
            continue
        r = figure_rect(page, cap)
        if r is None:
            print(f"{out}: không thấy hình")
            continue
        r = pymupdf.Rect(r.x0 - PAD, r.y0 - PAD, r.x1 + PAD, r.y1 + PAD) & page.rect
        pix = page.get_pixmap(dpi=DPI, clip=r)
        pix.save(OUT / f"{out}.png")
        print(f"{out}: p{pno} {pix.width}x{pix.height}")


if __name__ == "__main__":
    main()
