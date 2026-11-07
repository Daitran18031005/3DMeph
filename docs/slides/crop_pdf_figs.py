"""Cắt các hình trong PDF đề cương (Docs/TaiTao3D_Metric_3DMeph.pdf) ra PNG để đưa vào slide.

Hình trong PDF là vector, caption "Hình N." nằm DƯỚI hình. Với mỗi caption: lấy cụm nét vẽ liền kề
phía trên caption (khoảng hở dọc <= GAP pt), cộng chữ nằm trong cụm, rồi render vùng đó.
Vùng sai (bảng/hộp chữ lọt vào) sửa bằng OVERRIDE (đơn vị pt của trang PDF: x0, y0, x1, y1).
Chạy: python crop_pdf_figs.py  (cần pymupdf; ảnh ra docs/slides/img/pdf_fig_NN.png)
"""

import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import pymupdf  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]  # 3D_Metric/
PDF = ROOT / "Docs" / "TaiTao3D_Metric_3DMeph.pdf"
OUT = Path(__file__).resolve().parent / "img"
DPI = 220
GAP = 32  # pt: khoảng hở dọc tối đa giữa các nét vẽ cùng một hình
PAD = 6  # pt: đệm quanh vùng cắt
# fig_no -> bbox (pt) cho hình mà cụm nét vẽ bị đứt (khoảng hở lớn hơn GAP); đã xem từng ảnh
OVERRIDE: dict[int, tuple[float, float, float, float]] = {
    1: (66, 238, 530, 520),
    12: (60, 60, 535, 180),
    15: (100, 64, 495, 334),
    19: (60, 306, 535, 470),
}

CAP = re.compile(r"^\s*H[iì]nh\s*(\d+)\.\s")


def find_captions(doc):
    caps = []
    for pno, page in enumerate(doc):
        # theo từng dòng (block có thể gộp caption với nhãn trong hình)
        for blk in page.get_text("dict")["blocks"]:
            for line in blk.get("lines", []):
                text = "".join(s["text"] for s in line["spans"])
                m = CAP.match(text)
                if m and line["spans"][0]["flags"] & 16:  # chữ đậm: "Hình N." đầu caption
                    caps.append((int(m.group(1)), pno, pymupdf.Rect(line["bbox"])))
    return caps


CALLOUT_W = 470  # pt: hộp "ĐỊNH NGHĨA/VÍ DỤ" rộng cả cột chữ (483 pt), không thuộc hình
LABEL_MAX = (300, 30)  # pt: khối chữ nhỏ hơn cỡ này mới coi là nhãn của hình


def figure_rect(page, cap: pymupdf.Rect):
    pw = page.rect.width
    allr = [d["rect"] for d in page.get_drawings()]
    callouts = [r for r in allr if r.width >= CALLOUT_W and r.height > 30]
    rects = []
    for r in allr:
        if r.y1 > cap.y0 + 1 or r.y0 < 45:  # dưới caption hoặc vùng header
            continue
        if r.width > pw * 0.9 and r.height < 3:  # đường kẻ ngang cả trang
            continue
        if any(c.contains(r) for c in callouts):  # nét vẽ nằm trong hộp callout
            continue
        rects.append(r)
    rects.sort(key=lambda r: -r.y1)
    top, region = cap.y0, None
    for r in rects:
        if r.y1 >= top - GAP:
            region = r if region is None else region | r
            top = min(top, r.y0)
    if region is None:
        return None
    # thêm nhãn chữ trong hoặc sát vùng (tiêu đề panel, nhãn dưới hình)
    labels = [
        pymupdf.Rect(b[:4])
        for b in page.get_text("blocks")
        if (b[2] - b[0]) <= LABEL_MAX[0] and (b[3] - b[1]) <= LABEL_MAX[1]
    ]
    for _ in range(2):
        probe = pymupdf.Rect(region.x0, region.y0 - 14, region.x1, region.y1 + 14)
        for br in labels:
            if br.intersects(probe) and br.y1 <= cap.y0 + 1:
                region |= br
    return region


def main(only=None):
    OUT.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(PDF)
    for n, pno, cap in find_captions(doc):
        if only and n not in only:
            continue
        page = doc[pno]
        r = pymupdf.Rect(OVERRIDE[n]) if n in OVERRIDE else figure_rect(page, cap)
        if r is None:
            print(f"Hình {n}: không tìm thấy vùng (trang {pno + 1})")
            continue
        r = pymupdf.Rect(r.x0 - PAD, r.y0 - PAD, r.x1 + PAD, r.y1 + PAD) & page.rect
        pix = page.get_pixmap(dpi=DPI, clip=r)
        pix.save(OUT / f"pdf_fig_{n:02d}.png")
        print(f"Hình {n:2d} p{pno + 1:2d} bbox=({r.x0:.0f},{r.y0:.0f},{r.x1:.0f},{r.y1:.0f}) {pix.width}x{pix.height}")


if __name__ == "__main__":
    main({int(a) for a in sys.argv[1:]} or None)
