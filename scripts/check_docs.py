#!/usr/bin/env python3
"""
check_docs.py — Kiểm tra README khớp với cấu hình và đề cương.

Cách chạy (trong env 3d_metric, từ thư mục gốc repo):
    python scripts/check_docs.py             # kiểm tra đầy đủ, chạy cả các khối bash có nhãn `# check`
    python scripts/check_docs.py --no-run    # bỏ qua việc chạy lệnh trong README (nhanh)

Kiểm tra:
  1. Khoá trong configs/default.yaml khớp HAI CHIỀU với các bảng "## Tham số" của README sở hữu khoá
     (tiền tố → README ở OWNERS bên dưới), kể cả giá trị ghi trong bảng.
  2. README mỗi module (thư mục có __init__.py dưới pipeline/) có đủ 8 mục của khung.
  3. Nội dung README (ngoài khối code): số công thức trong ngoặc tròn thuộc 1–37 (ĐC có 37 công thức);
     không còn tên hệ số fusion cũ (λ kèm chỉ số r hoặc d); số 581 chỉ xuất hiện như ví dụ hoặc "không dùng".
  4. Link tương đối trỏ tới file có thật (link `../` ra ngoài repo bị bỏ qua).
  5. Mọi khối ```bash phải bắt đầu bằng `# check` (được chạy thật) hoặc `# skip` (lệnh nặng/chưa có, kèm lý do).

Mã thoát: 0 nếu không có lỗi, 1 nếu có.
"""

import argparse
import math
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from pipeline.common.config import flatten_keys  # noqa: E402

# Tiền tố khoá cấu hình → README sở hữu (đường dẫn tương đối repo)
OWNERS = {
    "keyframe": "pipeline/keyframe/README.md",
    "quality": "pipeline/common/README.md",
    "colmap": "pipeline/colmap/README.md",
    "vggt": "pipeline/vggt/README.md",
    "align": "pipeline/alignment/README.md",
    "fusion": "pipeline/fusion/README.md",
    "plane": "pipeline/plane_gate/README.md",
    "export": "pipeline/export/README.md",
    "eval": "pipeline/eval/README.md",
    "loss": "configs/README.md",
    "paths": "configs/README.md",
}

REQUIRED_HEADINGS = [
    "Vai trò", "Input/Output", "Công thức", "Tham số", "Cách chạy riêng",
    "Test vector và tiêu chí đạt", "Lỗi thường gặp", "Người phụ trách",
]

MAX_FORMULA = 37  # đề cương đánh số công thức (1)–(37)
FORBIDDEN = ("lambda_r", "lambda_d", "λ_r", "λ_d")
CONTEXT_581 = ("ví dụ", "không dùng", "không được dùng", "cũ", "đề cương", "ĐC", "không phải")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache"}

errors = []


def err(path, line, msg):
    rel = Path(path).relative_to(REPO) if Path(path).is_absolute() else path
    errors.append(f"{str(rel).replace(os.sep, '/')}:{line}: {msg}")


def readme_files():
    out = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != "raw"]
        if Path(root) == REPO / "data":
            dirs[:] = [d for d in dirs if d not in ("raw", "processed", "self_collected", "scenes")]
        for f in files:
            if f == "README.md":
                out.append(Path(root) / f)
    return sorted(out)


def split_lines(text):
    """Trả về danh sách (số dòng 1-based, nội dung, đang_trong_khối_code, nhãn_ngôn_ngữ_khối)."""
    res, in_code, lang = [], False, ""
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code:
                in_code, lang = True, stripped[3:].strip().split()[0] if stripped[3:].strip() else ""
            else:
                in_code, lang = False, ""
            res.append((i, line, True, lang))
            continue
        res.append((i, line, in_code, lang))
    return res


def norm_cell(s):
    s = s.strip().strip("`").strip()
    if s == "null":
        return None
    if s == "true":
        return True
    if s == "false":
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def same_value(a, b):
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        return a is b or a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
    return str(a) == str(b)


def section_table_rows(lines, heading):
    """Các dòng bảng (số dòng, ô1, ô2) trong mục '## heading'."""
    rows, active = [], False
    for no, text, in_code, _lang in lines:
        if in_code:
            continue
        if text.startswith("## "):
            active = text[3:].strip() == heading
            continue
        if active and text.lstrip().startswith("|"):
            cells = [c.strip() for c in text.strip().strip("|").split("|")]
            if len(cells) >= 2:
                rows.append((no, cells[0], cells[1]))
    return rows


def check_config_vs_readme():
    raw = yaml.safe_load((REPO / "configs" / "default.yaml").read_text(encoding="utf-8"))
    keys = flatten_keys(raw)

    def raw_get(dotted):
        cur = raw
        for p in dotted.split("."):
            cur = cur[p]
        return cur

    expected = {}
    for k in keys:
        prefix = k.split(".", 1)[0]
        owner = OWNERS.get(prefix)
        if owner is None:
            err(REPO / "configs" / "default.yaml", 1, f"khoá {k}: tiền tố {prefix!r} chưa có README sở hữu (cập nhật OWNERS)")
            continue
        expected.setdefault(owner, set()).add(k)

    for owner, exp in expected.items():
        path = REPO / owner
        if not path.is_file():
            err(path, 1, "README sở hữu khoá cấu hình không tồn tại")
            continue
        lines = split_lines(path.read_text(encoding="utf-8"))
        rows = section_table_rows(lines, "Tham số")
        documented = {}
        for no, c1, c2 in rows:
            m = re.fullmatch(r"`([A-Za-z0-9_.]+)`", c1)
            if not m:
                continue  # dòng tiêu đề hoặc dòng phân cách của bảng
            key = m.group(1)
            documented[key] = (no, c2)
        for k in sorted(exp - set(documented)):
            err(path, 1, f"khoá {k} có trong default.yaml nhưng chưa được mô tả ở mục 'Tham số'")
        for k, (no, cell) in sorted(documented.items()):
            if k not in exp:
                err(path, no, f"khoá {k} ghi trong README nhưng không có (hoặc không thuộc README này) trong default.yaml")
                continue
            if not same_value(norm_cell(cell), raw_get(k)):
                err(path, no, f"khoá {k}: README ghi {cell.strip()!r} nhưng default.yaml là {raw_get(k)!r}")


