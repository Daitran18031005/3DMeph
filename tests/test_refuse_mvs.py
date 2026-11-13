"""Test cấu hình d3 của stereo_fusion và sao lưu MVS lọc chặt của scripts/refuse_mvs.py."""

import importlib.util
import sys
from pathlib import Path

from pipeline.colmap.run_colmap import stereo_fusion_args
from pipeline.common import config as cfgmod
from pipeline.common.io import SceneLayout

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
spec = importlib.util.spec_from_file_location("refuse_mvs_under_test", REPO / "scripts" / "refuse_mvs.py")
rm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rm)


def test_stereo_fusion_args_mac_dinh_la_d3():
    a = stereo_fusion_args(cfgmod.load_config())
    d = dict(zip(a[::2], a[1::2]))
    assert d == {"--StereoFusion.min_num_pixels": 2, "--StereoFusion.max_reproj_error": 8, "--StereoFusion.max_depth_error": 0.05,
                 "--StereoFusion.max_normal_error": 30, "--StereoFusion.check_num_images": 100}
    assert stereo_fusion_args({"colmap": {}}) == []                                  # không khai báo thì dùng mặc định COLMAP


def test_backup_strict_giu_ban_cu_va_khong_ghi_de(tmp_path):
    lay = SceneLayout(tmp_path)
    for f, txt in [(lay.colmap_mvs / "fused.ply", "cu"), (lay.colmap_mvs / "fused.ply.vis", "vis"), (lay.colmap_metric / "fused_metric.ply", "m"),
                   (lay.fusion / "fused_points.ply", "f"), (lay.plane_refinement / "refined_points.ply", "r"), (lay.alignment / "scale.json", "{}"),
                   (lay.evaluation / "metrics.csv", "variant\n"), (lay.evaluation / "logs" / "align_B0.json", "{}")]:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(txt)
    made = rm.backup_strict(lay)
    assert (lay.colmap_mvs / "fused_strict.ply").read_text() == "cu" and (lay.colmap_mvs / "fused_strict.ply.vis").read_text() == "vis"
    assert (lay.proposed / "variants" / "strict_old" / "fusion" / "fused_points.ply").is_file()
    assert (lay.evaluation / "variants" / "strict_old" / "logs" / "align_B0.json").is_file() and len(made) == 8
    (lay.colmap_mvs / "fused.ply").write_text("moi")                                  # sau khi ghi fused.ply mới, chạy lại không được đè bản cũ
    assert rm.backup_strict(lay) == [] and (lay.colmap_mvs / "fused_strict.ply").read_text() == "cu"
