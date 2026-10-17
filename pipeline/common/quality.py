"""Tín hiệu chất lượng ảnh và hàm đổi sai số → điểm tin cậy. ĐC §7.3, §16.1, §16.2.

Mọi điểm tin cậy nằm trong [0, 1], càng lớn càng tốt.
"""

from __future__ import annotations

import numpy as np


def laplacian_variance(gray: np.ndarray) -> float:
    """V = Var(∇²I)  (3). gray: ảnh xám 2D."""
    import cv2  # import muộn: gói `pipeline` đã import torch trước (xem pipeline/__init__.py)

    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def q_blur(v: float, v_ref: float) -> float:
    """q_blur = min(1, V / V_ref)  (3). V_ref đo trên 6 scene Validation (chưa có số; quality.v_ref)."""
    if v_ref is None or v_ref <= 0:
        raise ValueError("v_ref chưa được đo (quality.v_ref); không có số mặc định")
    return float(min(1.0, max(0.0, v / v_ref)))


def exposure_counts(gray: np.ndarray, dark_px: int = 5, bright_px: int = 250):
    """(số pixel ≤ dark_px, số pixel ≥ bright_px, tổng pixel)."""
    return int((gray <= dark_px).sum()), int((gray >= bright_px).sum()), int(gray.size)


def q_exposure_from_counts(n_dark: int, n_bright: int, n_total: int) -> float:
    """q_exposure = 1 − (#{pixel ≤ 5} + #{pixel ≥ 250}) / #{pixel}  (20)."""
    if n_total <= 0:
        raise ValueError("n_total phải > 0")
    return float(1.0 - (n_dark + n_bright) / n_total)


def q_exposure(gray: np.ndarray, dark_px: int = 5, bright_px: int = 250) -> float:
    return q_exposure_from_counts(*exposure_counts(gray, dark_px, bright_px))


def q_texture(grad_mean: float, g_ref: float) -> float:
    """q_texture = min(1, ‖∇I‖_{N(k)} / G_ref)  (20). G_ref: trung vị trên Validation (quality.g_ref)."""
    if g_ref is None or g_ref <= 0:
        raise ValueError("g_ref chưa được đo (quality.g_ref); không có số mặc định")
    return float(min(1.0, max(0.0, grad_mean / g_ref)))


def window_gradient_mean(gray: np.ndarray, xy: np.ndarray, window: int = 15) -> np.ndarray:
    """Độ lớn gradient trung bình trong cửa sổ window×window quanh mỗi điểm (px, cột/hàng liên tục).

    xy: (n, 2) toạ độ (x, y). Trả về mảng (n,). Điểm ngoài ảnh được kẹp vào biên.
    """
    import cv2

    g = gray.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.sqrt(gx * gx + gy * gy)
    mean_map = cv2.boxFilter(mag, ddepth=-1, ksize=(window, window), borderType=cv2.BORDER_REPLICATE)
    h, w = gray.shape
    xy = np.atleast_2d(np.asarray(xy, dtype=np.float64))
    cols = np.clip(np.floor(xy[:, 0]).astype(int), 0, w - 1)
    rows = np.clip(np.floor(xy[:, 1]).astype(int), 0, h - 1)
    return mean_map[rows, cols].astype(np.float64)


def f_err(x, tau: float):
    """f(x) = e^{−x/τ}  (21): đổi sai số (càng lớn càng xấu) thành điểm tin cậy. f(0)=1, f(τ)=0,37, f(2τ)=0,14."""
    if tau <= 0:
        raise ValueError("tau phải > 0")
    return np.exp(-np.asarray(x, dtype=np.float64) / tau)
