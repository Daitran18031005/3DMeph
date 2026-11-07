"""Dựng bộ slide báo cáo dự án 3DMeph (30 slide) bằng python-pptx.

Chạy (Python hệ thống có python-pptx; ảnh đã tạo trước bằng crop_pdf_figs.py, crop_paper_figs.py,
render_results.py, render_equations.py trong cùng thư mục):
    python build_deck.py            ->  3DMeph_BaoCao.pptx
Mọi con số kết quả đọc thẳng từ file của scene dev 42444738 (JSON/CSV), không gõ tay lại.
Số ví dụ của đề cương (bàn 1,40 m, 72 keyframe...) luôn ghi nhãn "ví dụ ĐC".
"""

import csv
import json
import math
import sys
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
IMG = HERE / "img"
ROOT = HERE.parents[1]  # 3DMeph/
SCENE = ROOT / "data" / "scenes" / "arkitscenes" / "42444738"
SWEEP = ROOT / "docs" / "evidence" / "m2_sfm" / "after_30-10" / "sweep.csv"
OUTFILE = HERE / "3DMeph_BaoCao.pptx"

# ---------- giao diện ----------
INK = RGBColor(0x10, 0x30, 0x3A)  # nền tối, tiêu đề
TEAL = RGBColor(0x1E, 0x7A, 0x8C)  # nhấn chính
AMBER = RGBColor(0xE8, 0xA3, 0x3D)  # nhấn phụ (thước đo)
PALE = RGBColor(0xF4, 0xF7, 0xF8)  # nền thẻ
LINE = RGBColor(0xD5, 0xDE, 0xE2)
MUTED = RGBColor(0x5B, 0x6B, 0x73)
RED = RGBColor(0xC8, 0x45, 0x3B)
GREEN = RGBColor(0x3E, 0x9B, 0x6B)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
HEAD, BODY = "Cambria", "Calibri"
SW, SH = 13.333, 7.5
TOTAL = 30
WARN = []


# ---------- số liệu thật ----------
def jl(rel):
    return json.loads((SCENE / rel).read_text(encoding="utf-8"))


def vn(x, nd=1):
    """Số thập phân kiểu Việt: dấu phẩy."""
    return f"{x:.{nd}f}".replace(".", ",")


def vi(x):
    """Số nguyên có dấu chấm ngăn nghìn."""
    return f"{int(round(x)):,}".replace(",", ".")


def load_csv(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


SFM, MVS, VGGT = (
    jl("baselines/colmap/sfm/sfm_result.json"),
    jl("baselines/colmap/mvs/mvs_result.json"),
    jl("baselines/vggt/vggt_result.json"),
)
ALIGN, SCALE = jl("proposed/alignment/align_result.json"), jl("proposed/alignment/scale.json")
FUS, GATE = jl("proposed/fusion/fusion_result.json"), jl("proposed/plane_refinement/gate_result.json")
RUN = jl("evaluation/logs/run_meta.json")["stages"]
KF = RUN["keyframe"]["stats"]
METRICS = {r["variant"]: r for r in load_csv(SCENE / "evaluation" / "metrics.csv")}
SWEEP_ROWS = load_csv(SWEEP)


def seg_errors(variant):
    rows = load_csv(SCENE / "evaluation" / "logs" / f"lengths_{variant}_manual.csv")
    return {r["id"]: float(r["err_m"]) * 100 for r in rows if r["valid"] == "True"}


ERR_B0, ERR_PROP = seg_errors("B0"), seg_errors("proposed")


def f(v, nd=2):
    return vn(float(v), nd) if v not in ("", None) else "—"


# ---------- tiện ích dựng ----------
prs = Presentation()
prs.slide_width, prs.slide_height = Inches(SW), Inches(SH)
BLANK = prs.slide_layouts[6]
_n = [0]


def est_h(paras, w_in, size_pt, space_pt=4):
    """Ước chiều cao (inch) của khối chữ: ~0,5 em mỗi ký tự, giãn dòng 1,2."""
    cpl = max(1, w_in * 72 / (size_pt * 0.5))
    lines = 0
    for p in paras:
        t = p if isinstance(p, str) else "".join(r[0] for r in p)
        lines += max(1, math.ceil(len(t) / cpl))
    return (lines * size_pt * 1.2 + len(paras) * space_pt) / 72


def set_bullet(p, indent_in=0.22):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(int(Inches(indent_in))))
    pPr.set("indent", str(-int(Inches(indent_in))))
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    bu = pPr.makeelement(qn("a:buChar"), {"char": "•"})
    pPr.append(bu)


def txt(
    slide,
    x,
    y,
    w,
    h,
    paras,
    size=14,
    color=INK,
    bold=False,
    font=BODY,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
    bullet=False,
    space=4,
    italic=False,
    margin=0.04,
    name=None,
):
    """paras: danh sách đoạn; mỗi đoạn là str hoặc list các run (text, {bold,color,italic,size})."""
    if isinstance(paras, str):
        paras = [paras]
    need = est_h(paras, w - 2 * margin - (0.22 if bullet else 0), size, space)
    if need > h + 0.05:
        WARN.append(f"slide {_n[0]}: chữ có thể tràn ({need:.2f} > {h:.2f} in): {str(paras[0])[:40]}")
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(margin)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = anchor
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space)
        if bullet:
            set_bullet(p)
        runs = [(para, {})] if isinstance(para, str) else para
        for text, o in runs:
            r = p.add_run()
            r.text = text
            r.font.name = o.get("font", font)
            r.font.size = Pt(o.get("size", size))
            r.font.bold = o.get("bold", bold)
            r.font.italic = o.get("italic", italic)
            r.font.color.rgb = o.get("color", color)
    return tb


def rect(slide, x, y, w, h, fill=PALE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06, name=None):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        s.name = name
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(0.75)
    s.shadow.inherit = False
    return s


def card(slide, x, y, w, h, title, body, size=14, accent=TEAL, fill=PALE, bullet=False, title_size=16, space=4):
    rect(slide, x, y, w, h, fill=fill)
    txt(slide, x + 0.15, y + 0.1, w - 0.3, 0.4, title, size=title_size, bold=True, color=accent, font=HEAD)
    body = body if isinstance(body, list) else [body]
    txt(slide, x + 0.15, y + 0.5, w - 0.3, h - 0.58, body, size=size, bullet=bullet, space=space)


def stat(slide, x, y, w, big, label, color=TEAL, big_size=30, h=1.2, fill=PALE):
    rect(slide, x, y, w, h, fill=fill)
    txt(
        slide,
        x + 0.1,
        y + 0.08,
        w - 0.2,
        0.6,
        big,
        size=big_size,
        bold=True,
        color=color,
        font=HEAD,
        align=PP_ALIGN.CENTER,
    )
    txt(slide, x + 0.1, y + 0.72, w - 0.2, h - 0.76, label, size=12, color=MUTED, align=PP_ALIGN.CENTER)


def pill(slide, x, y, w, text, fill, color=WHITE, h=0.3, size=11):
    s = rect(slide, x, y, w, h, fill=fill, line=None, radius=0.5)
    tf = s.text_frame
    tf.margin_left = tf.margin_right = Inches(0.04)
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = text
    r.font.size, r.font.bold, r.font.name, r.font.color.rgb = Pt(size), True, BODY, color
    return s


def pic(slide, name, x, y, w, h, caption=None, alt="", border=True, valign="top", cap_size=10):
    """Chèn ảnh vừa khung (x, y, w, h) giữ tỉ lệ; trả về (x, y, w, h) thực tế. caption đặt ngay dưới."""
    path = IMG / name if not Path(name).is_absolute() else Path(name)
    if not path.exists():
        raise FileNotFoundError(path)
    iw, ih = Image.open(path).size
    k = min(w / iw, h / ih)
    pw, ph = iw * k, ih * k
    px = x + (w - pw) / 2
    py = y if valign == "top" else y + (h - ph) / 2
    p = slide.shapes.add_picture(str(path), Inches(px), Inches(py), Inches(pw), Inches(ph))
    p._element.nvPicPr.cNvPr.set("descr", alt or (caption or name))
    if border:
        p.line.color.rgb = LINE
        p.line.width = Pt(0.75)
    if caption:
        txt(slide, x, py + ph + 0.03, w, 0.3, caption, size=cap_size, color=MUTED, align=PP_ALIGN.CENTER, italic=True)
    return px, py, pw, ph


def eq(slide, key, x, y, w, h, align="left"):
    """Chèn công thức đã render (eq_<key>.png), vừa khung, không viền."""
    path = IMG / f"eq_{key}.png"
    iw, ih = Image.open(path).size
    k = min(w / iw, h / ih)
    pw, ph = iw * k, ih * k
    px = x if align == "left" else x + (w - pw) / 2
    p = slide.shapes.add_picture(str(path), Inches(px), Inches(y + (h - ph) / 2), Inches(pw), Inches(ph))
    p._element.nvPicPr.cNvPr.set("descr", f"Công thức {key}")
    return pw, ph


def new_slide(title, section=None, source=None, notes="", dark=False):
    _n[0] += 1
    s = prs.slides.add_slide(BLANK)
    bg = s.background.fill
    bg.solid()
    bg.fore_color.rgb = INK if dark else WHITE
    if title:
        txt(
            s,
            0.5,
            0.36,
            10.7,
            0.85,
            title,
            size=30,
            bold=True,
            color=WHITE if dark else INK,
            font=HEAD,
            anchor=MSO_ANCHOR.MIDDLE,
            name="Tiêu đề",
        )
    if section:
        pill(s, 11.0, 0.55, 1.83, section, TEAL if not dark else AMBER, color=WHITE if not dark else INK)
    if source:
        txt(
            s,
            0.5,
            7.08,
            11.2,
            0.3,
            "Nguồn: " + source,
            size=10,
            color=MUTED if not dark else RGBColor(0xA9, 0xBC, 0xC4),
        )
    txt(
        s,
        11.9,
        7.08,
        0.93,
        0.3,
        f"{_n[0]} / {TOTAL}",
        size=10,
        color=MUTED if not dark else RGBColor(0xA9, 0xBC, 0xC4),
        align=PP_ALIGN.RIGHT,
    )
    s.notes_slide.notes_text_frame.text = notes
    return s


def table(
    slide, x, y, widths, rows, size=12, row_h=0.36, header_fill=INK, zebra=True, bold_first_col=True, aligns=None
):
    nr, nc = len(rows), len(widths)
    gs = slide.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(sum(widths)), Inches(row_h * nr))
    t = gs.table
    for j, wd in enumerate(widths):
        t.columns[j].width = Inches(wd)
    for i, row in enumerate(rows):
        t.rows[i].height = Inches(row_h)
        for j, val in enumerate(row):
            c = t.cell(i, j)
            c.margin_left = c.margin_right = Inches(0.07)
            c.margin_top = c.margin_bottom = Inches(0.03)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.fill.solid()
            c.fill.fore_color.rgb = header_fill if i == 0 else (PALE if (zebra and i % 2 == 0) else WHITE)
            tf = c.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            if aligns and aligns[j] == "c":
                p.alignment = PP_ALIGN.CENTER
            runs = [(val, {})] if isinstance(val, str) else val
            for text, o in runs:
                r = p.add_run()
                r.text = text
                r.font.name = BODY
                r.font.size = Pt(o.get("size", size))
                r.font.bold = o.get("bold", i == 0 or (bold_first_col and j == 0))
                r.font.color.rgb = o.get("color", WHITE if i == 0 else INK)
    return gs


def style_chart(chart, size=12, legend=True):
    chart.font.size = Pt(size)
    chart.font.name = BODY
    chart.font.color.rgb = INK
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(size)
    va = chart.value_axis
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = LINE
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(size)
    chart.category_axis.tick_labels.font.size = Pt(size)
    chart.category_axis.format.line.color.rgb = LINE