def check_module_headings():
    pipeline = REPO / "pipeline"
    for d in sorted(p for p in pipeline.iterdir() if p.is_dir() and (p / "__init__.py").is_file()):
        readme = d / "README.md"
        if not readme.is_file():
            err(d, 1, "module chưa có README.md")
            continue
        heads = [t[3:].strip() for _n, t, in_code, _l in split_lines(readme.read_text(encoding="utf-8"))
                 if not in_code and t.startswith("## ")]
        for h in REQUIRED_HEADINGS:
            if h not in heads:
                err(readme, 1, f"thiếu mục '## {h}'")


def check_content(path):
    text = path.read_text(encoding="utf-8")
    for no, line, in_code, _lang in split_lines(text):
        if in_code:
            continue
        for tok in FORBIDDEN:
            if tok in line:
                err(path, no, f"còn ký hiệu cũ {tok!r}: đề cương dùng τ_e, τ_σ")
        # (?<![\w`]): bỏ qua lời gọi hàm như f(0) hoặc `q(3)`; chỉ xét số đứng riêng trong ngoặc
        for m in re.finditer(r"(?<![\w`])\((\d{1,3})\)", line):
            n = int(m.group(1))
            if n == 0 or n > MAX_FORMULA:
                err(path, no, f"số công thức ({n}) ngoài khoảng 1–{MAX_FORMULA} của đề cương")
        if "581" in line and not any(w in line for w in CONTEXT_581):
            err(path, no, "số 581 chỉ được nhắc như ví dụ/đề cương hoặc 'không dùng' (không phải giá trị cấu hình)")


def check_links(path):
    text = path.read_text(encoding="utf-8")
    for no, line, in_code, _lang in split_lines(text):
        if in_code:
            continue
        for m in re.finditer(r"\[[^\]]*\]\(([^)\s]+)\)", line):
            target = m.group(1)
            if re.match(r"^(https?:|mailto:|#)", target):
                continue
            rel = target.split("#", 1)[0]
            if not rel:
                continue
            resolved = (path.parent / rel).resolve()
            try:
                resolved.relative_to(REPO)
            except ValueError:
                continue  # trỏ ra ngoài repo (ví dụ ../PipelineFlowChart): bỏ qua
            if not resolved.exists():
                err(path, no, f"link {target!r} không trỏ tới file có thật")


def run_bash_blocks(path, run):
    lines = split_lines(path.read_text(encoding="utf-8"))
    i = 0
    while i < len(lines):
        no, text, in_code, lang = lines[i]
        if in_code and text.strip().startswith("```") and lang in ("bash", "sh"):
            j = i + 1
            body = []
            while j < len(lines) and not (lines[j][1].strip().startswith("```") and lines[j][2]):
                body.append((lines[j][0], lines[j][1]))
                j += 1
            first = next(((n, t.strip()) for n, t in body if t.strip()), None)
            if first is None or not (first[1].startswith("# check") or first[1].startswith("# skip")):
                err(path, no, "khối bash phải bắt đầu bằng '# check' hoặc '# skip (lý do)'")
            elif first[1].startswith("# check") and run:
                for n, t in body:
                    cmd = t.strip()
                    if not cmd or cmd.startswith("#"):
                        continue
                    argv = shlex.split(cmd)
                    if argv[0] == "python":
                        argv[0] = sys.executable
                    if any(a.endswith("check_docs.py") for a in argv) and "--help" not in argv:
                        continue  # tránh đệ quy vô hạn
                    r = subprocess.run(argv, cwd=REPO, capture_output=True, text=True, encoding="utf-8",
                                       errors="replace", timeout=180)
                    if r.returncode != 0:
                        tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or [""]
                        err(path, n, f"lệnh '# check' thất bại (mã {r.returncode}): {cmd} :: {tail[0]}")
            i = j
        i += 1


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Kiểm tra README khớp cấu hình và đề cương")
    ap.add_argument("--no-run", action="store_true", help="không chạy các lệnh '# check' trong README")
    args = ap.parse_args()

    check_config_vs_readme()
    check_module_headings()
    files = readme_files()
    for p in files:
        check_content(p)
        check_links(p)
        run_bash_blocks(p, run=not args.no_run)

    if errors:
        print(f"check_docs: {len(errors)} lỗi")
        for e in errors:
            print("  -", e)
        return 1
    print(f"check_docs: OK ({len(files)} README, {len(flatten_keys(yaml.safe_load((REPO / 'configs' / 'default.yaml').read_text(encoding='utf-8'))))} khoá cấu hình)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
