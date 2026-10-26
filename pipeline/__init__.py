"""3DMeph: dựng lại 3D metric trong nhà từ video điện thoại.

QUAN TRỌNG (thứ tự import): trong môi trường hiện tại, `import open3d` hoặc `import cv2` TRƯỚC
`pycolmap` gây lỗi "DLL load failed". Chạy được khi `import torch` đứng trước. Vì vậy gói này
import torch ngay khi được nạp; mọi module phải được import qua gói `pipeline`.
"""

try:
    import torch  # noqa: F401  (phải đứng đầu, trước open3d/cv2/pycolmap)
except ImportError:  # cho phép chạy phần không cần GPU khi chưa cài torch
    pass

__version__ = "0.1.0"
