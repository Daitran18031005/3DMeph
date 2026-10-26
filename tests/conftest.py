"""Cấu hình pytest cho 3DMeph.

- Đưa thư mục gốc repo vào sys.path để `import pipeline` chạy không cần cài.
- Import `pipeline` ngay đầu tiên: gói này `import torch` trước mọi thư viện khác, tránh lỗi DLL của
  pycolmap khi open3d/cv2 được nạp trước (xem pipeline/__init__.py).
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pipeline  # noqa: E402,F401