# =====================================================================
# A. MỞ ĐẦU (1–3)
# =====================================================================
s = new_slide(
    None,
    dark=True,
    notes=(
        "Kính chào thầy cô. Em là Trần Quang Đại, xin báo cáo tiến độ đồ án 3DMeph: dựng lại mô hình 3D có đơn vị mét "
        "của một căn phòng từ video quay bằng điện thoại thường. Báo cáo gồm năm phần: khái niệm và phương pháp, mục tiêu, "
        "kế hoạch, cách thực hiện, và kết quả hiện tại cùng các bước còn lại. Trạng thái tính đến ngày 06/11/2026."
    ),
)
rect(s, 0, 0, SW - 5.625, SH, fill=INK, line=None, shape=MSO_SHAPE.RECTANGLE)
kf = sorted((SCENE / "frames" / "keyframes").glob("*.jpg"))[31]
s.shapes.add_picture(str(kf), Inches(SW - 5.625), 0, Inches(5.625), Inches(SH))._element.nvPicPr.cNvPr.set(
    "descr", "Một keyframe thật của phòng khách trong scene dev 42444738"
)
txt(s, 0.7, 1.5, 6.6, 0.9, "3DMeph", size=60, bold=True, color=WHITE, font=HEAD)
txt(
    s,
    0.7,
    2.65,
    6.6,
    1.5,
    "Tái tạo 3D metric trong nhà từ video quay bằng điện thoại thường",
    size=28,
    color=AMBER,
    font=HEAD,
)
txt(s, 0.7, 4.5, 6.6, 0.4, "Báo cáo tiến độ dự án · Đồ án 2026", size=18, color=WHITE)
txt(s, 0.7, 5.0, 6.6, 0.4, "Trạng thái ngày 06/11/2026", size=16, color=RGBColor(0xA9, 0xBC, 0xC4))
txt(
    s,
    0.7,
    6.5,
    6.6,
    0.4,
    "Ảnh nền: keyframe thật của scene 42444738 (ARKitScenes)",
    size=11,
    color=RGBColor(0xA9, 0xBC, 0xC4),
)

s = new_slide(
    "Giới thiệu đề tài và người thực hiện",
    "Mở đầu",
    source="README.md, WORKING_LOG.md (06/11/2026)",
    notes=(
        "Đề tài tên đầy đủ là Tái tạo 3D metric trong nhà từ ảnh điện thoại. Dự án do em thực hiện một mình, dưới sự hướng dẫn "
        "của cô Lê Thị Vĩnh Thanh. Bài toán: quay video một đến hai phút trong phòng, hệ thống trả về mô hình 3D tính bằng mét, "
        "người dùng chọn hai điểm để đọc khoảng cách. Mục tiêu thử nghiệm là sai số trung vị dưới 5 cm cho phòng 3 đến 5 mét, "
        "sau một lần neo tỉ lệ bằng một đoạn dài 1 đến 2 mét. Đây là mục tiêu, chưa phải kết quả."
    ),
)
card(
    s,
    0.5,
    1.5,
    6.9,
    5.3,
    "Thông tin đề tài",
    [
        [("Đề tài: ", {"bold": True}), ("Tái tạo 3D metric trong nhà từ video điện thoại (3DMeph)", {})],
        [("Sinh viên thực hiện: ", {"bold": True}), ("Trần Quang Đại, MSSV 23714441 (một người)", {})],
        [("Giảng viên hướng dẫn: ", {"bold": True}), ("Lê Thị Vĩnh Thanh", {})],
        [("Loại: ", {"bold": True}), ("Đồ án 2026", {})],
        [("Dữ liệu: ", {"bold": True}), ("ARKitScenes, Replica, video tự thu", {})],
        [("Phần cứng: ", {"bold": True}), ("1 GPU RTX 4060 Laptop 8 GB", {})],
    ],
    size=19,
    bullet=True,
    space=12,
)
stat(s, 7.8, 1.5, 5.0, "1–2 phút", "video quay trong một phòng, bằng điện thoại thường", h=1.6, big_size=34)
stat(
    s,
    7.8,
    3.3,
    5.0,
    "< 5 cm",
    "mục tiêu sai số trung vị, phòng 3–5 m (mục tiêu, chưa phải kết quả)",
    color=AMBER,
    h=1.6,
    big_size=34,
)
stat(
    s,
    7.8,
    5.1,
    5.0,
    "1 đoạn 1–2 m",
    "mốc scale chỉ cần làm một lần để đổi toàn bộ mô hình sang mét",
    h=1.7,
    big_size=30,
)

s = new_slide(
    "Mục lục",
    "Mở đầu",
    notes=(
        "Báo cáo đi theo sáu nhóm. A: các khái niệm nền và lý do chọn phương pháp. B: mục tiêu thực tế và khoa học. "
        "C: kế hoạch đặt ra. D: cách thực hiện từng bước của phương pháp đề xuất. E: kết quả hiện tại, trình bày trung thực kể cả chỗ chưa đạt. "
        "F: các bước còn lại và kết luận hiện tại."
    ),
)
items = [
    (
        "A",
        "Khái niệm và phương pháp",
        "bài toán, cơ sở lý thuyết, dữ liệu, kiến trúc, phương pháp đề xuất, lý do chọn",
        "4–12",
    ),
    ("B", "Mục tiêu cuối cùng", "mặt thực tế và mặt khoa học", "13–14"),
    ("C", "Kế hoạch đặt ra", "các mốc M0a–M6 và tiến độ", "15"),
    (
        "D",
        "Cách thực hiện",
        "chín stage: keyframe, COLMAP, VGGT, căn tỉ lệ, fusion, plane gate, xuất, đánh giá",
        "16–24",
    ),
    ("E", "Kết quả hiện tại", "chạy thật scene dev, số đo chiều dài, kiểm tra trên 6 scene Validation", "25–27"),
    ("F", "Còn lại và kết luận", "các bước hoàn thiện, kết luận hiện tại, tài liệu tham khảo", "28–30"),
]
for i, (k, t1, t2, pg) in enumerate(items):
    y = 1.5 + i * 0.9
    rect(s, 0.5, y, 12.33, 0.78, fill=PALE)
    c = rect(s, 0.62, y + 0.1, 0.58, 0.58, fill=TEAL, line=None, shape=MSO_SHAPE.OVAL)
    txt(
        s,
        0.62,
        y + 0.1,
        0.58,
        0.58,
        k,
        size=22,
        bold=True,
        color=WHITE,
        font=HEAD,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        margin=0,
    )
    txt(s, 1.45, y + 0.06, 8.6, 0.36, t1, size=19, bold=True, font=HEAD)
    txt(s, 1.45, y + 0.4, 9.6, 0.34, t2, size=14, color=MUTED)
    txt(s, 11.2, y + 0.18, 1.5, 0.4, f"slide {pg}", size=14, color=TEAL, bold=True, align=PP_ALIGN.RIGHT)

# =====================================================================
# A. KHÁI NIỆM (4–12)
# =====================================================================
s = new_slide(
    "Bài toán: từ video điện thoại ra số đo mét",
    "A · Khái niệm",
    source="ĐC Hình 3 (Docs/TaiTao3D_Metric_3DMeph.pdf); ảnh keyframe thật scene 42444738",
    notes=(
        "Đây là bài toán cụ thể. Đầu vào là video quay một vòng quanh phòng. Hệ thống chạy qua bốn giai đoạn: lấy ảnh sạch, dựng hình, "
        "gắn mét, làm sạch rồi đo. Ảnh bên phải là sáu trong tám mươi keyframe thật của scene dev. Điểm khó nhất là dựng hình từ ảnh "
        "thì chỉ có hình dạng mà chưa có đơn vị mét; phần sau sẽ giải thích vì sao và cách gắn mét bằng một đoạn mốc."
    ),
)
pic(
    s,
    "pdf_fig_03.png",
    0.5,
    1.45,
    12.33,
    1.45,
    "Bốn giai đoạn của hệ thống [ĐC Hình 3]",
    alt="Sơ đồ bốn giai đoạn: lấy ảnh sạch, dựng hình, gắn mét, làm sạch, đo",
)
txt(
    s,
    0.5,
    3.15,
    6.4,
    3.8,
    [
        [("Vào: ", {"bold": True, "color": TEAL}), ("video 1–2 phút quay trong một phòng bằng điện thoại thường.", {})],
        [
            ("Ra: ", {"bold": True, "color": TEAL}),
            ("mô hình 3D đơn vị mét; chọn hai điểm trên mô hình để đọc khoảng cách.", {}),
        ],
        [
            ("Mục tiêu đo: ", {"bold": True, "color": TEAL}),
            ("sai số trung vị < 5 cm cho phòng 3–5 m, sau một lần neo scale bằng đoạn 1–2 m [ĐC trang 1].", {}),
        ],
        [("Lưu ý: ", {"bold": True, "color": RED}), ("đây là mục tiêu thử nghiệm, chưa phải kết quả.", {})],
    ],
    size=17,
    bullet=True,
    space=10,
)
pic(
    s,
    "res_keyframes.png",
    7.2,
    3.15,
    5.63,
    3.4,
    "6 trong 80 keyframe thật của scene dev 42444738",
    alt="Lưới sáu keyframe phòng khách",
)

s = new_slide(
    "Vì sao cần bước neo scale (đổi sang mét)",
    "A · Khái niệm",
    source="ĐC §2, Hình 2; pipeline/alignment/README.md. Số trong ví dụ là số minh họa của đề cương",
    notes=(
        "Cả COLMAP lẫn VGGT đều không tự cho ra mét. Ví dụ trong đề cương: một chiếc bàn dài 1,40 m. COLMAP đo ra 0,688 đơn vị tuỳ ý, "
        "VGGT ra 0,215 đơn vị của riêng nó. Nếu ứng dụng đọc 0,688 thành 0,688 mét thì sai gần gấp đôi. "
        "Vì vậy phải neo bằng một đoạn thật dài 1 đến 2 mét: lấy chiều dài thật chia cho chiều dài trong mô hình ta được hệ số s_m đổi toàn bộ mô hình sang mét. "
        "Đây là số ví dụ của đề cương, không phải kết quả thí nghiệm."
    ),
)
pic(
    s,
    "pdf_fig_02.png",
    0.5,
    1.45,
    8.3,
    2.75,
    "Chiếc bàn 1,40 m đi qua tám bước (ví dụ ĐC Hình 2)",
    alt="Sơ đồ tám bước biến video thành số đo của bàn",
)
card(
    s,
    9.1,
    1.45,
    3.73,
    2.95,
    "Vấn đề",
    [
        "COLMAP và VGGT cho hình dạng đúng nhưng đơn vị tuỳ ý.",
        "Ví dụ ĐC: bàn thật 1,40 m, COLMAP ra 0,688 đv. Đọc nhầm thành mét thì sai gần gấp đôi.",
    ],
    size=14,
    accent=RED,
)
card(
    s,
    0.5,
    4.65,
    6.0,
    2.25,
    "Cách giải: một đoạn mốc 1–2 m",
    [
        "Chọn một đoạn dễ thấy, không nằm trên gương hoặc kính, đo chiều dài thật L_real.",
        "Hệ số mét của cả scene (công thức (4)):",
    ],
    size=14,
)
eq(s, "sm", 3.5, 5.75, 2.4, 1.05, align="center")
card(
    s,
    6.83,
    4.65,
    6.0,
    2.25,
    "Đổi toàn bộ về mét",
    ["Áp lên điểm VGGT đã căn vào COLMAP (công thức (18)); ví dụ ĐC: 0,215 × 3,20 × 2,00 = 1,376 m ≈ 1,38 m."],
    size=14,
)
eq(s, "xmet", 7.05, 5.75, 5.6, 0.85, align="center")

