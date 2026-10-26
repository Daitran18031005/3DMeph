#!/usr/bin/env python3
"""adapters.py — lớp chuyển tiếp: cài đặt đã chuyển sang `pipeline/common/adapters.py` (M1) để gói `pipeline` dùng được.

Giữ file này để các script và test hiện có (`import adapters`) chạy không đổi.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import pipeline  # noqa: E402,F401  (import torch trước cv2/open3d/pycolmap)

# isort: split
from pipeline.common.adapters import *  # noqa: E402,F401,F403
from pipeline.common.adapters import __all__  # noqa: E402,F401
