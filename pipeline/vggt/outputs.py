"""Hậu xử lý đầu ra VGGT. ĐC §13.

VGGT trả confidence theo conf = 1 + exp(x) ∈ [1, ∞) (vggt/heads/head_act.py, conf_activation="expp1").
Đề cương cần c_model ∈ [0, 1] cho (19) nhưng KHÔNG nêu cách đổi; đây là quyết định của nhóm.
"""

from __future__ import annotations

import numpy as np


def conf_to_c_model(conf) -> np.ndarray:
    """c_model = 1 − 1/conf  (conf ≥ 1). conf=1 → 0; conf=2,2 → 0,55; conf=50 → 0,98.

    Đây là aleatoric confidence tỷ lệ với uncertainty, KHÔNG phải xác suất đã hiệu chuẩn (ĐC §13, §23).
    """
    conf = np.asarray(conf, dtype=np.float64)
    if np.any(conf < 1.0):
        raise ValueError("conf của VGGT (expp1) phải ≥ 1")
    return 1.0 - 1.0 / conf