s = new_slide(
    "Cơ sở lý thuyết 1: COLMAP (SfM + MVS)",
    "A · Khái niệm",
    source="Schönberger & Frahm, CVPR 2016 (Hình 2); Schönberger và cs., ECCV 2016 (Hình 2); ĐC Hình 15",
    notes=(
        "COLMAP gồm hai phần. Structure from Motion tìm điểm đặc trưng, ghép cặp, kiểm tra hình học bằng RANSAC, rồi dựng dần camera và điểm 3D thưa, "
        "có bundle adjustment. Multi-View Stereo tính depth cho từng ảnh bằng PatchMatch rồi gộp thành điểm dày. "
        "Hình bên phải là hình đề cương vẽ lại đúng theo hai bài báo, kèm nơi sinh ra từng tín hiệu độ tin cậy: sai số chiếu lại e_reproj từ SfM, thưa; "
        "và sai lệch depth photometric so với geometric từ MVS, dày. Hai tín hiệu này sẽ vào bước fusion."
    ),
)
px, py, pw, ph = pic(
    s,
    "paper_sfm_fig2.png",
    0.5,
    1.45,
    5.9,
    1.4,
    "Quy trình SfM tăng dần (bài báo COLMAP SfM, Hình 2)",
    alt="Sơ đồ SfM tăng dần của COLMAP",
)
pic(
    s,
    "paper_mvs_fig2.png",
    0.5,
    3.15,
    5.9,
    1.0,
    "Các prior hình học của MVS (bài báo COLMAP MVS, Hình 2)",
    alt="Prior góc tam giác, độ phân giải, góc tới",
)
txt(
    s,
    0.5,
    4.5,
    5.9,
    2.0,
    [
        [
            ("SfM: ", {"bold": True, "color": TEAL}),
            ("đặc trưng → ghép cặp → RANSAC → PnP + bundle adjustment ⇒ camera và điểm 3D thưa.", {}),
        ],
        [
            ("MVS: ", {"bold": True, "color": TEAL}),
            ("PatchMatch photometric → geometric → lọc ⇒ điểm dày fused.ply.", {}),
        ],
        [("Tín hiệu cho fusion: ", {"bold": True, "color": TEAL}), ("e_reproj (thưa), σ_depth (dày).", {})],
    ],
    size=14,
    bullet=True,
    space=5,
)
eq(s, "ereproj", 0.55, 6.35, 3.5, 0.5)
pic(
    s,
    "pdf_fig_15.png",
    6.7,
    1.45,
    6.13,
    5.4,
    "Luồng COLMAP theo hai bài báo và nơi sinh tín hiệu [ĐC Hình 15]",
    alt="Luồng COLMAP SfM và MVS với tín hiệu e_reproj và sigma_depth",
)

s = new_slide(
    "Cơ sở lý thuyết 2: VGGT",
    "A · Khái niệm",
    source="Wang và cs., VGGT, CVPR 2025 (Hình 2); ĐC Hình 14",
    notes=(
        "VGGT là Visual Geometry Grounded Transformer: một mạng feed-forward nhận N ảnh của cùng cảnh và trả ngay camera, depth, point map và track, "
        "không cần tối ưu lặp như COLMAP. Ảnh được cắt patch bằng DINO, thêm token camera và token register, rồi hai mươi bốn lớp attention luân phiên "
        "giữa frame và global. Vì chạy một lượt nên rất nhanh và cho depth dày, nhưng cũng không ra mét. "
        "VGGT trả độ tin cậy conf; ta đổi sang khoảng 0 đến 1 bằng c_model bằng 1 trừ 1 chia conf."
    ),
)
pic(
    s,
    "paper_vggt_fig2.png",
    0.5,
    1.45,
    7.0,
    2.6,
    "Kiến trúc VGGT (bài báo VGGT, Hình 2)",
    alt="Kiến trúc VGGT: DINO, attention, camera head, DPT head",
)
txt(
    s,
    0.5,
    4.5,
    7.0,
    1.9,
    [
        [
            ("Đầu vào: ", {"bold": True, "color": TEAL}),
            ("N ảnh cùng cảnh, mạng trả camera, depth, point map trong một lượt.", {}),
        ],
        [("Ưu điểm: ", {"bold": True, "color": TEAL}), ("nhanh, dày, không tối ưu lặp.", {})],
        [("Hạn chế: ", {"bold": True, "color": RED}), ("đơn vị tuỳ ý, mỗi chunk có gốc riêng; chưa ra mét.", {})],
    ],
    size=15,
    bullet=True,
    space=6,
)
rect(s, 0.5, 6.1, 7.0, 0.8, fill=PALE)
txt(s, 0.65, 6.2, 2.4, 0.6, "Độ tin cậy dùng ở fusion:", size=13, color=MUTED, anchor=MSO_ANCHOR.MIDDLE)
eq(s, "cmodel", 3.3, 6.2, 2.4, 0.62)
pic(
    s,
    "pdf_fig_14.png",
    7.8,
    1.45,
    5.03,
    5.4,
    "VGGT theo bài báo, đề cương vẽ lại [ĐC Hình 14]",
    alt="Sơ đồ VGGT và các đầu ra camera, depth, point map, track",
)

s = new_slide(
    "Cơ sở lý thuyết 3: Sim(3), Umeyama và mốc scale",
    "A · Khái niệm",
    source="Umeyama, IEEE TPAMI 13(4), 1991; ĐC §15, Hình 16–17; pipeline/alignment/README.md",
    notes=(
        "Để ghép hai nhánh, ta cần đưa tâm camera VGGT về cùng hệ với COLMAP. Phép biến đổi đồng dạng Sim(3) gồm tỉ lệ s, xoay R và tịnh tiến t. "
        "Thuật toán Umeyama năm 1991 cho nghiệm dạng đóng bằng SVD của ma trận hiệp phương sai. Bước này chỉ cho cùng hệ toạ độ, chưa ra mét. "
        "Chỉ mốc scale ngoài đời mới đổi sang mét, bằng công thức (4) và (18). Hình dưới là ví dụ bốn camera quanh bàn ăn với s bằng 3,20."
    ),
)
pic(
    s,
    "pdf_fig_16.png",
    0.5,
    1.45,
    7.2,
    2.0,
    "Hai bước: Umeyama đưa về cùng hệ, mốc scale đổi sang mét [ĐC Hình 16]",
    alt="Sơ đồ hai bước Umeyama và mốc scale",
)
pic(
    s,
    "pdf_fig_17.png",
    0.5,
    3.95,
    7.2,
    2.7,
    "Ví dụ 4 camera quanh bàn ăn: s = 3,20, R = 90° (ví dụ ĐC Hình 17)",
    alt="Bốn camera VGGT và COLMAP quanh bàn ăn",
)
card(s, 8.0, 1.45, 4.83, 5.45, "Công thức", ["Căn Sim(3) (13)–(17):"], size=14)
eq(s, "umeyama1", 8.2, 2.2, 2.2, 0.55)
eq(s, "umeyama2", 8.15, 2.85, 4.55, 0.9)
txt(s, 8.15, 3.9, 4.5, 0.5, "Hệ số mét từ mốc (4) và áp lên điểm (18):", size=14)
eq(s, "sm", 8.2, 4.4, 1.9, 0.85)
eq(s, "xmet", 8.15, 5.35, 4.55, 0.7)
txt(
    s,
    8.15,
    6.15,
    4.5,
    0.65,
    "Umeyama chỉ cho cùng hệ toạ độ; chỉ mốc ngoài đời mới đổi sang mét.",
    size=12,
    color=MUTED,
    italic=True,
)

s = new_slide(
    "Dữ liệu sử dụng",
    "A · Khái niệm",
    source="README.md §4; ĐC Hình 4, 5, 13; Baruch và cs., ARKitScenes, NeurIPS 2021 (Hình 1); Straub và cs., Replica, 2019 (Hình 1)",
    notes=(
        "Dự án dùng ba nguồn dữ liệu với ba bộ số riêng, không trộn kết quả. Một: ARKitScenes, tập con có laser Faro làm ground truth, hiện có bốn mươi scene "
        "chia ba mươi chín trên venue, sáu validation và năm held-out theo venue với seed 42. Held-out chỉ chạy đúng một lần và không bao giờ dùng để chỉnh tham số. "
        "Hai: Replica, mười tám scene thực chất là mười ba không gian độc lập, dùng để test một lần. Ba: video tự thu sáu đến tám phòng, hiện chưa có."
    ),
)
table(
    s,
    0.5,
    1.45,
    [1.75, 1.75, 3.2],
    [
        ["Nguồn", "Vai trò", "Hiện có"],
        ["ARKitScenes", "train / val / held-out", "40 scene (29 / 6 / 5), RGB + laser Faro"],
        ["Replica", "test, chạy một lần", "18 scene = 13 không gian; thiếu nhãn phẳng"],
        ["Tự thu", "cross-domain, đo ngoài đời", "6–8 phòng [ĐC §5]: chưa có"],
    ],
    size=12,
    row_h=0.62,
)
pic(
    s,
    "paper_arkit_fig1.png",
    0.5,
    4.25,
    2.35,
    1.5,
    "ARKitScenes (bài báo, Hình 1)",
    alt="ARKitScenes: ảnh RGB và depth",
    cap_size=9,
)
pic(s, "paper_replica_fig1.png", 3.0, 4.25, 2.35, 1.5, "Replica (bài báo, Hình 1)", alt="Cảnh Replica", cap_size=9)
pic(
    s,
    "pdf_fig_05.png",
    5.5,
    4.25,
    2.45,
    1.5,
    "Tự thu: quỹ đạo quay [ĐC Hình 5]",
    alt="Quỹ đạo quay quanh phòng",
    cap_size=9,
)
txt(
    s,
    0.5,
    6.1,
    7.5,
    0.85,
    "Chia theo venue (nhà), không theo scene, để một nhà không nằm ở hai tập; held-out chỉ chạy một lần.",
    size=14,
    color=MUTED,
    italic=True,
)
pic(
    s,
    "pdf_fig_13.png",
    8.3,
    1.45,
    4.53,
    3.1,
    "Chia dữ liệu theo venue [ĐC Hình 13]",
    alt="Sơ đồ chia train, validation, held-out theo venue",
)
stat(s, 8.3, 5.0, 1.4, "29", "train", h=1.2, big_size=26)
stat(s, 9.88, 5.0, 1.4, "6", "validation", h=1.2, big_size=26)
stat(s, 11.46, 5.0, 1.37, "5", "held-out", h=1.2, big_size=26, color=AMBER)

s = new_slide(
    "Kiến trúc mô hình tổng thể",
    "A · Khái niệm",
    source="ĐC Hình 1 (Docs/TaiTao3D_Metric_3DMeph.pdf); pipeline/README.md",
    notes=(
        "Đây là kiến trúc tổng thể theo đề cương. Điện thoại chỉ thu video và hiển thị; máy GPU phía sau làm toàn bộ phần tính nặng, FastAPI đứng giữa quản lý job. "
        "Bên trong máy GPU có bảy bước từ A đến G: lọc keyframe, rồi hai nhánh độc lập là COLMAP và VGGT, căn bằng Umeyama và đổi mét, "
        "fusion sáu tín hiệu, plane gate và xuất file. Lưu ý phạm vi hiện tại: em mới làm lõi dòng lệnh; FastAPI và Unity thuộc mốc cuối M6."
    ),
)
pic(
    s,
    "pdf_fig_01.png",
    0.5,
    1.45,
    7.7,
    5.4,
    "Kiến trúc triển khai [ĐC Hình 1]",
    alt="Kiến trúc điện thoại, FastAPI, máy GPU với các bước A đến G",
)
card(
    s,
    8.5,
    1.45,
    4.33,
    3.55,
    "Lõi xử lý trên máy GPU",
    [
        "Hai nhánh độc lập: COLMAP (hình học) và VGGT (học sâu).",
        "Căn cùng hệ toạ độ, đổi sang mét bằng một mốc.",
        "Ghép theo trọng số 6 tín hiệu, rồi làm phẳng có cổng.",
        "Các stage chỉ giao tiếp qua file.",
    ],
    size=14,
    bullet=True,
)
card(
    s,
    8.5,
    5.2,
    4.33,
    1.65,
    "Phạm vi hiện tại",
    ["Đã làm: lõi dòng lệnh chạy 1 scene. Chưa làm: FastAPI, Unity (mốc M6)."],
    size=14,
    accent=AMBER,
)

