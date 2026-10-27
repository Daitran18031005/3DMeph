"""Mã lỗi của pipeline (ĐC Hình 24, kế hoạch §3). Stage ném `StageError`; `pipeline.run` ghi mã vào `run_meta.json` và thoát khác 0."""

from __future__ import annotations

E_TOO_FEW_KEYFRAMES = "E_TOO_FEW_KEYFRAMES"      # dưới 40 keyframe sau lọc (ĐC §7)
E_SFM_FAILED = "E_SFM_FAILED"                    # SfM không dựng được model (ĐC Hình 24)
E_MISSING_INPUT = "E_MISSING_INPUT"              # thiếu file đầu vào của stage (stage trước chưa chạy)
E_COLMAP_FAILED = "E_COLMAP_FAILED"              # lệnh COLMAP thoát khác 0
E_NOT_IMPLEMENTED = "E_NOT_IMPLEMENTED"          # stage chưa cài (ví dụ eval ở M1)
E_CUDA_OOM = "E_CUDA_OOM"                        # hết bộ nhớ GPU (VGGT quá chunk)
E_ANCHOR_STALE = "E_ANCHOR_STALE"                # mốc scale đã click trên model COLMAP khác với model hiện tại: click lại


class StageError(RuntimeError):
    """Lỗi của một stage kèm mã lỗi ổn định để ghi log và test."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
