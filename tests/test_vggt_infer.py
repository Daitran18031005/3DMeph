"""Test stage vggt (pipeline/vggt/infer.py) KHÔNG cần GPU hay trọng số: hình học `pad` đối chiếu với tiền xử lý thật của repo VGGT,
chia chunk, định dạng file đầu ra bằng mô hình giả, mã lỗi (thiếu file, hết bộ nhớ)."""

import json

import cv2
import numpy as np
import pytest

from pipeline.common import config as cfgmod
from pipeline.common import io as pio
from pipeline.common.errors import E_CUDA_OOM, E_MISSING_INPUT, StageError
from pipeline.common.schema import write_keyframes_csv
from pipeline.vggt import infer

torch = pytest.importorskip("torch")


# ---------------------------------------------------------------------------
# Hình học pad
# ---------------------------------------------------------------------------


def test_pad_geometry_anh_dung_ngang_va_vuong():
    g = infer.pad_geometry(480, 640)
    assert (g["new_w"], g["new_h"], g["pad_left"], g["pad_top"]) == (392, 518, 63, 0)
    assert g["scale_x"] == pytest.approx(392 / 480) and g["scale_y"] == pytest.approx(518 / 640)
    h = infer.pad_geometry(640, 480)
    assert (h["new_w"], h["new_h"], h["pad_left"], h["pad_top"]) == (518, 392, 0, 63)
    s = infer.pad_geometry(600, 600)
    assert (s["new_w"], s["new_h"], s["pad_left"], s["pad_top"]) == (518, 518, 0, 0)
    assert all(v % 14 == 0 for v in (g["new_w"], g["new_h"], h["new_w"], h["new_h"]))


def test_pad_khop_voi_tien_xu_ly_that_cua_vggt(tmp_path):
    """Chấm đen trên nền trắng: vị trí chấm sau `load_and_preprocess_images(mode='pad')` phải khớp `original_to_vggt` (sai ≤ 1 px trên 518)."""
    from vggt.utils.load_fn import load_and_preprocess_images
    w, h = 480, 640
    geo = infer.pad_geometry(w, h)
    for (cx, cy) in ((104.0, 204.0), (400.0, 90.0), (60.0, 600.0)):
        img = np.full((h, w, 3), 255, dtype=np.uint8)
        img[int(cy) - 4:int(cy) + 4, int(cx) - 4:int(cx) + 4] = 0
        p = tmp_path / f"dot_{int(cx)}_{int(cy)}.jpg"
        cv2.imwrite(str(p), img, [cv2.IMWRITE_JPEG_QUALITY, 100])
        t = load_and_preprocess_images([str(p)], mode="pad")
        assert tuple(t.shape) == (1, 3, 518, 518)
        ys, xs = np.nonzero(t[0, 0].numpy() < 0.5)
        got = np.array([xs.mean() + 0.5, ys.mean() + 0.5])                    # tâm chấm, toạ độ liên tục
        want = infer.original_to_vggt([[cx, cy]], geo)[0]
        assert np.abs(got - want).max() < 1.0, (got, want)
        back = infer.vggt_to_original(want[None, :], geo)[0]
        assert np.abs(back - [cx, cy]).max() < 1e-9


def test_vggt_dtype():
    assert infer.vggt_dtype("bf16") == (torch.bfloat16, True)
    assert infer.vggt_dtype("fp16") == (torch.float16, True)
    assert infer.vggt_dtype("fp32") == (torch.float32, False)
    with pytest.raises(ValueError):
        infer.vggt_dtype("int8")


# ---------------------------------------------------------------------------
# run_vggt với mô hình giả
# ---------------------------------------------------------------------------


class FakeVGGT:
    """Camera nào cũng là gốc, depth = 2 m, conf = 2,2 (⇒ c_model = 0,5455)."""

    def __init__(self, fail_on_call=None):
        self.calls, self.fail_on_call = [], fail_on_call

    def __call__(self, images):
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            raise torch.cuda.OutOfMemoryError("giả lập")
        s, _, h, w = images.shape
        self.calls.append(s)
        pose = torch.zeros(1, s, 9)
        pose[..., 6] = 1.0            # quaternion (0,0,0,1)
        pose[..., 7:] = 0.8           # FoV
        return {"pose_enc": pose, "depth": torch.full((1, s, h, w, 1), 2.0), "depth_conf": torch.full((1, s, h, w), 2.2)}


def make_scene(tmp_path, n=25, w=48, h=64):
    layout = pio.scene_layout(tmp_path / "scenes", "arkitscenes", "777")
    pio.ensure_dir(layout.keyframes)
    pio.ensure_dir(layout.metadata)
    rng = np.random.default_rng(0)
    rows = []
    for i in range(n):
        cv2.imwrite(str(layout.keyframes / f"{i:04d}.jpg"), rng.integers(0, 256, (h, w, 3), dtype=np.uint8))
        rows.append({"view_id": i, "frame_ts": 1000 + i, "src_name": f"x_{i}.png", "w": w, "h": h, "fx": 500, "fy": 500, "cx": w / 2, "cy": h / 2})
    write_keyframes_csv(rows, layout.metadata / "keyframes.csv")
    return layout