s = new_slide(
    "Phương pháp đề xuất: lai hình học và học sâu",
    "A · Khái niệm",
    source="ĐC §16, Hình 18 (Docs/TaiTao3D_Metric_3DMeph.pdf); pipeline/fusion/README.md",
    notes=(
        "Phương pháp đề xuất có ba ý. Một, giữ hai nhánh độc lập: COLMAP chính xác nhưng thưa, VGGT dày và nhanh nhưng có nhiễu. "
        "Hai, với mỗi điểm, mỗi view nhìn thấy điểm đó có một trọng số được tính từ sáu tín hiệu thuộc ba nhóm: độ tin cậy mô hình, hình học đa view, chất lượng ảnh. "
        "Hình bên trái là sơ đồ trong đề cương. Ba, plane gate kéo điểm về mặt phẳng tường, sàn, trần nhưng chỉ khi đủ bốn điều kiện, để không phá đồ vật không phẳng."
    ),
)
pic(
    s,
    "pdf_fig_18.png",
    0.5,
    1.45,
    7.7,
    5.4,
    "Từ sáu tín hiệu đến một trọng số chuẩn hóa mỗi view [ĐC Hình 18]",
    alt="Sáu tín hiệu ba nhóm nhân thành trọng số w rồi chuẩn hóa",
)
card(
    s,
    8.5,
    1.45,
    4.33,
    1.7,
    "1. Hai nhánh độc lập",
    ["COLMAP chính xác nhưng thưa; VGGT dày nhanh nhưng nhiễu."],
    size=14,
)
card(
    s,
    8.5,
    3.3,
    4.33,
    1.7,
    "2. Sáu tín hiệu → trọng số",
    ["Tín hiệu mô hình, hình học đa view, chất lượng ảnh nhân lại thành w."],
    size=14,
)
card(
    s,
    8.5,
    5.15,
    4.33,
    1.7,
    "3. Plane gate",
    ["Kéo điểm về tường, sàn, trần chỉ khi đủ bốn điều kiện."],
    size=14,
    accent=AMBER,
)

s = new_slide(
    "Vì sao chọn hướng này",
    "A · Khái niệm",
    source="ĐC §2, Hình 26, 28, 29 (Docs/TaiTao3D_Metric_3DMeph.pdf); AGENTS.md §6; số đo lấy từ kết quả scene dev",
    notes=(
        "Vì sao không dùng một phương pháp đơn lẻ? COLMAP thuần cho hình học tốt nhưng thưa, có thể đứt chuỗi và chạy lâu: MVS cho scene dev mất khoảng 12 phút. "
        "VGGT thuần chạy khoảng hai phút nhưng không ra mét và có nhiễu. Depth một mắt kiểu UniDepthV2 có sẵn mét nhưng không có ràng buộc đa view; "
        "em để nó làm baseline B2 mở rộng. GGPT dùng điểm thưa làm mỏ neo cho nhánh dense; em chọn để hai nhánh độc lập rồi ghép có trọng số, "
        "để biết rõ nhánh nào sai ở đâu. Cuối cùng mốc scale lấy từ một đoạn đo ngoài đời, không dùng pose ground truth để suy ra scale."
    ),
)
rows = [
    ["Hướng", "Ra mét?", "Điểm mạnh", "Hạn chế"],
    ["COLMAP thuần (B0)", "Không", "hình học chính xác", f"thưa; MVS {vn(MVS['seconds'] / 60, 0)} phút/80 ảnh"],
    ["VGGT thuần (B1)", "Không", "nhanh, dày", f"{vn(VGGT['seconds'] / 60, 1)} phút; có nhiễu"],
    ["Depth đơn mắt (B2)", "Có", "sẵn thang mét", "không ràng buộc đa view"],
    ["GGPT", "Không", "điểm thưa neo nhánh dense", "một nhánh làm chủ"],
    ["3DMeph (đề xuất)", "Có (mốc)", "ghép hai nhánh, có trọng số", "phụ thuộc mốc và các ngưỡng"],
]
table(s, 0.5, 1.45, [1.9, 0.95, 2.35, 2.45], rows, size=12, row_h=0.56)
txt(
    s,
    0.5,
    5.0,
    7.65,
    1.9,
    [
        [
            ("Hai nhánh độc lập, ghép có trọng số: ", {"bold": True}),
            ("biết rõ nguồn lỗi, thay vì để nhánh này sửa nhánh kia (ĐC Hình 29).", {}),
        ],
        [("Mốc 1 đoạn, không dùng pose GT: ", {"bold": True}), ("tránh lộ scale từ dữ liệu đánh giá.", {})],
        [
            ("Gate có điều kiện: ", {"bold": True}),
            ("chỉ kéo điểm đủ bốn điều kiện để không phá đồ vật không phẳng.", {}),
        ],
    ],
    size=14,
    bullet=True,
    space=5,
)
pic(
    s,
    "pdf_fig_29.png",
    8.45,
    1.45,
    4.38,
    2.3,
    "GGPT so với 3DMeph [ĐC Hình 29]",
    alt="So sánh GGPT với 3DMeph hai nhánh độc lập",
)
pic(
    s,
    "pdf_fig_26.png",
    8.45,
    4.2,
    4.38,
    1.6,
    "Chuỗi cấu hình B0 → Đề xuất [ĐC Hình 26]",
    alt="Chuỗi B0, B1, B2, B3, đề xuất và hai ablation",
)
txt(
    s,
    8.45,
    6.2,
    4.38,
    0.7,
    "Mỗi bậc thêm đúng một module, nên ablation chỉ ra từng phần đóng góp bao nhiêu.",
    size=12,
    color=MUTED,
    italic=True,
)

# =====================================================================
# B. MỤC TIÊU (13–14)  C. KẾ HOẠCH (15)
# =====================================================================
s = new_slide(
    "Mục tiêu cuối cùng: mặt thực tế",
    "B · Mục tiêu",
    source="README.md §1; ĐC §19, Hình 25 (giao diện minh họa, số minh họa; ứng dụng chưa làm)",
    notes=(
        "Về mặt thực tế, mục tiêu là ai cũng đo được một căn phòng bằng điện thoại thường, không cần máy LiDAR đắt tiền hay thước dây dài. "
        "Người dùng quay một đến hai phút, chọn một đoạn mốc dài một đến hai mét một lần, rồi chạm hai điểm trên mô hình để đọc khoảng cách. "
        "Ảnh bên phải là giao diện minh họa của đề cương với số minh họa. Ứng dụng này thuộc mốc M6, hiện em mới làm lõi dòng lệnh, đo hai điểm bằng lệnh measure."
    ),
)
for i, (t1, t2) in enumerate(
    [
        ("Không cần thiết bị đặc biệt", "Chỉ cần video từ điện thoại thường, không cần LiDAR hay thước dây dài."),
        ("Một lần neo, đo nhiều lần", "Chọn một đoạn mốc 1–2 m một lần; sau đó đo mọi khoảng cách khác trên mô hình."),
        ("Đủ chính xác cho phòng ở", "Mục tiêu sai số trung vị dưới 5 cm cho phòng 3–5 m."),
        ("Hiện trạng", "Đo hai điểm đã chạy bằng dòng lệnh; ứng dụng điện thoại (FastAPI + Unity) thuộc mốc M6."),
    ]
):
    y = 1.5 + i * 1.35
    rect(s, 0.5, y, 7.0, 1.2, fill=PALE)
    rect(s, 0.65, y + 0.25, 0.7, 0.7, fill=AMBER if i == 3 else TEAL, line=None, shape=MSO_SHAPE.OVAL)
    txt(
        s,
        0.65,
        y + 0.25,
        0.7,
        0.7,
        str(i + 1),
        size=22,
        bold=True,
        color=WHITE,
        font=HEAD,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        margin=0,
    )
    txt(s, 1.55, y + 0.08, 5.8, 0.38, t1, size=17, bold=True, font=HEAD)
    txt(s, 1.55, y + 0.5, 5.8, 0.68, t2, size=13, color=MUTED)
pic(
    s,
    "pdf_fig_25.png",
    7.9,
    1.45,
    4.93,
    5.4,
    "Giao diện đo minh họa, số minh họa [ĐC Hình 25]",
    alt="Giao diện điện thoại hiển thị mô hình phòng và khoảng cách giữa hai điểm",
)

s = new_slide(
    "Mục tiêu cuối cùng: mặt khoa học",
    "B · Mục tiêu",
    source="ĐC §20–21 (Docs/TaiTao3D_Metric_3DMeph.pdf), Hình 26; pipeline/eval/README.md",
    notes=(
        "Về mặt khoa học có ba mục tiêu. Một, sai số trung vị chiều dài nhỏ hơn 5 cm, đo bằng MAE, median, MAPE và tỉ lệ đoạn dưới 5 cm. "
        "Hai, giảm mười lăm đến hai mươi phần trăm sai số mặt phẳng mà F-score không giảm đáng kể; mức cải thiện tính theo công thức (31). "
        "Ba, chứng minh từng thành phần bằng ablation: chuỗi cấu hình B0, B1, B2, B3 rồi đề xuất, mỗi bậc thêm đúng một module. "
        "Nếu không đạt thì báo số thật và phân tích nguyên nhân."
    ),
)
card(
    s,
    0.5,
    1.45,
    4.0,
    2.55,
    "1. Độ chính xác chiều dài",
    ["Median < 5 cm cho phòng 3–5 m.", "Đo bằng MAE, median, MAPE, % đoạn dưới 5 cm."],
    size=14,
    bullet=True,
)
card(
    s,
    4.67,
    1.45,
    4.0,
    2.55,
    "2. Chất lượng mặt phẳng",
    ["Giảm 15–20% sai số mặt phẳng, F-score không giảm đáng kể.", "Mức cải thiện theo (31):"],
    size=14,
    bullet=True,
)
eq(s, "delta", 4.85, 3.35, 3.6, 0.55)
card(
    s,
    8.83,
    1.45,
    4.0,
    2.55,
    "3. Chứng minh từng phần",
    ["Ablation: bỏ tín hiệu chất lượng ảnh; ép mọi điểm về mặt phẳng.", "Không đạt thì báo số thật."],
    size=14,
    bullet=True,
    accent=AMBER,
)
pic(
    s,
    "pdf_fig_26.png",
    0.5,
    4.3,
    8.4,
    2.5,
    "Chuỗi cấu hình B0 → Đề xuất và hai ablation [ĐC Hình 26]",
    alt="Chuỗi cấu hình B0, B1, B2, B3, đề xuất",
)
txt(
    s,
    9.2,
    4.4,
    3.63,
    2.4,
    [
        "B0: COLMAP thuần.",
        "B1: VGGT thuần.",
        "B2: thêm depth mét (mở rộng).",
        "B3: fusion không gate.",
        "Đề xuất: fusion + plane gate.",
    ],
    size=14,
    bullet=True,
    space=5,
)

s = new_slide(
    "Kế hoạch đặt ra và tiến độ",
    "C · Kế hoạch",
    source="README.md §7; WORKING_LOG.md bảng mốc (06/11/2026); ĐC §25, Hình 30",
    notes=(
        "Kế hoạch chia thành các mốc. M0a dựng môi trường, cấu hình và lõi toán: xong. M0b chọn và chia scene, tải dữ liệu, căn Faro, chấm mốc và đoạn test: xong cho scene dev. "
        "M1 chạy cả chín stage trên một scene: xong có điều kiện. M2 khoá ngưỡng keyframe trên sáu scene Validation: gần xong. "
        "M3 đánh giá và ablation trên một scene: đang làm. M4 nhiều scene ARKit, M5 Replica và tự thu, M6 ứng dụng và báo cáo: chưa bắt đầu. "
        "Đề cương chỉ nêu tổng thời gian và ưu tiên tuần đầu là một scene chạy xuyên suốt, chưa train confidence head; cách chia tuần là ước tính."
    ),
)
ms = [
    ("M0a", "Môi trường, config, lõi toán, README", "Xong", GREEN),
    ("M0b", "Chia scene, tải dữ liệu, căn Faro, chấm mốc và 12 đoạn test", "Xong (scene dev)", GREEN),
    ("M1", "Chín stage chạy trên scene 42444738", "Xong có điều kiện", GREEN),
    ("M2", "Khoá ngưỡng keyframe trên 6 Validation", "Gần xong", AMBER),
    ("M3", "Eval đủ chỉ số, B0/B1/B3/đề xuất/ablation", "Đang làm", AMBER),
    ("M4", "Nhiều scene ARKit; held-out chạy một lần", "Chưa", MUTED),
    ("M5", "Replica và video tự thu", "Chưa", MUTED),
    ("M6", "FastAPI + Unity, báo cáo", "Chưa", MUTED),
]
for i, (m, d, st, col) in enumerate(ms):
    y = 1.45 + i * 0.66
    rect(s, 0.5, y, 8.3, 0.58, fill=PALE)
    txt(s, 0.6, y, 0.8, 0.58, m, size=17, bold=True, color=TEAL, font=HEAD, anchor=MSO_ANCHOR.MIDDLE)
    txt(s, 1.45, y, 5.1, 0.58, d, size=13, anchor=MSO_ANCHOR.MIDDLE)
    pill(s, 6.65, y + 0.14, 2.05, st, col, h=0.3, size=11)
