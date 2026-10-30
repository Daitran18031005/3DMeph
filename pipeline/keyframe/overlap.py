"""Overlap giữa hai khung chỉ từ RGB (ĐC §6.1 công thức (1); kế hoạch M2).

Overlap = (W − Δ)/W: với phép dịch ngang Δ trên bề rộng W. Tổng quát cho xoay và dịch: ORB + khớp + homography RANSAC, rồi lấy phần diện tích của khung A
được ảnh B phủ (khung B chiếu vào A), chia diện tích A. Không đủ điểm khớp (tường trơn, di chuyển quá nhanh) ⇒ overlap = 0, coi là mất kết nối.
Pose ARKit không được dùng (ĐC §10: chỉ RGB làm input).
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

N_FEATURES = 1000
RATIO = 0.75                 # lọc tỉ lệ của Lowe khi khớp
MIN_INLIERS = 15             # dưới số này coi là không khớp được [Suy luận]
RANSAC_PX = 3.0


class Features:
    """Đặc trưng ORB của một khung xám, tính một lần rồi so với nhiều khung khác."""

    def __init__(self, gray: np.ndarray, n_features: int = N_FEATURES):
        self.shape = gray.shape[:2]
        orb = cv2.ORB_create(nfeatures=n_features)
        self.kp, self.des = orb.detectAndCompute(gray, None)


def overlap_fraction(a: Features, b: Features, min_inliers: int = MIN_INLIERS) -> Dict:
    """Phần diện tích khung A được khung B phủ, trong [0, 1]. Trả về {overlap, n_matches, n_inliers}."""
    out = {"overlap": 0.0, "n_matches": 0, "n_inliers": 0}
    if a.des is None or b.des is None or len(a.kp) < 4 or len(b.kp) < 4:
        return out
    knn = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(b.des, a.des, k=2)
    good = [m[0] for m in knn if len(m) == 2 and m[0].distance < RATIO * m[1].distance]
    out["n_matches"] = len(good)
    if len(good) < min_inliers:
        return out
    pb = np.float32([b.kp[m.queryIdx].pt for m in good])
    pa = np.float32([a.kp[m.trainIdx].pt for m in good])
    h, inl = cv2.findHomography(pb, pa, cv2.RANSAC, RANSAC_PX)
    if h is None or inl is None or not np.all(np.isfinite(h)):
        return out
    out["n_inliers"] = int(inl.sum())
    if out["n_inliers"] < min_inliers:
        return out
    hb, wb = b.shape
    ha, wa = a.shape
    quad = cv2.perspectiveTransform(np.float32([[0, 0], [wb, 0], [wb, hb], [0, hb]]).reshape(-1, 1, 2), h).reshape(-1, 2)
    if not np.all(np.isfinite(quad)) or np.abs(quad).max() > 1e5 or not cv2.isContourConvex(quad.astype(np.float32).reshape(-1, 1, 2)):
        return out                                                   # homography suy biến (khung B bị méo không còn là tứ giác lồi)
    mask = np.zeros((ha, wa), np.uint8)
    cv2.fillPoly(mask, [np.round(quad).astype(np.int32)], 1)
    out["overlap"] = float(mask.sum()) / float(ha * wa)
    return out


def select_by_overlap(n: int, overlap: Callable[[int, int], float], o_max: float, o_min: float) -> Tuple[List[int], int]:
    """Chọn keyframe từ n ứng viên theo thời gian (chỉ số 0..n−1). Từ khung giữ cuối `last`:
    bỏ khung trùng (overlap(last, j) > o_max); nhận khung đầu tiên không trùng; nếu khung đó đã mất kết nối (overlap < o_min)
    thì lùi một khung (khung trùng ngay trước nó) để giữ liên tục; nếu không còn khung nào lùi được thì nhận khung đó và đếm một "đứt".
    Trả về (chỉ số giữ, số lần đứt). Khung cuối không có người kế nhiệm thì không được thêm chỉ vì ở cuối [Suy luận]."""
    if not (0.0 <= o_min < o_max <= 1.0):
        raise ValueError("cần 0 ≤ overlap.min < overlap.max ≤ 1")
    if n == 0:
        return [], 0
    kept, breaks, last, j = [0], 0, 0, 1
    while j < n:
        o = overlap(last, j)
        if o > o_max:
            j += 1
            continue
        if o < o_min and j - 1 > last:
            j -= 1
        elif o < o_min:
            breaks += 1
        kept.append(j)
        last = j
        j += 1
    return kept, breaks


def features_cache(grays: List[np.ndarray], n_features: int = N_FEATURES) -> List[Features]:
    return [Features(g, n_features) for g in grays]


def make_overlap_fn(feats: List[Features], stats: Optional[List[Dict]] = None) -> Callable[[int, int], float]:
    """Hàm overlap(i, j) có nhớ đệm trên danh sách đặc trưng; ghi từng lần đo vào `stats` nếu có."""
    cache: Dict[Tuple[int, int], float] = {}

    def fn(i: int, j: int) -> float:
        if (i, j) not in cache:
            r = overlap_fraction(feats[i], feats[j])
            cache[(i, j)] = r["overlap"]
            if stats is not None:
                stats.append({"i": i, "j": j, **r})
        return cache[(i, j)]

    return fn