def cfg_fp32():
    cfg = cfgmod.load_config()
    cfg["vggt"]["dtype"] = "fp32"
    return cfg


def test_run_vggt_chunks_file_va_thong_ke(tmp_path):
    layout = make_scene(tmp_path, n=25)
    fake = FakeVGGT()
    logs = []
    st = infer.run_vggt(layout, cfg_fp32(), log=logs.append, device="cpu", load=lambda d, dev, dt: fake, weights_dir=tmp_path / "w")
    assert st["n_chunks"] == 3 and fake.calls == [12, 12, 5]                  # ⌈(25−2)/(12−2)⌉ = 3; chunk cuối còn 5 ảnh
    assert st["chunks"][1]["start"] == 10 and st["chunks"][1]["end"] == 22      # gối 2 ảnh
    assert st["camera0_identity_err_max"] < 1e-6 and st["peak_vram_mib"] is None and st["device"] == "cpu"
    raw, out, meta = infer.read_chunk(layout, 2)
    assert raw["extrinsic"].shape == (5, 3, 4) and raw["intrinsic"].shape == (5, 3, 3)
    assert raw["depth"].shape == (5, 518, 518) and raw["depth_conf"].shape == (5, 518, 518)
    assert out["points"].shape == (5, 518, 518, 3) and out["c_model"].shape == (5, 518, 518)
    assert np.allclose(out["c_model"], 1 - 1 / 2.2, atol=1e-6)
    assert np.allclose(out["points"][..., 2], 2.0, atol=1e-5)                  # camera gốc nhìn thẳng: z world = depth
    assert meta["views"] == [20, 21, 22, 23, 24] and meta["pad_geometry"]["pad_left"] == 63
    assert (layout.vggt / "vggt_result.json").is_file() and (layout.vggt / "chunk_01" / "chunk_meta.json").is_file()
    assert json.loads((layout.vggt / "vggt_result.json").read_text(encoding="utf-8"))["pad_geometry"]["new_w"] == 392
    assert any("3 chunk" in m for m in logs)


def test_run_vggt_oom_va_thieu_dau_vao(tmp_path):
    layout = make_scene(tmp_path, n=25)
    with pytest.raises(StageError) as e:
        infer.run_vggt(layout, cfg_fp32(), log=lambda m: None, device="cpu", load=lambda d, dev, dt: FakeVGGT(fail_on_call=1),
                       weights_dir=tmp_path / "w")
    assert e.value.code == E_CUDA_OOM and "chunk 1" in str(e.value)
    assert (layout.vggt / "chunk_00" / "vggt_raw.npz").is_file()                # chunk trước OOM đã ghi
    empty = pio.scene_layout(tmp_path / "empty", "arkitscenes", "888")
    with pytest.raises(StageError) as e2:
        infer.run_vggt(empty, cfg_fp32(), log=lambda m: None, device="cpu", load=lambda d, dev, dt: FakeVGGT())
    assert e2.value.code == E_MISSING_INPUT
    (layout.keyframes / "0003.jpg").unlink()
    with pytest.raises(StageError) as e3:
        infer.run_vggt(layout, cfg_fp32(), log=lambda m: None, device="cpu", load=lambda d, dev, dt: FakeVGGT())
    assert e3.value.code == E_MISSING_INPUT and "0003.jpg" in str(e3.value)


def test_runtime_error_out_of_memory_thanh_e_cuda_oom(tmp_path):
    class Boom(FakeVGGT):
        def __call__(self, images):
            raise RuntimeError("CUDA error: out of memory")

    layout = make_scene(tmp_path, n=12)
    with pytest.raises(StageError) as e:
        infer.run_vggt(layout, cfg_fp32(), log=lambda m: None, device="cpu", load=lambda d, dev, dt: Boom(), weights_dir=tmp_path / "w")
    assert e.value.code == E_CUDA_OOM


def test_load_model_thieu_trong_so(tmp_path):
    with pytest.raises(StageError) as e:
        infer.load_model(tmp_path / "khong_co", "cpu")
    assert e.value.code == E_MISSING_INPUT and "model.safetensors" in str(e.value)


def test_resolve_weights_dir_tuong_doi_so_voi_repo(tmp_path):
    cfg = cfgmod.load_config()
    assert infer.resolve_weights_dir(cfg, tmp_path) == tmp_path / "../vggt_weights/VGGT-1B"
    cfg["vggt"]["weights_dir"] = str(tmp_path / "abs")
    assert infer.resolve_weights_dir(cfg) == tmp_path / "abs"