pic(
    s,
    "pdf_fig_30.png",
    9.1,
    1.45,
    3.73,
    1.3,
    "Ưu tiên tuần đầu [ĐC Hình 30]",
    alt="Một scene chạy xuyên suốt từ video đến số đo",
    cap_size=9,
)
card(
    s,
    9.1,
    3.35,
    3.73,
    3.5,
    "Cách chia tuần",
    [
        "Đề cương chỉ nêu tổng 9 tuần và ưu tiên tuần đầu: một scene chạy xuyên suốt, chưa train confidence head.",
        "Cách chia tuần ở trên là ước tính của em.",
    ],
    size=13,
    accent=AMBER,
)

# =====================================================================
# D. CÁCH THỰC HIỆN (16–24)
# =====================================================================
s = new_slide(
    "Quy trình: chín stage, giao tiếp qua file",
    "D · Cách thực hiện",
    source="pipeline/README.md; evaluation/logs/run_meta.json của scene 42444738 (số giây đo thật)",
    notes=(
        "Quy trình gồm chín stage chạy bằng một lệnh: keyframe, sfm, mvs, vggt, align, fuse, gate, export, eval. Các stage chỉ giao tiếp qua file, "
        "vì GPU chỉ 8 GB nên COLMAP và VGGT không thể nằm trong bộ nhớ cùng lúc. Mỗi stage ghi run_meta.json gồm thời gian, VRAM đỉnh, hash cấu hình và mã lỗi. "
        "Các số giây ở hàng dưới đo thật trên scene dev: MVS tốn nhiều nhất, khoảng mười hai phút; các bước ghép và làm phẳng chỉ vài giây. "
        "Stage eval đang trong mốc M3, nên có viền vàng."
    ),
)
stages = [
    ("keyframe", "frames/*.jpg\ncamera.json"),
    ("sfm", "sparse/0\nobservations"),
    ("mvs", "depth map\nfused.ply"),
    ("vggt", "vggt_raw.npz\ntheo chunk"),
    ("align", "sim3.json\nscale.json"),
    ("fuse", "fused_points\n(w_k)"),
    ("gate", "refined_points"),
    ("export", "model.glb"),
    ("eval", "metrics.csv"),
]
bw, gap = 1.22, 0.167
for i, (nm, out) in enumerate(stages):
    x = 0.5 + i * (bw + gap)
    b = rect(
        s, x, 1.55, bw, 0.7, fill=TEAL if nm != "eval" else WHITE, line=TEAL if nm != "eval" else AMBER, radius=0.15
    )
    if nm == "eval":
        b.line.width = Pt(2.5)
    txt(
        s,
        x,
        1.55,
        bw,
        0.7,
        nm,
        size=15,
        bold=True,
        color=WHITE if nm != "eval" else INK,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
        margin=0,
    )
    txt(
        s,
        x - 0.02,
        2.3,
        bw + 0.04,
        0.62,
        out.split("\n"),
        size=11,
        color=MUTED,
        align=PP_ALIGN.CENTER,
        space=0,
        margin=0,
    )
    sec = RUN.get(nm, {}).get("seconds")
    label = "—" if sec is None else (f"{vn(sec, 1)} s" if sec < 100 else f"{vi(sec)} s")
    txt(
        s,
        x,
        3.0,
        bw,
        0.3,
        label,
        size=13,
        bold=True,
        color=AMBER if nm == "mvs" else INK,
        align=PP_ALIGN.CENTER,
        margin=0,
    )
txt(
    s,
    0.5,
    3.35,
    12.3,
    0.3,
    "Thời gian chạy thật trên scene dev 42444738 (eval chạy được nhưng còn hoàn thiện ở M3).",
    size=11,
    color=MUTED,
    italic=True,
)
card(
    s,
    0.5,
    3.85,
    4.0,
    3.0,
    "Hai nhánh tách biệt",
    ["Nhánh 1: sfm → mvs (COLMAP).", "Nhánh 2: vggt (theo chunk).", "Gặp nhau ở align rồi fuse."],
    size=14,
    bullet=True,
)
card(
    s,
    4.67,
    3.85,
    4.0,
    3.0,
    "Vì sao qua file",
    ["GPU 8 GB không giữ VGGT và COLMAP cùng lúc.", "Chạy lại riêng từng stage mà không làm lại cả chuỗi."],
    size=14,
    bullet=True,
)
card(
    s,
    8.83,
    3.85,
    4.0,
    3.0,
    "Ghi vết mỗi stage",
    ["run_meta.json: thời gian, VRAM đỉnh, hash config, mã lỗi.", "Lỗi có mã rõ: E_TOO_FEW_KEYFRAMES, E_SFM_FAILED."],
    size=14,
    bullet=True,
    accent=AMBER,
)

kst = KF
s = new_slide(
    "Keyframe: lọc ảnh sạch trước khi dựng",
    "D · Cách thực hiện",
    source="pipeline/keyframe/README.md; ĐC Hình 6 (số ví dụ ĐC); run_meta.json scene 42444738",
    notes=(
        f"Stage đầu tiên chọn ảnh. Từ video lấy hai khung mỗi giây, xoay ảnh về đứng theo hướng sky_direction của ARKit, rồi lọc: bỏ ảnh mờ bằng q_blur theo công thức (3), "
        f"đo độ phơi sáng theo (20), và bỏ ảnh trùng hoặc đứt kết nối theo overlap (1). Lý do: ảnh mờ làm SfM lệch hoặc không đăng ký được, ảnh trùng chỉ tốn thời gian. "
        f"Trên scene dev: {vi(kst['n_frames'])} khung, {kst['n_candidates']} ứng viên, sau lọc mờ còn {kst['n_after_blur']}, sau lọc trùng còn {kst['n_after_overlap']}; "
        f"sau SfM chọn lại {SFM['n_keyframes']} keyframe. Hình trên là ví dụ trong đề cương với con số 72, chỉ minh họa."
    ),
)
pic(
    s,
    "pdf_fig_06.png",
    0.5,
    1.45,
    7.6,
    2.5,
    "Từ video đến keyframe (số ví dụ của ĐC, Hình 6)",
    alt="Sơ đồ từ video 90 giây đến 72 keyframe",
)
txt(s, 0.5, 4.45, 3.6, 0.35, "Độ mờ (3) và phơi sáng (20):", size=13, bold=True, color=TEAL)
eq(s, "qblur", 0.5, 4.85, 7.6, 0.75)
eq(s, "qexp", 0.5, 5.7, 5.8, 0.75)
txt(
    s,
    0.5,
    6.5,
    7.6,
    0.45,
    "Overlap giữa hai keyframe liên tiếp (1): mục tiêu 60–80% theo đề cương.",
    size=12,
    color=MUTED,
    italic=True,
)
stat(s, 8.4, 1.45, 2.1, vi(kst["n_frames"]), "khung video thô", big_size=24, h=1.15)
stat(s, 10.73, 1.45, 2.1, str(kst["n_candidates"]), "ứng viên (2 fps)", big_size=24, h=1.15)
stat(s, 8.4, 2.75, 2.1, str(kst["n_after_blur"]), f"sau lọc mờ (q_blur ≥ {vn(kst['q_drop'], 2)})", big_size=24, h=1.15)
stat(s, 10.73, 2.75, 2.1, str(kst["n_after_overlap"]), "sau lọc trùng", big_size=24, h=1.15)
stat(
    s,
    8.4,
    4.05,
    4.43,
    str(SFM["n_keyframes"]),
    "keyframe cuối, chọn từ ảnh đã đăng ký SfM (40–80)",
    big_size=28,
    h=1.2,
    color=AMBER,
)
card(s, 8.4, 5.45, 4.43, 1.4, "Vì sao lọc", ["Ảnh mờ và trùng làm SfM lệch hoặc không đăng ký."], size=13)

s = new_slide(
    "COLMAP: SfM + MVS cho hình học và tín hiệu",
    "D · Cách thực hiện",
    source="pipeline/colmap/README.md; sfm_result.json, mvs_result.json; WORKING_LOG.md (lệch #39–#41)",
    notes=(
        f"COLMAP chạy hai phần. SfM trên {SFM['n_images']} ảnh ứng viên đăng ký được {SFM['n_registered']} ảnh, {vn(SFM['registered_ratio'] * 100, 1)} phần trăm, "
        f"sai số chiếu lại trung bình {vn(SFM['mean_reproj_error_px'], 2)} pixel, mất {vn(SFM['seconds'], 0)} giây. MVS cho {MVS['n_depth_maps']} depth map và "
        f"{vi(MVS['n_fused_points'])} điểm dày trong {vn(MVS['seconds'], 0)} giây. Trong lần chạy đầu ở mốc M1, SfM chỉ đăng ký 83,9 phần trăm ảnh; "
        "em đổi sang tập ứng viên dày kèm khớp exhaustive để vượt ngưỡng 90 phần trăm. Mục đích của COLMAP trong dự án: cho camera và điểm dày làm gốc hình học, "
        "đồng thời cho hai tín hiệu e_reproj và σ_depth vào fusion. Ảnh bên trái là mây điểm dày đã đổi sang mét, vẽ từ trên xuống."
    ),
)
pic(
    s,
    "res_b0_top.png",
    0.5,
    1.45,
    6.4,
    5.35,
    "Mây điểm dày COLMAP đã đổi sang mét (B0), nhìn từ trên xuống",
    alt="Mây điểm màu của phòng nhìn từ trên xuống",
)
stat(
    s,
    7.2,
    1.45,
    2.7,
    f"{SFM['n_registered']}/{SFM['n_images']}",
    f"ảnh đăng ký SfM ({vn(SFM['registered_ratio'] * 100, 1)}%)",
    big_size=26,
    h=1.2,
)
stat(s, 10.13, 1.45, 2.7, f"{vn(SFM['mean_reproj_error_px'], 2)} px", "sai số chiếu lại TB", big_size=26, h=1.2)
stat(s, 7.2, 2.8, 2.7, vi(MVS["n_fused_points"]), f"điểm dày MVS ({MVS['n_depth_maps']} depth map)", big_size=26, h=1.2)
stat(
    s,
    10.13,
    2.8,
    2.7,
    f"{vi(SFM['seconds'])} + {vi(MVS['seconds'])} s",
    "thời gian SfM + MVS",
    big_size=22,
    h=1.2,
    color=AMBER,
)
card(
    s,
    7.2,
    4.15,
    5.63,
    2.7,
    "Vì sao chạy COLMAP",
    [
        "Cho camera và điểm dày làm gốc hình học.",
        "Sinh hai tín hiệu: e_reproj (thưa) và σ_depth (dày).",
        "Lần đầu (M1) chỉ đăng ký 83,9% ảnh; đổi sang tập ứng viên dày + khớp exhaustive để vượt 90%.",
    ],
    size=13,
    bullet=True,
)

