# Ghi chú luồng 2: adapter video điện thoại (feature/video-adapter, 31/10)

Để gộp vào `WORKING_LOG.md` sau (luồng này không sửa WORKING_LOG theo yêu cầu).

## Đã làm và đã chạy thật
- `adapters.VideoSource` (đọc timestamp, tag rotation, khung theo chỉ số) + `estimate_intrinsics`; `orientation.rotation_for_video`, `upright_rot`;
  `extract.py` tách lõi `_densify` dùng chung, thêm `extract_video_keyframes`; `run.py` nhận `--scene self_collected/<id>` (chỉ chèn dòng);
  khối config `video:` (`source_dir`, `long_edge`, `focal35_mm`) + dòng `video` trong `OWNERS` của `scripts/check_docs.py`.
- **Hồi quy ARKit sau refactor** (đã chạy thật, 42444738, stage `keyframe` ghi vào scratchpad, không đụng kết quả có sẵn): `candidates.csv`, `camera.json` trùng byte với bản chạy trước refactor;
  111/111 ảnh `frames/candidates/*.jpg` trùng byte; `source.json` trùng (trừ `stats.seconds`).
- Test: `tests/test_keyframe_video.py` (8 test, video tổng hợp mp4v). Toàn bộ: `pytest tests -q` = 284 passed, 11 skipped (worktree không có `data/`, 11 test cần dữ liệu bị skip, chưa chạy ở đây);
  `ruff check .` sạch; `check_docs.py --no-run` OK (19 README, 71 khoá; repo chính tính 20 README).
- CLI thật trên video tổng hợp 40 s (320×240, 30 khung/giây) đặt ở `<root>/data/self_collected/clip/`: `python -m pipeline.run --scene self_collected/clip --from-stage keyframe --to-stage keyframe`
  → exit 0, 80 ứng viên, `camera.json` fx = 240,35 (= 26·400/43,27), `run_meta.json` ghi `self_collected/clip`. Chỉ video tổng hợp, chưa có video điện thoại thật.

## Quyết định đã được người dùng duyệt (31/10)
- Hạ ảnh video về cạnh dài 640 trước khi đo blur và trước khi ghi ứng viên (không đo lại `V_ref` trên video điện thoại).
- Thêm khoá `video` vào `OWNERS` của `check_docs.py` (file ngoài danh sách được sửa; chỉ thêm một dòng).
- `video.focal35_mm = 26` là giá trị TẠM.

## Lệch so với kế hoạch / lưu ý
- Tiêu cự: chưa đọc EXIF/QuickTime (không có `ffprobe`/`av`/`pymediainfo` trong env `3d_metric`). Thay bằng `video.focal35_mm` hoặc `video.json` cạnh video. Muốn đọc tự động cần thêm dependency (chưa làm, cần xin).
- **Ảnh hưởng ngoài luồng**: `fusion/stage.py` tính `q_texture = grad / g_ref.vga` trên keyframe; keyframe video cạnh dài 640 nhưng tỉ lệ 16:9 (vd. 640×360) nên số pixel khác `vga_wide` 640×480. Cửa sổ gradient 15×15 là cục bộ nên ít ảnh hưởng, nhưng chưa kiểm.
- Video ở hướng ngang có tag rotation 0 (quay ngang) hay đứng (tag 90/270) đều qua `upright_rot`; ảnh quay đứng bằng điện thoại cho ra ảnh đứng (vd. 360×640). Cần kiểm trên video thật.

## Chưa làm / chưa kiểm chứng
- [chưa kiểm chứng trên video điện thoại thật]: chiều của tag rotation (theo mã OpenCV 4.8 `CAP_PROP_ORIENTATION_META` = góc xoay CW để đứng; test chỉ tiêm giá trị), timestamp VFR, `q_blur` thực tế của video (thang so với `V_ref`), tiêu cự thật.
- Test `timestamps()` rơi về fps metadata (`ts_from_meta`) chưa có (khó tạo video có timestamp xấu bằng OpenCV).
- Các stage sau `keyframe` (`sfm` …) chưa chạy trên scene tự thu (không chạy việc nặng GPU theo luật chung); `align` cần `ground_truth/scale_anchor.json` cho scene tự thu.
- Ứng viên giữ trong RAM (xem `# shortcut:` ở `extract_video_keyframes`).
