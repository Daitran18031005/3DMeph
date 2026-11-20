"""Chụp các sơ đồ SVG trong diagrams/ ra img/<tên>.png bằng Chrome headless (độ phân giải x3).

Chạy: python render_diagrams.py   (cần Chrome hoặc Edge; đặt biến CHROME nếu ở chỗ khác)
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC, OUT = HERE / "diagrams", HERE / "img"
CANDIDATES = [
    os.environ.get("CHROME", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def main() -> int:
    chrome = next((c for c in CANDIDATES if c and Path(c).exists()), None)
    if chrome is None:
        print("Không tìm thấy Chrome/Edge; đặt biến CHROME.")
        return 1
    for svg in sorted(SRC.glob("*.svg")):
        text = svg.read_text(encoding="utf-8")
        w, h = map(float, re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', text).groups())
        html = f"<!doctype html><meta charset='utf-8'><body style='margin:0;background:#fff'>{text}</body>"
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "p.html"
            page.write_text(html, encoding="utf-8")
            png = OUT / f"{svg.stem}.png"
            subprocess.run(
                [
                    chrome,
                    "--headless=new",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    "--force-device-scale-factor=3",
                    f"--window-size={int(w)},{int(h)}",
                    f"--screenshot={png}",
                    page.as_uri(),
                ],
                check=True,
                capture_output=True,
            )
        print(f"{svg.name} -> {png.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