s = new_slide(
    "VGGT theo chunk: nhanh và dày",
    "D · Cách thực hiện",
    source="pipeline/vggt/README.md; vggt_result.json; ĐC Hình 7 (ví dụ 72 keyframe, ĐC)",
    notes=(
        f"VGGT không nhét hết ảnh một lần vì GPU chỉ 8 GB. Em chia keyframe thành các chunk 12 ảnh, hai chunk liền kề gối nhau 2 ảnh, "
        f"số chunk tính theo công thức (2). Ví dụ đề cương: 72 ảnh cho 7 chunk. Trên scene dev: {VGGT['n_keyframes']} keyframe cho {VGGT['n_chunks']} chunk, "
        f"chạy {vn(VGGT['seconds'], 1)} giây, VRAM đỉnh {vi(VGGT['peak_vram_mib'])} MiB, dưới 8.188 MiB của GPU. Lần đầu em để aggregator ở fp32 thì đỉnh 9.487 MiB và hết bộ nhớ ở chunk 10; "
        "chuyển aggregator sang bf16 thì vừa. Mỗi chunk có gốc toạ độ riêng nên phải căn từng chunk vào COLMAP ở bước sau."
    ),
)
pic(
    s,
    "pdf_fig_07.png",
    0.5,
    1.45,
    7.6,
    1.8,
    "Các chunk 12 ảnh, hai chunk liền kề gối nhau 2 ảnh (ví dụ ĐC Hình 7)",
    alt="Bảy chunk 12 ảnh gối nhau 2 ảnh",
)
txt(s, 0.5, 3.75, 4.0, 0.35, "Số chunk (2):", size=13, bold=True, color=TEAL)
eq(s, "nchunk", 0.5, 4.15, 3.2, 1.0)
txt(
    s,
    0.5,
    5.3,
    7.6,
    1.6,
    [
        "c = 12 ảnh mỗi chunk, o = 2 ảnh gối: ảnh gối để kiểm tra nhất quán.",
        "Aggregator bf16 để vừa 8 GB (fp32: đỉnh 9.487 MiB, hết bộ nhớ ở chunk 10).",
        "Mỗi chunk có gốc riêng nên căn từng chunk vào COLMAP.",
    ],
    size=14,
    bullet=True,
    space=4,
)
stat(s, 8.4, 1.45, 2.1, str(VGGT["n_chunks"]), f"chunk cho {VGGT['n_keyframes']} keyframe", big_size=28, h=1.4)
stat(s, 10.73, 1.45, 2.1, f"{vn(VGGT['seconds'], 1)} s", "thời gian chạy", big_size=26, h=1.4)
stat(
    s,
    8.4,
    3.05,
    4.43,
    f"{vi(VGGT['peak_vram_mib'])} MiB",
    "VRAM đỉnh (GPU có 8.188 MiB)",
    big_size=30,
    h=1.4,
    color=AMBER,
)
card(
    s,
    8.4,
    4.65,
    4.43,
    2.2,
    "Vì sao chọn VGGT",
    ["Một lượt feed-forward cho depth dày và camera, nhanh hơn MVS nhiều lần."],
    size=14,
)

s = new_slide(
    "Căn tỉ lệ: Sim(3) vào COLMAP, rồi đổi sang mét",
    "D · Cách thực hiện",
    source="pipeline/alignment/README.md; scale.json, align_result.json, scale_anchor.json; ĐC Hình 8 (ví dụ ĐC)",
    notes=(
        f"Căn tỉ lệ có hai việc. Một, đưa từng chunk VGGT về hệ COLMAP bằng Sim(3). Đề cương dùng tâm camera với RANSAC và Umeyama; "
        "trên scene dev tâm camera của nhiều chunk chỉ trải dưới 0,6 mét nên căn kém điều kiện, em đã đổi sang cách lấy xoay từ hướng camera, tỉ lệ từ điểm, và tịnh tiến từ tâm camera. "
        "Đây là chỗ lệch có chủ ý so với đề cương, đã được ghi trong nhật ký. Hai, đổi sang mét bằng một đoạn mốc. "
        f"Mốc của scene dev là chiều dài tủ trắng {vn(SCALE['L_real'], 4)} m đo trên laser Faro; trong mô hình dài {vn(SCALE['L_model'], 4)} đơn vị COLMAP, "
        f"nên s_m bằng {vn(SCALE['s_m'], 4)} mét trên đơn vị. Cả {ALIGN['n_accepted']} trên {ALIGN['n_chunks']} chunk được nhận."
    ),
)
pic(
    s,
    "pdf_fig_08.png",
    0.5,
    1.45,
    4.6,
    4.9,
    "Một mốc 1,50 m và các đoạn test (ví dụ ĐC Hình 8)",
    alt="Mặt bằng phòng với mốc scale và đoạn test",
)
card(
    s,
    5.35,
    1.45,
    3.7,
    2.45,
    "Cách chọn mốc",
    ["Một đoạn 1–2 m, dễ thấy, không trên gương hoặc kính.", "Mốc bị loại khỏi chỉ số test [ĐC §8.1]."],
    size=13,
    bullet=True,
)
card(
    s,
    5.35,
    4.05,
    3.7,
    2.8,
    "Chỗ lệch có chủ ý",
    [
        "Đề cương căn bằng tâm camera. Trên scene dev tâm camera nhiều chunk trải < 0,6 m nên căn kém điều kiện.",
        "Em đổi sang xoay từ hướng camera, tỉ lệ từ điểm (orientation_depth).",
    ],
    size=12,
    accent=AMBER,
    bullet=True,
)
stat(s, 9.3, 1.45, 3.53, f"{vn(SCALE['L_real'], 4)} m", "mốc S06 (tủ trắng), đo trên laser Faro", big_size=24, h=1.3)
stat(s, 9.3, 2.9, 3.53, f"{vn(SCALE['L_model'], 4)} đv", "chiều dài đoạn đó trong mô hình COLMAP", big_size=24, h=1.3)
stat(s, 9.3, 4.35, 3.53, f"s_m = {vn(SCALE['s_m'], 4)}", "mét trên mỗi đơn vị COLMAP", big_size=24, h=1.3, color=AMBER)
stat(
    s, 9.3, 5.8, 3.53, f"{ALIGN['n_accepted']}/{ALIGN['n_chunks']}", "chunk VGGT được nhận khi căn", big_size=24, h=1.05
)

s = new_slide(
    "Confidence fusion: ghép theo sáu tín hiệu",
    "D · Cách thực hiện",
    source="pipeline/fusion/README.md; ĐC §16, Hình 19; fusion_result.json scene 42444738",
    notes=(
        f"Fusion trả lời câu hỏi: một điểm nhiều view cùng thấy thì tin view nào. Mỗi cặp view i và điểm k có trọng số w theo công thức (19), "
        "là tích sáu thừa số: độ tin cậy mô hình, hai tín hiệu hình học được đổi bằng hàm mũ, và ba tín hiệu chất lượng ảnh. Tích nên một tín hiệu rất thấp hạ cả view. "
        "Sau đó chuẩn hoá theo (22) và lấy trung bình có trọng số các vị trí. Hình ví dụ của đề cương: ảnh C mờ và phản chiếu bị hạ phiếu xuống dưới một phần trăm, "
        "nhưng thuật toán không xoá ảnh. "
        f"Trên scene dev: {vi(FUS['n_points_fused'])} điểm, w_k trung vị {vn(FUS['w_k_percentiles']['50'], 2)}, chỉ {vn(FUS['frac_w_k_above_tau_w'] * 100, 1)} phần trăm điểm có w_k lớn hơn ngưỡng tau_w. "
        f"Lệch VGGT so với COLMAP theo cặp: trung vị {vn(FUS['vggt_vs_colmap_pair_cm']['median'], 1)} cm; đây là lệch giữa hai phương pháp, chưa phải sai số so với ground truth."
    ),
)
pic(
    s,
    "pdf_fig_19.png",
    0.5,
    1.45,
    6.5,
    2.4,
    "Ba khung nhìn điểm k trên mép bàn: ảnh C mờ bị hạ phiếu (ví dụ ĐC Hình 19)",
    alt="Ba khung hình A, B, C và trọng số chuẩn hóa",
)
eq(s, "w", 0.5, 4.2, 6.5, 0.45)
eq(s, "wtilde", 0.5, 4.8, 6.5, 0.9)
eq(s, "wk", 0.5, 5.75, 2.4, 0.5)
txt(
    s,
    3.1,
    5.75,
    3.9,
    0.55,
    "w_k: độ tin cậy của điểm sau khi ghép, chuyển sang cổng.",
    size=12,
    color=MUTED,
    italic=True,
    anchor=MSO_ANCHOR.MIDDLE,
)
txt(s, 0.5, 6.4, 6.5, 0.55, "Tích sáu thừa số: một tín hiệu rất thấp hạ cả view; view có w ≈ 0 không bị xoá.", size=13)
pic(
    s,
    "res_wk_top.png",
    7.3,
    1.45,
    5.53,
    4.45,
    "Bản đồ w_k trên mô hình scene dev (nhìn từ trên xuống)",
    alt="Mây điểm tô màu theo w_k",
)
txt(
    s,
    7.3,
    6.3,
    5.53,
    0.65,
    f"{vi(FUS['n_points_fused'])} điểm; w_k trung vị {vn(FUS['w_k_percentiles']['50'], 2)}; chỉ {vn(FUS['frac_w_k_above_tau_w'] * 100, 1)}% điểm có w_k > τ_w.",
    size=13,
    bold=True,
    color=TEAL,
)

pc = GATE["condition_pass_fraction"]
s = new_slide(
    "Plane-gated filter: làm phẳng có điều kiện",
    "D · Cách thực hiện",
    source="pipeline/plane_gate/README.md; ĐC §17, Hình 20; gate_result.json scene 42444738",
    notes=(
        f"Plane gate kéo điểm về mặt phẳng tường, sàn, trần để mô hình phẳng hơn, nhưng không phá đồ vật. RANSAC tìm mặt phẳng; mỗi điểm qua cổng (24) khi đủ bốn điều kiện: "
        "gần mặt phẳng, pháp tuyến cục bộ cùng hướng, thuộc loại cấu trúc, và độ tin cậy w_k đủ cao. Điểm đạt được kéo một phần theo hệ số alpha (25); điểm không đạt giữ nguyên. "
        f"Kết quả thật trên scene dev: {GATE['n_planes']} mặt phẳng, chỉ {GATE['n_gate_pass']} trên {vi(GATE['n_points'])} điểm, tức {vn(GATE['frac_gate_pass'] * 100, 2)} phần trăm, qua cổng. "
        f"Điều kiện chặn chủ yếu là w_k lớn hơn ngưỡng: chỉ {vn(pc['w_k>tau_w'] * 100, 1)} phần trăm điểm đạt, và điều kiện pháp tuyến {vn(pc['theta<tau_n'] * 100, 1)} phần trăm. "
        "Nghĩa là cổng đang quá chặt nên hầu như chưa làm phẳng được gì; đây là việc cần xem lại, dùng validation, không dùng held-out."
    ),
)
pic(
    s,
    "pdf_fig_20.png",
    0.5,
    1.45,
    6.2,
    3.55,
    "Cổng bốn điều kiện quyết định điểm nào được kéo (ngưỡng ví dụ, ĐC Hình 20)",
    alt="Sơ đồ cổng bốn điều kiện AND",
)
eq(s, "gate", 0.5, 5.3, 6.2, 0.5)
eq(s, "proj", 0.5, 5.95, 4.6, 0.5)
txt(
    s,
    0.5,
    6.5,
    6.2,
    0.45,
    "Điểm không qua cổng giữ nguyên (g = 0), vẫn nằm trong kết quả.",
    size=12,
    color=MUTED,
    italic=True,
)
pic(
    s,
    "res_planes_gate.png",
    7.0,
    1.45,
    5.83,
    2.55,
    "Mặt phẳng RANSAC (trái) và điểm qua cổng (phải), scene dev",
    alt="Hai bản đồ: mặt phẳng và điểm qua cổng",
)
stat(s, 7.0, 4.3, 1.85, f"{GATE['n_planes']}", "mặt phẳng RANSAC", big_size=24, h=1.15)
stat(
    s,
    9.0,
    4.3,
    1.85,
    f"{vn(GATE['frac_gate_pass'] * 100, 2)}%",
    f"qua cổng ({GATE['n_gate_pass']} điểm)",
    big_size=22,
    h=1.15,
    color=RED,
)
stat(s, 11.0, 4.3, 1.83, f"{vn(GATE['displacement_cm']['max'], 1)} cm", "dịch tối đa", big_size=22, h=1.15)
txt(
    s,
    7.0,
    5.65,
    5.83,
    1.3,
    [
        [
            ("Tỉ lệ điểm qua từng điều kiện: ", {"bold": True}),
            (
                f"r < τ_r {vn(pc['r<tau_r'] * 100, 1)}%; θ < τ_n {vn(pc['theta<tau_n'] * 100, 1)}%; w_k > τ_w {vn(pc['w_k>tau_w'] * 100, 1)}%.",
                {},
            ),
        ],
        [("Nút cổ chai là w_k và pháp tuyến, nên cổng đang quá chặt.", {"color": RED, "bold": True})],
    ],
    size=13,
    space=4,
)

