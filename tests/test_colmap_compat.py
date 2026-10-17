"""Tương thích pycolmap ↔ COLMAP CLI 4.2: pycolmap phải đọc được model do CLI ghi, và e_reproj theo từng
quan sát của ta phải khớp sai số chiếu lại mỗi điểm mà COLMAP ghi (ĐC §14.3).

Dùng model COLMAP đã chạy sẵn ở data/processed/images/sparse (thư mục bị .gitignore). Không có thì bỏ qua.

Dung sai có căn cứ (đo ngày 17/10/2026 trên 2.377 điểm / 121 ảnh): trung vị |Δ| = 0,0008 px, p95 = 0,008 px,
max = 0,05 px, tương quan 0,99996, trung bình lệch 0,04%. Khác biệt nhỏ do COLMAP lưu `point3D.error` ở bước
tối ưu trước, còn ta tính lại từ pose/điểm cuối cùng; vì vậy so ở mức tổng hợp, không đòi trùng từng điểm.
"""

from pathlib import Path

import numpy as np
import pytest

from pipeline.common.geometry import reproj_error

REPO_ROOT = Path(__file__).resolve().parents[1]
SPARSE = REPO_ROOT / "data" / "processed" / "images" / "sparse"

pycolmap = pytest.importorskip("pycolmap")


@pytest.mark.skipif(not (SPARSE / "points3D.bin").is_file(), reason="chưa có model COLMAP mẫu ở data/processed")
def test_pycolmap_reads_cli_model_and_per_observation_error_matches():
    rec = pycolmap.Reconstruction(str(SPARSE))
    assert len(rec.images) > 0 and len(rec.points3D) > 0

    mine, theirs = [], []
    for p in rec.points3D.values():
        errs = []
        for el in p.track.elements:
            img = rec.images[el.image_id]
            cam = rec.cameras[img.camera_id]
            cfw = img.cam_from_world
            xy = img.points2D[el.point2D_idx].xy
            errs.append(reproj_error(cam.calibration_matrix(), cfw.rotation.matrix(), cfw.translation,
                                     p.xyz[None, :], xy[None, :])[0])
        mine.append(np.mean(errs))
        theirs.append(p.error)
    mine, theirs = np.array(mine), np.array(theirs)
    diff = np.abs(mine - theirs)

    assert np.median(diff) < 2e-3
    assert np.percentile(diff, 95) < 2e-2
    assert diff.max() < 0.1
    assert np.corrcoef(mine, theirs)[0, 1] > 0.999
    assert mine.mean() == pytest.approx(theirs.mean(), rel=1e-3)