s = new_slide(
    "Xuất mô hình GLB và đo hai điểm",
    "D · Cách thực hiện",
    source="pipeline/export/README.md; ĐC §19 (công thức (30)); model.glb scene 42444738",
    notes=(
        "Bước cuối tạo mô hình để xem và đo. Từ điểm sau làm phẳng, em tính pháp tuyến, dựng mặt bằng Poisson, cắt vùng mật độ thấp, xoay về trục lên là +Y và ghi GLB đơn vị mét. "
        "Đo hai điểm là khoảng cách Euclid theo công thức (30); lệnh measure đã chạy được. Ví dụ trong đề cương: A bằng 0,52; 0,75; 1,20 và B bằng 1,90; 0,75; 1,20 cho 1,38 mét. "
        "Hình mesh bên trái là mô hình thật của scene dev. Em cho xem thẳng để thấy chất lượng hình học hiện còn thấp, mesh còn nhiều mảnh vỡ; đây là một lý do cần cải thiện gate và fusion."
    ),
)
pic(
    s,
    "res_mesh.png",
    0.5,
    1.45,
    6.2,
    4.4,
    "Mesh Poisson (GLB) của scene dev: chất lượng hình học còn thấp",
    alt="Mesh phòng dựng từ điểm, còn nhiều mảnh vỡ",
)
pic(s, "res_b0_3d.png", 6.9, 1.45, 5.93, 3.2, "Mây điểm COLMAP đã ra mét, góc nhìn xiên", alt="Mây điểm 3D của phòng")
txt(
    s,
    0.5,
    6.2,
    6.2,
    0.7,
    "Pháp tuyến PCA → Poisson (độ sâu 9) → cắt mật độ thấp → xoay +Y lên → GLB (mét).",
    size=13,
    bold=True,
    color=TEAL,
)
card(
    s, 6.9, 5.0, 5.93, 1.9, "Đo hai điểm (30)", ["Lệnh: python -m pipeline.export.measure --a x y z --b x y z"], size=13
)
eq(s, "measure", 7.1, 6.15, 5.5, 0.55)

s = new_slide(
    "Cách đánh giá",
    "D · Cách thực hiện",
    source="pipeline/eval/README.md; WORKING_LOG.md (căn Faro, 26/10); ĐC §20–21; faro_align_topdown_final.png",
    notes=(
        "Đánh giá cần ground truth đủ tốt. Em căn đám mây laser Faro vào hệ scene bằng ICP; sai số còn lại, tức khoảng cách mặt phẳng, có trung vị 1,59 cm và phân vị 95 là 5,28 cm, "
        "nên GT có sàn sai số cỡ một đến hai cm. Hình bên trái là hình căn: đỏ là Faro, xanh là điểm depth ARKit, tím là chồng khít. "
        "Em chấm tay một đoạn mốc và mười hai đoạn test trên Faro; sai số click khoảng một đến hai cm. Các biến thể so sánh: B0, B1, B3, đề xuất và ablation bỏ tín hiệu chất lượng. "
        "Ablation hai, ép mọi điểm về mặt phẳng, chuyển sang giai đoạn Replica. Các chỉ số: MAE theo công thức (32), median, MAPE, tỉ lệ dưới 5 cm, ATE, Chamfer và F-score với ngưỡng 5 cm."
    ),
)
pic(
    s,
    "res_faro_topdown.png",
    0.5,
    1.45,
    5.6,
    3.6,
    "Căn Faro vào hệ scene: đỏ = Faro, xanh = depth ARKit, tím = chồng khít",
    alt="Hình nhìn từ trên xuống thể hiện căn Faro",
    border=True,
)
txt(s, 0.5, 5.4, 5.6, 0.4, "Độ chính xác của ground truth", size=14, bold=True, color=TEAL)
txt(
    s,
    0.5,
    5.8,
    5.6,
    1.15,
    "Residual căn Faro: trung vị 1,59 cm, p95 5,28 cm. Click đầu mút khoảng 1–2 cm. Nên GT có sàn sai số cỡ 1–2 cm.",
    size=13,
)
table(
    s,
    6.4,
    1.45,
    [2.2, 4.23],
    [
        ["Hạng mục", "Cách làm"],
        ["Mốc scale", "1 đoạn (S06, tủ trắng 2,41 m), loại khỏi chỉ số test"],
        ["Đoạn test", "12 đoạn chấm tay trên Faro (S01–S13, trừ mốc)"],
        ["Biến thể", "B0, B1, B3, đề xuất, ablation bỏ chất lượng ảnh"],
        ["Chiều dài", "MAE, median, MAPE, % dưới 5 cm (32)–(33)"],
        ["Hình học", "ATE, Chamfer, F-score (δ = 5 cm)"],
        ["Quy tắc", "Held-out chạy đúng một lần; chỉnh tham số chỉ trên validation"],
    ],
    size=12,
    row_h=0.6,
)
eq(s, "mae", 6.5, 5.85, 4.2, 0.9)

# =====================================================================
# E. KẾT QUẢ (25–27)
# =====================================================================
s = new_slide(
    "Kết quả chạy thật trên scene dev 42444738",
    "E · Kết quả",
    source="sfm_result.json, mvs_result.json, vggt_result.json, scale.json, fusion_result.json, gate_result.json (data/scenes/arkitscenes/42444738)",
    notes=(
        f"Đây là kết quả chạy thật trên scene dev, đọc trực tiếp từ các file kết quả. Video có {vi(KF['n_frames'])} khung, qua lọc còn {KF['n_after_overlap']} ứng viên, chọn {SFM['n_keyframes']} keyframe. "
        f"SfM đăng ký {SFM['n_registered']} trên {SFM['n_images']} ảnh. VGGT chạy {VGGT['n_chunks']} chunk trong {vn(VGGT['seconds'], 1)} giây với VRAM đỉnh {vi(VGGT['peak_vram_mib'])} MiB. "
        f"Hệ số mét s_m bằng {vn(SCALE['s_m'], 4)}. Fusion ra {vi(FUS['n_points_fused'])} điểm; gate cho {GATE['n_gate_pass']} điểm qua cổng. "
        "Đây là minh chứng pipeline chạy xuyên suốt, chưa phải bảng sai số; sai số so với ground truth ở slide sau."
    ),
)
pic(s, "res_keyframes.png", 0.5, 1.45, 3.9, 3.4, "6 trong 80 keyframe", alt="Sáu keyframe thật")
pic(s, "res_wk_top.png", 4.6, 1.45, 3.9, 3.4, "Điểm đã ghép, màu theo w_k", alt="Mây điểm màu theo w_k")
tiles = [
    (f"{SFM['n_registered']}/{SFM['n_images']}", "ảnh đăng ký SfM", TEAL),
    (f"{vn(SFM['mean_reproj_error_px'], 2)} px", "sai số chiếu lại", TEAL),
    (f"{VGGT['n_chunks']} chunk", f"VGGT, {vn(VGGT['seconds'], 0)} s, {vi(VGGT['peak_vram_mib'])} MiB", TEAL),
    (f"{vn(SCALE['s_m'], 4)}", "s_m (m / đv COLMAP)", AMBER),
    (vi(FUS["n_points_fused"]), "điểm sau fusion", TEAL),
    (f"{GATE['n_gate_pass']}", "điểm qua cổng (1,09%)", RED),
]
for i, (b, label, col) in enumerate(tiles):
    x = 8.75 + (i % 2) * 2.1
    y = 1.45 + (i // 2) * 1.15
    stat(s, x, y, 2.0, b, label, big_size=20, h=1.05, color=col)
card(
    s,
    0.5,
    5.1,
    12.33,
    1.55,
    "Ý nghĩa",
    [
        "Pipeline đã chạy xuyên suốt trên một scene thật: từ video ra mô hình mét, có số đo theo thời gian và VRAM.",
        "Đây chưa phải bảng sai số: chất lượng hình học còn thấp và gate đang quá chặt (xem slide 22 và 26).",
    ],
    size=14,
    bullet=True,
)

b0, pr = METRICS["B0"], METRICS["proposed"]
s = new_slide(
    "Kết quả đo chiều dài: chỉ 3 đoạn hợp lệ",
    "E · Kết quả",
    source="evaluation/metrics.csv, lengths_B0_manual.csv, lengths_proposed_manual.csv (scene 42444738, chấm mù 05/11)",
    notes=(
        f"Đây là kết quả đo thật nhưng rất nhỏ: một scene và chỉ ba đoạn hợp lệ là S01, S02, S03, do các đoạn còn lại chưa chấm hoặc không bám được vào mô hình. "
        f"Với B0, MAE {f(b0['mae_cm'])} cm, trung vị {f(b0['median_cm'])} cm. Với đề xuất, MAE {f(pr['mae_cm'])} cm, trung vị {f(pr['median_cm'])} cm. "
        "Nghĩa là hiện đề xuất chưa tốt hơn B0, và ba đoạn không đủ để kết luận thống kê. B1 chưa có đoạn hợp lệ nào vì chưa chấm. "
        f"Về hình học, ATE cứng khoảng {f(b0['ate_rigid_cm'])} cm cho B0. Chamfer của B0 và đề xuất còn cao, chưa phân tích hết nguyên nhân. "
        "Mục tiêu dưới 5 cm đạt trên ba đoạn này, nhưng em không coi đó là kết quả cuối."
    ),
)
cd = CategoryChartData()
ids = sorted(set(ERR_B0) & set(ERR_PROP))
cd.categories = ids
cd.add_series("B0 (COLMAP thuần)", [round(ERR_B0[i], 2) for i in ids])
cd.add_series("Đề xuất", [round(ERR_PROP[i], 2) for i in ids])
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.5), Inches(1.45), Inches(5.6), Inches(4.0), cd)
ch = gf.chart
style_chart(ch)
ch.plots[0].gap_width = 70
ch.plots[0].has_data_labels = True
dl = ch.plots[0].data_labels
dl.number_format, dl.number_format_is_linked, dl.position, dl.font.size = (
    "0.0",
    False,
    XL_LABEL_POSITION.OUTSIDE_END,
    Pt(12),
)
for ser, col in zip(ch.plots[0].series, (TEAL, AMBER)):
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = col
ch.value_axis.has_title = True
ch.value_axis.axis_title.text_frame.text = "Sai số tuyệt đối (cm)"
ch.value_axis.axis_title.text_frame.paragraphs[0].runs[0].font.size = Pt(12)
ch.value_axis.axis_title.text_frame.paragraphs[0].runs[0].font.bold = False
ch.value_axis.maximum_scale = 5
ch.value_axis.minimum_scale = 0
txt(s, 0.5, 5.55, 5.6, 0.35, "Ngưỡng mục tiêu là 5 cm (đỉnh trục).", size=11, color=MUTED, italic=True)
rows = [["Biến thể", "Đoạn hợp lệ", "MAE (cm)", "Median (cm)", "ATE (cm)", "Chamfer (cm)", "F-score"]]
for v, lab in (("B0", "B0"), ("B1", "B1"), ("B3", "B3"), ("proposed", "Đề xuất"), ("abl_quality", "Abl. chất lượng")):
    m = METRICS[v]
    rows.append(
        [
            lab,
            f"{m['n_valid']}/12",
            f(m["mae_cm"]),
            f(m["median_cm"]),
            f(m["ate_rigid_cm"]),
            f(m["chamfer_cm"], 1),
            f(m["f_score"], 3),
        ]
    )
table(
    s,
    6.35,
    1.45,
    [1.45, 0.95, 0.85, 0.95, 0.75, 0.9, 0.63],
    rows,
    size=11,
    row_h=0.5,
    aligns=["l", "c", "c", "c", "c", "c", "c"],
)
rect(s, 6.35, 4.65, 6.48, 2.25, fill=RGBColor(0xFB, 0xEE, 0xEC), line=RED)
txt(
    s,
    6.5,
    4.72,
    6.2,
    2.1,
    [
        [("Đọc đúng con số này", {"bold": True, "color": RED, "size": 15})],
        "1 scene, 3 đoạn: chưa phải kết luận thống kê.",
        "Đề xuất hiện chưa tốt hơn B0 (median 2,53 so với 1,12 cm).",
        "B1 chưa có đoạn hợp lệ (chưa chấm); Chamfer còn cao, chưa phân tích nguyên nhân.",
    ],
    size=13,
    bullet=False,
    space=4,
)

ratios = [(r["scene"].split("/")[-1], float(r["ratio"]) * 100, int(r["n_models"])) for r in SWEEP_ROWS]
med = sorted(r for _, r, _ in ratios)
median_ratio = (med[2] + med[3]) / 2
s = new_slide(
    "Kiểm tra trên 6 scene Validation (M2)",
    "E · Kết quả",
    source="docs/evidence/m2_sfm/after_30-10/sweep.csv (khoảng 30/10/2026); WORKING_LOG.md bảng M2",
    notes=(
        f"Mốc M2 kiểm tra quy trình chọn keyframe và SfM trên sáu scene Validation. Tiêu chí: số keyframe từ 40 đến 80, từ 90 phần trăm keyframe đăng ký SfM, và VRAM đỉnh dưới 8 GB. "
        f"Số keyframe đạt 78 đến 80 ở cả sáu scene. Tỉ lệ đăng ký trung vị {vn(median_ratio, 1)} phần trăm, nhưng scene 47204552 chỉ {vn(ratios[-1][1], 1)} phần trăm, dưới ngưỡng, và SfM tách thành {ratios[-1][2]} model rời. "
        "VGGT đo trên scene 42897599 có VRAM đỉnh 6.021 MiB. Phần chưa xong: chưa khoá lại ngưỡng overlap và exposure với SfM mới; các giá trị đó còn là tạm."
    ),
)
cd = CategoryChartData()
cd.categories = [r[0] for r in ratios]
cd.add_series("Tỉ lệ ảnh đăng ký SfM (%)", [round(r[1], 1) for r in ratios])
gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.5), Inches(1.45), Inches(7.6), Inches(4.6), cd)
ch = gf.chart
style_chart(ch, legend=False)
ch.plots[0].gap_width = 60
ch.plots[0].has_data_labels = True
dl = ch.plots[0].data_labels
dl.number_format, dl.number_format_is_linked, dl.position, dl.font.size = (
    "0.0",
    False,
    XL_LABEL_POSITION.OUTSIDE_END,
    Pt(12),
)
ser = ch.plots[0].series[0]
for i, (_, r, _) in enumerate(ratios):
    pt = ser.points[i]
    pt.format.fill.solid()
    pt.format.fill.fore_color.rgb = TEAL if r >= 90 else RED
ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 70, 105
ch.value_axis.has_title = True
ch.value_axis.axis_title.text_frame.text = "Tỉ lệ đăng ký (%)"
ch.value_axis.axis_title.text_frame.paragraphs[0].runs[0].font.size = Pt(12)
ch.value_axis.axis_title.text_frame.paragraphs[0].runs[0].font.bold = False
txt(
    s,
    0.5,
    6.15,
    7.6,
    0.8,
    "Mục tiêu ≥ 90% (màu xanh đạt, màu đỏ chưa đạt). Trục bắt đầu từ 70%.",
    size=12,
    color=MUTED,
    italic=True,
)
stat(s, 8.4, 1.45, 2.1, f"{vn(median_ratio, 1)}%", "đăng ký trung vị", big_size=26, h=1.3)
stat(s, 10.73, 1.45, 2.1, "78–80", "keyframe mỗi scene (40–80)", big_size=26, h=1.3)
stat(
    s,
    8.4,
    2.9,
    4.43,
    f"{vi(VGGT['peak_vram_mib'])} MiB",
    "VRAM đỉnh của VGGT (đo trên 42897599; GPU 8.188 MiB)",
    big_size=26,
    h=1.3,
)
card(
    s,
    8.4,
    4.35,
    4.43,
    2.55,
    "Còn tồn tại",
    [
        f"47204552 chỉ {vn(ratios[-1][1], 1)}% (SfM tách {ratios[-1][2]} model).",
        "Chưa khoá lại ngưỡng overlap và exposure với SfM mới (giá trị tạm).",
    ],
    size=13,
    accent=RED,
    bullet=True,
)

# =====================================================================
# F. CÒN LẠI, KẾT LUẬN (28–30)
# =====================================================================
s = new_slide(
    "Các bước còn lại để hoàn thiện dự án",
    "F · Còn lại",
    source="WORKING_LOG.md (mục chưa làm, câu hỏi mở); README.md §7, §10; AGENTS.md §6",
    notes=(
        "Các việc còn lại theo thứ tự ưu tiên. Một, đóng M3: chấm đoạn cho B1, các đoạn S04, S09, S10, và nhờ người khác chấm mù để bỏ thiên lệch vì em nhớ ground truth. "
        "Hai, khoá lại ngưỡng overlap và exposure với SfM mới và xử lý scene 47204552 dưới 90 phần trăm. "
        "Ba, xem lại cổng plane gate đang quá chặt, chỉnh trên validation, không dùng held-out. "
        "Bốn, M4: chạy nhiều scene ARKit, ngưỡng khoá trên validation, held-out chạy đúng một lần. "
        "Năm, M5: Replica, cần render bằng Habitat-Sim, nhưng khả năng cài trên Windows chưa kiểm chứng, và thiếu nhãn phẳng; cùng với thu sáu đến tám phòng thật. "
        "Sáu, M6: FastAPI, Unity và báo cáo."
    ),
)
rows = [
    ["#", "Việc cần làm", "Mục đích", "Mốc", "Ưu tiên"],
    ["1", "Chấm B1, S04/S09/S10; chấm mù bởi người khác", "Đóng M3, bỏ thiên lệch người chấm", "M3", "Cao"],
    ["2", "Khoá lại overlap, exposure; xử lý 47204552 (< 90%)", "Đạt tiêu chí M2 trên mọi scene", "M2", "Cao"],
    [
        "3",
        "Xem lại cổng plane gate (w_k > τ_w chặn nhiều nhất)",
        "Để gate thật sự làm phẳng, chỉnh trên validation",
        "M3–M4",
        "Cao",
    ],
    ["4", "Chạy nhiều scene ARKit; held-out chạy một lần", "Có bảng val và held-out riêng", "M4", "Trung bình"],
    [
        "5",
        "Replica (Habitat-Sim, nhãn phẳng) và thu 6–8 phòng thật",
        "Test cross-domain; Ablation 2",
        "M5",
        "Trung bình",
    ],
    ["6", "FastAPI + Unity, báo cáo cuối", "Ứng dụng đo trên điện thoại", "M6", "Sau"],
]
table(
    s,
    0.5,
    1.45,
    [0.45, 5.2, 4.4, 1.1, 1.18],
    rows,
    size=12,
    row_h=0.62,
    aligns=["c", "l", "l", "c", "c"],
    bold_first_col=False,
)
card(
    s,
    0.5,
    5.95,
    12.33,
    1.0,
    "Rủi ro đã biết",
    ["Replica thiếu nhãn phẳng; Habitat-Sim chưa cài được trên Windows (chưa kiểm chứng); GPU chỉ 8 GB."],
    size=13,
    accent=RED,
)

s = new_slide(
    "Kết luận hiện tại",
    "F · Còn lại",
    dark=True,
    source="WORKING_LOG.md, metrics.csv (06/11/2026)",
    notes=(
        "Kết luận hiện tại. Đã làm được: toàn bộ pipeline chín stage chạy xuyên suốt trên một scene thật, có ground truth Faro đã căn, có số đo thời gian và VRAM, "
        "và SfM đạt trung vị 95,9 phần trăm đăng ký trên sáu scene Validation. Chưa chứng minh được: phương pháp đề xuất chưa tốt hơn B0 trên ba đoạn hợp lệ, "
        "cổng plane gate quá chặt nên hầu như chưa làm phẳng; dưới 5 cm mới đạt trên ba đoạn của một scene, chưa phải kết luận. "
        "Hướng tiếp theo: đóng M3 với chấm mù, chỉnh gate trên validation, rồi mở rộng sang nhiều scene và Replica."
    ),
)
cols = [
    (
        "Đã làm được",
        GREEN,
        [
            "Pipeline 9 stage chạy xuyên suốt trên một scene thật.",
            "Ground truth Faro đã căn; 1 mốc + 12 đoạn test.",
            f"SfM đăng ký trung vị {vn(median_ratio, 1)}% trên 6 Validation.",
        ],
    ),
    (
        "Chưa chứng minh",
        RED,
        [
            "Đề xuất chưa tốt hơn B0 (3 đoạn, 1 scene).",
            "Plane gate quá chặt: chỉ 1,09% điểm qua cổng.",
            "Mục tiêu < 5 cm mới đạt trên 3 đoạn, chưa phải kết luận.",
        ],
    ),
    (
        "Hướng tiếp theo",
        AMBER,
        [
            "Đóng M3 với chấm mù, chỉnh gate trên validation.",
            "M4: nhiều scene, held-out chạy một lần.",
            "M5–M6: Replica, tự thu, ứng dụng.",
        ],
    ),
]
for i, (t1, col, body) in enumerate(cols):
    x = 0.5 + i * 4.15
    rect(s, x, 1.55, 4.0, 5.2, fill=RGBColor(0x1A, 0x42, 0x4E), line=None)
    txt(s, x + 0.2, 1.7, 3.6, 0.5, t1, size=24, bold=True, color=col, font=HEAD)
    txt(s, x + 0.2, 2.5, 3.6, 4.1, body, size=19, color=WHITE, bullet=True, space=18)

s = new_slide(
    "Tài liệu tham khảo và hỏi đáp",
    "F · Còn lại",
    dark=True,
    source="Papers/ và Docs/TaiTao3D_Metric_3DMeph.pdf (§22, Hình 28)",
    notes=(
        "Đây là các tài liệu cốt lõi của dự án. Phần lớn nằm trong thư mục Papers. Em xin dừng báo cáo tại đây và mong nhận được góp ý của thầy cô. Xin cảm ơn."
    ),
)
refs = [
    "Baruch và cs. ARKitScenes: A Diverse Real-World Dataset for 3D Indoor Scene Understanding. NeurIPS Datasets and Benchmarks, 2021.",
    "Straub và cs. The Replica Dataset: A Digital Replica of Indoor Spaces. arXiv 1906.05797, 2019.",
    "Wang và cs. VGGT: Visual Geometry Grounded Transformer. CVPR 2025.",
    "Schönberger, Frahm. Structure-from-Motion Revisited. CVPR 2016.",
    "Schönberger, Zheng, Pollefeys, Frahm. Pixelwise View Selection for Unstructured Multi-View Stereo. ECCV 2016.",
    "Umeyama. Least-squares estimation of transformation parameters between two point patterns. IEEE TPAMI 13(4), 1991.",
    "GGPT; UniDepthV2; PlanarSplatting; Trust3R; PlaneMVS; ConfidentSplat: xem ĐC §22 và Hình 28.",
]
txt(s, 0.5, 1.5, 8.3, 5.4, refs, size=14, color=WHITE, bullet=True, space=9)
rect(s, 9.1, 1.6, 3.73, 5.1, fill=RGBColor(0x1A, 0x42, 0x4E), line=None)
txt(s, 9.2, 2.6, 3.53, 1.0, "Xin cảm ơn", size=34, bold=True, color=AMBER, font=HEAD, align=PP_ALIGN.CENTER)
txt(s, 9.2, 3.8, 3.53, 0.8, "Hỏi đáp và góp ý", size=22, color=WHITE, font=HEAD, align=PP_ALIGN.CENTER)
txt(
    s,
    9.2,
    5.3,
    3.53,
    0.9,
    "Trần Quang Đại · GVHD Lê Thị Vĩnh Thanh",
    size=13,
    color=RGBColor(0xA9, 0xBC, 0xC4),
    align=PP_ALIGN.CENTER,
)

# ---------- lưu ----------
prs.core_properties.title = "3DMeph: Tái tạo 3D metric trong nhà từ video điện thoại - Báo cáo tiến độ"
prs.core_properties.author = "Trần Quang Đại"
if _n[0] != TOTAL:
    WARN.append(f"Số slide {_n[0]} khác {TOTAL}")
prs.save(OUTFILE)
print(f"Đã lưu {OUTFILE} ({_n[0]} slide)")
for w in WARN:
    print("CẢNH BÁO:", w)
sys.exit(0)
