# WORKING_LOG.md — nhật ký đối chiếu với kế hoạch v4

- **Ngày tạo:** 2026-10-17
- **Nhánh:** M0a ở `feature/m0a-foundation` (theo dõi `origin/QuangDai_Work`); M0b ở `feature/m0b-data` (đã push lên `origin/QuangDai_Work` đến `3f1366f`, 18/10; nhánh chưa có upstream, chưa có PR)
- **Commit khi tạo file:** `6a7ea50` (commit chứa chính file này sẽ đứng ngay sau)
- **Chốt M0a:** 2026-10-17 14:2x, trên `c7fa757` (đã đồng bộ `origin/main` bằng merge `8629ac3`); commit cập nhật log M0a: `76d9353`
- **Cập nhật M0b (phần 1: chia scene và tải dữ liệu; đo `V_ref`/`G_ref`):** 2026-10-18, trên `feature/m0b-data` sau commit `06004c8`; commit chứa bản cập nhật này đứng ngay sau
- **Đối chiếu với:** kế hoạch **v4** (`docs/PLAN_v4.md`), PDF đề cương `Docs/TaiTao3D_Metric_3DMeph.pdf`
- **Quy tắc cập nhật:** `AGENTS.md` mục 10. Chỉ ☑ khi có bằng chứng (lệnh đã chạy + kết quả hoặc commit); dry-run không tính.

Ký hiệu: ☑ xong có bằng chứng · ☐ chưa làm · ◐ làm dở. Nhãn nguồn: [ĐC §x], [Suy luận], [Cần xác nhận], [chưa kiểm chứng].

## 1. Bảng tổng quan mốc

| Mốc | Trạng thái | Nhánh | Commit | Tiêu chí đạt (PLAN §10) | Đã đạt chưa, bằng chứng |
|---|---|---|---|---|---|
| M0a Nền tảng | **Xong** (code, đã đồng bộ `origin/main`); chưa mở PR, chưa merge vào `main` | `feature/m0a-foundation` (sao lưu `origin/QuangDai_Work`) | `5ffd429`, `6a7ea50`, `f00b2a3`, merge `8629ac3`, `82f7201`, `c7fa757` | `check_env.py` exit 0; `pytest` xanh cho vector không cần dữ liệu; `check_docs.py` exit 0 | **Đạt** (đo ngày 17/10 trên `c7fa757`, trong worktree `../3DMeph_m0a`): `pytest` **94 passed, 1 skipped** (skip = `test_colmap_compat`, worktree không có `data/processed`; ở thư mục chính 95 passed); `ruff check .` **All checks passed** (E, F, W, I); `check_docs.py` **OK** (18 README trong worktree, 41 khoá); `check_env.py` **exit 0, 0 lỗi, 3 cảnh báo**. **Chưa kiểm chứng:** `create_env.bat` mới chỉ chạy `--dry-run`; chưa có `pipeline.run`; chưa tải dữ liệu |
| M0b Dữ liệu | **Đang làm** (xong: chia scene, tải đủ 4 đợt, đo `V_ref`/`G_ref`, căn Faro scene dev; còn chấm mốc và đoạn test) | `feature/m0b-data` (sao lưu `origin/QuangDai_Work` = `3f1366f`; chưa có PR) | `9047112` (chia tập), `bf6d57a` (wrapper), `cdc9643` (retry), `06004c8` (log tải); `V_ref`/`G_ref`: `d92317a` | `splits.csv` 29/6/5, 0 venue ở 2 tập, chạy lại cho cùng held-out; mỗi đợt tải khớp dung lượng HEAD; residual căn Faro được log; `measurements.csv` ≥ 1 anchor + ≥ 12 đoạn test; `v_ref.vga`, `g_ref.vga` trong config | **Đạt 3/5 tiêu chí:** (3) `quality.v_ref.vga` = 205,69, `g_ref.vga` = 29,01 trong config (`measured_on: validation`, 6 scene, 2026-10-18); (1) `splits.csv` 29/6/5, 0 venue ở 2 tập, chạy lại cho cùng kết quả (`pytest` 138 passed, 18 test chia tập); (2) 4 đợt tải khớp HEAD (`--batch all --dry-run`: còn phải tải 0,00 GiB cả 4 đợt; CRC zip OK; header PLY khớp). **Chưa đạt:** `measurements.csv`. Residual căn Faro **đã đo, log và được duyệt** (xem checklist) |
| M1 Walking skeleton | Chưa bắt đầu (chờ M0b) | — | — | `python -m pipeline.run` exit 0, `model.glb` mở được bằng trimesh, `measure` đo được 1 đoạn, `run_meta.json` đủ | Chưa |
| M2 Chất lượng dữ liệu | Chưa bắt đầu | — | — | 40 ≤ N_kf ≤ 80; ≥ 90% keyframe đăng ký SfM; peak VRAM < 8 GB (có số đo) | Chưa |
| M3 Eval + ablation 1 scene | Chưa bắt đầu | — | — | `metrics.csv` đủ 6 cấu hình; test chỉ số qua; Δ% theo (31) | Chưa (hàm chỉ số + test đã có từ M0a, chưa có stage) |
| M4 Nhiều scene ARKit | Chưa bắt đầu | — | — | ngưỡng khoá ghi vào `default.yaml`; bảng val và held-out riêng | Chưa |
| M5 Replica + tự thu | Chưa bắt đầu (Replica hoãn, Q6) | — | — | 18 scene chạy một lần; báo theo 13 không gian | Chưa |
| M6 Ứng dụng và báo cáo | Chưa bắt đầu (ngoài phạm vi mốc đầu) | — | — | theo ĐC §21 "Ứng dụng" | Chưa |

## 2. Checklist chi tiết theo mốc

### M0a (PLAN §10 M0a)

- ☑ `requirements.txt`, `environment/baseline-requirements.txt`, `environment/create_env.bat`, `environment/check_env.py` (§8) — 2026-10-17 — `python environment/check_env.py`: 0 lỗi, 3 cảnh báo (open3d→pycolmap, cv2→pycolmap lỗi DLL đã biết; `vggt` chưa cài); commit `5ffd429`
- ◐ `create_env.bat` chạy thật — chỉ `environment\create_env.bat --dry-run` (in 5 lệnh, exit 0). **Chưa chạy thật**, cần xác nhận (có thể ảnh hưởng env đang dùng)
- ☑ `configs/default.yaml` (§4.9) — 41 khoá lá; `check_docs.py` khớp hai chiều với README — `5ffd429`
- ☑ `pipeline/common/{config,io,schema,geometry,quality}.py` (§4.9); `splits.py` thuộc M0b — `pytest` 95 passed
- ☑ Lõi toán: `alignment/ransac.py`, `fusion/fusion.py`, `plane_gate/gate.py`, `eval/metrics.py`, `vggt/{chunks,outputs}.py`, `keyframe/orientation.py`, `export/measure.py` (§4.4–§4.8) — test theo test vector §5 — `5ffd429`
- ☑ Test tương thích pycolmap 3.10 đọc model COLMAP 4.2 (`tests/test_colmap_compat.py`) — trên 2.377 điểm / 121 ảnh: trung vị |Δ| 0,0008 px, tương quan 0,99996 — `5ffd429`
- ☑ README gốc + README phụ 9 module + `environment/`, `configs/`, `scripts/`, `data/`, `outputs/`, `reports/`, `app/`, `docs/` (§7) — `check_docs.py`: OK (19 README) — `5ffd429`
- ☑ `scripts/check_docs.py` + `tests/test_check_docs.py` (§7d) — 10 test (1 bản sao sạch + 9 lỗi cố ý bị phát hiện), `pytest` 95 passed
- ☑ Sửa lỗi repo (§7c): `docs/` thay `thesis/` (CODEOWNERS, CONTRIBUTING, PR template), `gitattributes` → `.gitattributes`, `reports/stastitic` → `reports/statistics`, đường dẫn mặc định của `explore_dataset.py`/`validate_dataset.py`, `extract_sparse_keyframe.py` có `argparse` và `main()`, bỏ 3 thư mục `outputs/` rỗng — `5ffd429`
- ☑ `.gitignore`: `data/scenes/`, `.pytest_cache/` (`5ffd429`); `.env`, `*.pt`, `*.pth`, `*.safetensors`, `*.ckpt` (`6a7ea50`, `git check-ignore` xác nhận cả 5)
- ☑ Kiểm tra trước push: file lớn nhất trong HEAD 12,9 KB; không có tên file nhạy cảm; `git grep` bí mật không có kết quả
- ☑ Push `feature/m0a-foundation` → `origin/QuangDai_Work` (người dùng xác nhận, không force) — `git log origin/QuangDai_Work`: `6a7ea50`, `5ffd429`, `b14f47e`
- ☑ `AGENTS.md`, `CLAUDE.md`, `WORKING_LOG.md`, `docs/PLAN_v4.md` — 2026-10-17 — commit `f00b2a3`
- ☑ Đồng bộ `origin/main` (người dùng chọn **merge**, không rebase): xem trước `git merge-tree --write-tree` sạch, không xung đột; merge `8629ac3` không đổi file nào (`origin/main` không đổi file so với merge-base `b14f47e`); `git rev-list --left-right --count origin/main...HEAD` = `0 6`
- ☑ `ruff.toml` cố định (E, F, W, I; ignore E501, E701, E402) và đồng bộ lệnh ruff trong `AGENTS.md` — `82f7201`. Trước đó `ruff check .` (bộ luật mặc định, không có cấu hình) đỏ 70 lỗi kiểu dáng, không có lỗi logic
- ☑ Sửa 8 lỗi I001 bằng `ruff check --select I --fix` (8 file test, chỉ định dạng lại khối import) — `c7fa757`
- ☑ Bốn kiểm tra xanh trên `c7fa757` (xem mục 1) rồi push `QuangDai_Work`: `f00b2a3..c7fa757`, không force

### M0b (PLAN §4.0, §10 M0b)

- ☑ `scripts/select_scenes.py` (seed 42) → `data/splits.csv`, `data/splits.lock`, `data/rejected.csv` (§4.0b) — 2026-10-17 — 40 scene hợp lệ, 0 bị loại, 29/6/5, 38 venue; chạy lần 2 báo "trùng đúng bản đã khoá"; người dùng xác nhận danh sách; held-out 43828368, 44796254, 47331622, 47332314, 47332795 — `9047112`
- ☑ `pipeline/common/splits.py` + `compute_v_ref`/`compute_g_ref` (`quality.py`): `raise HeldoutError` khi gặp scene held-out (§4.0b mục 4, §4.9) — `tests/test_splits.py` 18 passed — `9047112`
- ☑ `data/README.md`, README gốc, `scripts/README.md`, `common/README.md` cập nhật theo chia tập thật — `9047112`; `data/README.md` còn mục "Dung lượng cần tải thêm (đã duyệt, chưa tải)" và dòng "42.348.620 điểm" cần sửa (xem mục 3, Q23)
- ☑ `scripts/download_arkitscenes.py` (§4.0c): `--batch`, `--dry-run`, bắt buộc `--yes`, tuần tự, resume, kiểm `Content-Length`, log CSV, chặn ổ thấp và held-out — `tests/test_download_arkitscenes.py` 25 passed — `bf6d57a`, sửa retry `cdc9643`
- ☑ Đợt A: `vga_wide` + intrinsics scene 42444738 — **đã tải thật** 2026-10-18 13:04 (34 s), 2 file 0,69 GiB, CRC zip OK, 1.804 ảnh / 1.804 file intrinsics (sửa 18/10: lúc đầu ghi 1.805 là số mục zip, gồm 1 mục thư mục)
- ☑ Đợt B: Faro visit 421267, 6 `.ply` + 6 `_pose.txt` — **đã tải thật**, 10,22 GiB, 12 file, `--dry-run` đối chiếu HEAD còn 0,00 GiB, header PLY khớp (42.348.620 / 41.467.500 / 40.935.479 điểm), mỗi `.ply` có `_pose.txt`, các cặp trùng pose giống hệt. Có 1 sự cố giữa chừng (mục 4, 18/10 13:15)
- ☑ `scripts/adapters.py` (gom `AssetReader`) (§4.0d) — 2026-10-18 — `tests/test_adapters.py` 19 passed (17 tổng hợp + 2 dữ liệu thật: header Faro 421267; `Trajectory` trên `.traj` thật và `highres_depth`); `validate_dataset.py` và `explore_dataset.py` nay `from adapters import AssetReader`: `validate_arkitscenes_scene(42444738)` cho kết quả **y hệt** trước và sau (so bằng `git stash`), `explore_arkitscenes_scene` chạy thật (stride 200); chưa commit
- ☑ `scripts/faro_align.py` + `scripts/faro_registration.py` (§4.0d) — 2026-10-18/19 — chạy thật trên 42444738; **người dùng duyệt bản ứng viên và `--commit` (Faro, voxel 1 cm)**: `ground_truth/faro/faro_to_scene.json` + `faro_scene_frame.ply` (1.244.413 điểm; đọc lại được bằng `adapters.iter_ply_xyz`). Pha 1: 3 cặp cùng pose trùng xyz hoàn toàn (0/124,75 triệu điểm khác), `.ply` đã ở hệ chung (trung vị 1–5 mm giữa scan khác pose; 0,17–11 m nếu áp `_pose.txt`). Quy ước camera OpenCV (trung vị tới mesh ARKit 2,84 cm; OpenGL 39 cm). Căn thô yaw 12,80° (điểm 0,997; đỉnh thứ hai 193° điểm 0,946), FPFH độc lập yaw 12,03°. ICP 4 mức đều hội tụ theo dung sai (mức 1 cm: 29 vòng, fitness 0,817). **Faro→scene: yaw 12,312°, nghiêng 0,381°, tịnh tiến (4,2866; 1,0696; −215,1603)**. Residual đích→Faro (khoảng cách mặt phẳng, cm): trung vị 1,59, p90 4,26, p95 5,28, p99 8,22, max 18,2; ≤5 cm 94%. Theo khung: trung vị 1,43, tệ nhất 6,35 (khung 0). Hai nửa chẵn/lẻ: độ dời điểm trong phòng rms 1,43 cm, p95 2,34, max 2,97 cm. Tự căn lại từng khung: rmse mặt phẳng trung vị 0,35 cm (trước 1,43), hiệu chỉnh trung vị 0,98° và 3,87 cm (max 12,3° và 21,8 cm; 3/104 khung không hội tụ) ⇒ **phần lớn residual đến từ pose từng khung (`.traj`/thời điểm), không phải từ phép căn chung**. `tests/test_faro_align.py` 16 passed. **Lưu ý độ chính xác (người dùng yêu cầu ghi):** (a) residual thật: trung vị 1,59 cm, p95 5,28 cm, max 18,2 cm; hai nửa chẵn/lẻ lệch rms 1,43 cm; (b) nguồn lệch chính là **pose từng khung** (`.traj`/thời điểm khung), không phải phép căn chung: tự căn lại từng khung giảm trung vị từ 1,43 xuống 0,35 cm; (c) **3/104 khung không hội tụ** khi tự căn lại (96, 97, 101: hiệu chỉnh 17–22 cm, 8–12°); (d) **nội suy pose so với pose gần nhất chưa phân định** (trung vị tới mesh 2,95 vs 2,84 cm; nội suy tốt hơn ở p90/p99/≤5 cm); (e) **sàn sai số cỡ 1–2 cm** khi dùng GT Faro đã căn cho Chamfer/F-score (δ = 5 cm) và định vị đầu mút trong hệ ARKit; chiều dài đo giữa hai điểm Faro **không** phụ thuộc phép căn; (f) `faro_scene_frame.ply` gồm cả điểm ngoài phòng nhìn qua cửa sổ (x từ −24,8 đến 20,9 m), eval cần cắt theo vùng phòng; (g) căn thô có đỉnh yaw thứ hai 193° (0,946 so với 0,997), FPFH độc lập đồng ý yaw ≈ 12°. Commit git: bước 2 (chưa push)
- ☐ `scripts/annotate_segments.py`: 1 anchor + ≥ 12 đoạn test → `ground_truth/measurements.csv`, `scale_anchor.json` (§4.0d)
- ☑ Đợt C: `vga_wide` + intrinsics 6 Validation — **đã tải thật** (13:25–13:30, 354 s), 12 file 9,53 GiB, CRC 12 zip OK, số ảnh = số file intrinsics ở cả 6 scene (2.316 / 1.640 / 9.034 / 4.354 / 3.179 / 4.283)
- ☑ Đợt D (thêm ngoài Q16): Faro 6 visit Validation 421380, 422785, 423477, 434659, 468711, 471952 — **đã tải thật** (13:33–14:12, 2.395 s ≈ 40 phút), 27 `.ply` + 27 `_pose.txt`, 46,21 GiB, 1.127.653.846 điểm, không phải thử lại, header PLY khớp, đủ `_pose.txt`
- ☑ Kiểm tra sau cả 4 đợt: `--batch all --dry-run` còn phải tải 0,00 GiB ở A, B, C, D; không còn `.part` trong `data/raw`; ổ D trống **25,16 GiB** (1024³)
- ☑ Đo `V_ref`, `G_ref` trên `vga_wide` của 6 Validation → `default.yaml` (kèm `measured_on`, `n_scenes`, `date`, `stride`) — 2026-10-18 — `python scripts/measure_reference.py --write-config` (1 phút 28 giây): **V_ref = 205,69, G_ref = 29,01**; hàm đo đọc `splits.csv` (kiểm `splits.lock`), `raise HeldoutError` trước khi đọc ảnh nếu gặp held-out; `tests/test_reference.py` 10 passed + 1 skipped (nay chạy); `d92317a`

### M1 (PLAN §10 M1)

- ☐ `pipeline/run.py` (CLI, `--from-stage/--to-stage`, `--variant`), `run_meta.json`, mã lỗi `E_TOO_FEW_KEYFRAMES`, `E_SFM_FAILED`
- ☐ Stage `keyframe` (trích 2 fps, xoay, lọc, ghi `keyframes.csv`, `camera.json`)
- ☐ Stage `sfm`, `mvs`, `signals` (CLI COLMAP 4.2; `observations.npz`, `e_reproj_map`, `sigma_depth`)
- ☐ Stage `vggt` (cài `vggt` editable `--no-deps`, tải trọng số VGGT-1B cần xin riêng)
- ☐ Stage `align` (đọc dữ liệu thật, ghi `chunk_XX_sim3.json`, `scale.json`)
- ☐ Stage `fuse` (lấy mẫu 6 tín hiệu tại `(i,k)`, `fused_points.ply`, `fusion_log.npz`)
- ☐ Stage `gate` (RANSAC mặt phẳng, hướng lên, nhãn, `refined_points.ply`)
- ☐ Stage `export` (Poisson → GLB, `measurements.json`)

### M2–M6 (PLAN §10)

- ☐ M2: khoá `keyframe.blur.q_drop`, `keyframe.overlap.*` trên 6 Validation; đo peak VRAM và tỷ lệ đăng ký SfM
- ☐ M3: stage `eval`, protocol đo chiều dài (thủ công trước, tự động snap 2 cm), bảng B0/B1/B3/Proposed/Ablation 1–2 trên scene dev
- ☐ M4: 6 Validation khoá ngưỡng; 5 held-out chạy đúng một lần
- ☐ M5: Replica (render, nhãn `preseg/semantic/glass.sur`), tự thu pilot R02
- ☐ M6: FastAPI + Unity, báo cáo

## 3. Việc chưa nằm trong mốc nào nhưng đã biết

- ☑ "42.348.620 điểm mỗi scan" chỉ đúng cho 1 file: đã sửa trong `data/README.md` và (Q23, người dùng đồng ý 18/10) trong `docs/PLAN_v4.md` (4 chỗ + ghi chú đầu file); số liệu đo bằng header PLY trên cả 33 file Faro, `332 + n×44 = kích thước` đúng 33/33
- ☐ Quyết định chính sách `reports/` trong `.gitignore` (Q11c)

## 4. Đã làm (theo thứ tự thời gian)

| Ngày giờ | Việc | File đổi | Kiểm tra đã chạy | Commit |
|---|---|---|---|---|
| 2026-10-17 (sáng–trưa) | Đọc PDF 52 trang, 3 HTML, README, script, dữ liệu; lập kế hoạch v1→v4 ở chế độ Plan; kiểm chứng dữ liệu bằng lệnh đọc (HEAD/Range) | không đổi file repo | `pdftotext`; so `eda_stats.csv` với PDF (9 scene `blur_min<10`, PDF ghi 8); HEAD dung lượng `vga_wide` và Faro; Range so 3 cặp Faro (cùng xyz, khác RGB) | — |
| 2026-10-17 | Cài `pytest` vào env `3d_metric` (đã được cho phép) | env conda | `pip install -r requirements.txt` OK (pytest 9.1.1) | — |
| 2026-10-17 12:57 | **M0a**: sửa lỗi repo, môi trường, `default.yaml`, `pipeline/common` + lõi toán 7 module, 12 file test, README gốc và phụ, `check_docs.py` | 68 file (`git show --stat 5ffd429`: 3917 dòng thêm, 65 xoá) | `pytest` 95 passed; `check_docs` OK; `check_env` exit 0; `create_env.bat --dry-run` exit 0; `ruff` All checks passed | `5ffd429` |
| 2026-10-17 13:16 | Vá `.gitignore` (`.env`, `*.pt`, `*.pth`, `*.safetensors`, `*.ckpt`), commit riêng | `.gitignore` | `git check-ignore -v` xác nhận 5 mẫu; kiểm tra trước push: không file nhạy cảm, lớn nhất 12,9 KB | `6a7ea50` |
| 2026-10-17 (sau 13:16) | Push `feature/m0a-foundation` → `origin/QuangDai_Work` (không force) | — | `git log origin/QuangDai_Work` = `6a7ea50`, `5ffd429`, `b14f47e` | — |
| 2026-10-17 (sau push) | Dọn nhánh cũ (người dùng xác nhận từng bước): xoá `feature/Update` (`b14f47e`), `feature/setup-data-scripts` (`5dd829a`) bằng `-d`; `feature/extract_frame` (cục bộ `fd4cd8b`, origin `f0bee5b`) và `feature/gitignore` (`6058077`, chỉ cục bộ) bằng `-D` sau khi được phép | không đổi file | `git branch -a` còn `main`, `feature/m0a-foundation`, `origin/QuangDai_Work`, `origin/main`; `git cat-file -t` xác nhận 3 hash vẫn tồn tại | — |
| 2026-10-17 13:37 | Tạo `AGENTS.md`, `CLAUDE.md`, `WORKING_LOG.md`, sao chép kế hoạch vào `docs/PLAN_v4.md`; kiểm chứng 3 điểm hở của kế hoạch (mục 5) | 4 file mới | `pytest` 95 passed; `ruff` xanh; `check_docs` OK; HEAD/Range đo Faro | `f00b2a3` |
| 2026-10-17 (sau 13:37) | Đo dung lượng Faro 38 visit bằng HEAD (chỉ đọc); sửa ước lượng ngân sách ổ đĩa (đơn vị GiB) | không đổi file repo | script ở scratchpad; 5/38 visit có file cùng kích thước, `_pose.txt` của 8/8 nhóm trùng giống hệt | — |
| 2026-10-17 | **Chốt M0a.** Tạo worktree `../3DMeph_m0a` (thư mục chính ở `feature/m0b-data` giữ nguyên); push `f00b2a3` lên `QuangDai_Work` (`6a7ea50..f00b2a3`) | không đổi file | `git status` sạch; không force | — |
| 2026-10-17 14:07 | Xem trước và thực hiện merge `origin/main` → `feature/m0a-foundation` | không đổi file (diff rỗng) | `git merge-tree --write-tree`: mã 0, không xung đột | `8629ac3` |
| 2026-10-17 14:13 | `ruff check .` đỏ 70 lỗi (bộ luật mặc định): thêm `ruff.toml`, sửa 8 lỗi I001, cập nhật lệnh ruff trong `AGENTS.md` | `ruff.toml`, `AGENTS.md`, 8 file `tests/*.py` | sau sửa: `pytest` 94 passed 1 skipped; `ruff check .` pass; `check_docs` OK; `check_env` exit 0 | `82f7201`, `c7fa757` |
| 2026-10-17 14:2x | Push `QuangDai_Work` `f00b2a3..c7fa757` (không force); cập nhật log này | `WORKING_LOG.md` | `git log origin/QuangDai_Work` | `c7fa757`; log: `76d9353` |
| 2026-10-17 | Đưa M0a vào `feature/m0b-data` bằng merge `--no-ff` (không rebase, không stash); dọn worktree `../3DMeph_m0a`; soạn mô tả PR M0a (chỉ in ra, chưa mở PR) | các file M0a | trước và sau merge: 7 hash SHA-256 file M0b chưa commit trùng nhau; `pytest` 113 passed, `ruff`, `check_docs` xanh | `c2483e3` |
| 2026-10-17 | **M0b phần 1:** `select_scenes.py` + `splits.py` + `compute_v_ref/g_ref` + 18 test; chia 29/6/5, seed 42; người dùng xác nhận danh sách held-out | `scripts/select_scenes.py`, `pipeline/common/{splits,quality}.py`, `tests/test_splits.py`, `data/splits.csv`, `data/splits.lock`, `data/rejected.csv`, README | `pytest` 113 passed; `ruff`, `check_docs` xanh; chạy lần 2 báo trùng khoá | `9047112` |
| 2026-10-17 | `scripts/download_arkitscenes.py` + 20 test; `--dry-run` 4 đợt khớp số đã báo (A 0,69 / B 10,22 / C 9,53 / D 46,21 GiB); đo ổ: trống 91,81 GiB (lần đo trước 55,09 GiB, ổ đã được giải phóng, không do tôi) | `scripts/download_arkitscenes.py`, `tests/test_download_arkitscenes.py`, README, `AGENTS.md` | `pytest` 133 passed; `ruff`, `check_docs` xanh; không tạo file trong `data/raw` | `bf6d57a` |
| 2026-10-18 13:04 | Đợt A tải nền (người dùng xác nhận "tải đợt A, B, C, D") | `data/raw/arkitscenes/Training/42444738/vga_wide*.zip` | `exit=0`; 2 file khớp `Content-Length`; CRC zip OK (1.805 mục zip = 1.804 ảnh + 1 thư mục). Kết quả lượt đó bị mất khi phiên đổi; xác nhận lại bằng log ở scratchpad phiên cũ (`dl_A.log`, `download_log.csv`) | — |
| 2026-10-18 13:08–13:15 | Đợt B: 5/6 `.ply` + 5 `_pose.txt` xong; **lỗi thật** ở `169975.ply` (36%): `curl mã 56: schannel: server closed abruptly`, kết nối đứng ~2,5 phút rồi mới báo lỗi; wrapper dừng đúng thiết kế, giữ `.part` (648.453.686 B). Thông báo tác vụ nền ghi "exit code 0" là mã của lệnh `tail`, không phải của wrapper (log ghi `exit=1`) | — | `dl_B.log`; kiểm tra dữ liệu đã tải: 5 file đúng kích thước, header khớp | — |
| 2026-10-18 | **Sửa wrapper** sau sự cố (người dùng chọn): `--retry-all-errors`, `--speed-limit 10240 --speed-time 30`, thử tối đa `--max_attempts` 5 lần mỗi file (resume giữa các lần), +5 test | `scripts/download_arkitscenes.py`, `tests/test_download_arkitscenes.py`, `scripts/README.md` | `pytest` 138 passed; `ruff`, `check_docs` xanh | `cdc9643` |
| 2026-10-18 13:24 | Resume đợt B: bỏ qua 10 file đã xong, nối tiếp `169975.ply` từ `.part` rồi tải `169975_pose.txt` | — | `WRAPPER_EXIT=0`; 12 file; `--dry-run` HEAD còn 0,00 GiB; header PLY, `_pose.txt`, không còn `.part` | — |
| 2026-10-18 13:25–13:30 | Đợt C tải nền (6 Validation) | `Validation/<id>/vga_wide*.zip` ×6 | `WRAPPER_EXIT=0`; 12 file 9,53 GiB; CRC 12 zip OK | — |
| 2026-10-18 13:33–14:12 | Đợt D tải nền (Faro 6 visit Validation, 54 file) | `laser_scanner_point_clouds/{421380,422785,423477,434659,468711,471952}/` | `WRAPPER_EXIT=0`; 0 lần thử lại; 27 `.ply` + 27 `_pose.txt`; header PLY khớp (1.127.653.846 điểm); `--batch all --dry-run` còn 0,00 GiB cả 4 đợt; ổ trống 25,16 GiB | — |
| 2026-10-18 | Cập nhật log này, `AGENTS.md`, `scripts/README.md`, `data/README.md` theo trạng thái tải thật | `WORKING_LOG.md` và 3 file tài liệu | `check_docs` (xem commit) | `06004c8` |
| 2026-10-18 | **Đo `V_ref`, `G_ref`** (theo PLAN §4.1): `pipeline/common/reference.py` (`scene_stats`, `measure_reference`), `quality.mean_window_gradient`, `scripts/measure_reference.py`, `tests/test_reference.py`; đo thật 6 scene Validation `vga_wide`, mỗi 10 khung (2.483 khung mẫu), rồi ghi `default.yaml`. Kết quả (trung vị của trung bình mỗi scene): **V_ref 205,69; G_ref 29,01** (42445022: blur 126,2 / texture 22,1; 42897566: 201,4 / 30,8; 42897599: 386,5 / 44,0; 42898849: 210,0 / 28,8; 45662981: 163,5 / 28,0; 47204552: 283,1 / 29,2). So với 581 (lowres, 40 scene): −64,6%. Cùng 6 scene ở `lowres_wide` (EDA) trung vị 635,3 → vga/lowres = 0,32 lần | `pipeline/common/{reference,quality}.py`, `scripts/measure_reference.py`, `configs/default.yaml`, 3 README, 2 file test | `pytest` **150 passed**; `ruff` All checks passed; `check_docs` OK (19 README, 49 khoá); chỉ đọc raw (không ghi vào `data/raw`) | commit kế tiếp |
| 2026-10-18 | Xử lý việc treo: chạy lại 4 kiểm tra (`pytest` 150 passed; `ruff check .` All checks passed; `check_docs` OK 19 README/49 khoá; `check_env` exit 0, 0 lỗi 3 cảnh báo); xác nhận `splits.csv` 29/6/5, `splits.lock` hợp lệ (`load_splits` kiểm khoá), seed 42, 0 venue ở 2 tập, held-out 43828368, 44796254, 47331622, 47332314, 47332795; ruff.toml (E,F,W,I) và 62 lỗi hoãn đã ghi ở mục 6 dòng 9 từ trước (không đổi); đối chiếu độ nhạy V_ref/G_ref bỏ từng scene; push `QuangDai_Work` `76d9353..d92317a` (không force) | `WORKING_LOG.md` | như trên | `d92317a` (đã push); log: `3f1366f` |
| 2026-10-18 | Push `3f1366f` lên `origin/QuangDai_Work` theo yêu cầu (`git push origin 3f1366f:refs/heads/QuangDai_Work`, fast-forward `d92317a..3f1366f`, không force; chưa mở PR) | không đổi file | `git merge-base --is-ancestor` trước push; `git rev-parse origin/QuangDai_Work` = `3f1366f` sau push | — |
| 2026-10-18 | Đọc header PLY của cả 33 file Faro đã tải (chỉ đọc 2 KB đầu mỗi file): `332 + n×44 = kích thước` đúng 33/33; số điểm 39.826.951–43.422.282; tổng 1.377.157.044 (421267: 249.503.198; Validation: 1.127.653.846). Phát hiện `data/README.md` ghi nhầm đơn vị: "1,863 GiB" phải là 1,863 GB (= 1,735 GiB) | không đổi file | script `python -I` ở stdin | — |
| 2026-10-18 | **Commit tài liệu** (theo yêu cầu, trước khi code M0b phần 2): sửa các chỗ lệch giữa tài liệu và thực tế (`AGENTS.md`: 150 passed, 49 khoá, ổ D 25 GiB, nhánh hiện tại, đợt A–D; `README.md`: `vga_wide`/Faro đã tải, `V_ref`/`G_ref` đã đo, M0b đang làm; `data/README.md`: Faro đã tải, 1.804 ảnh, đơn vị GB/GiB; `WORKING_LOG.md`: hash `d92317a`, 1.804 ảnh) và Q23 (`docs/PLAN_v4.md`: 4 chỗ số điểm Faro + ghi chú đầu file) | `AGENTS.md`, `README.md`, `data/README.md`, `docs/PLAN_v4.md`, `WORKING_LOG.md` | `pytest` 150 passed; `ruff` All checks passed; `check_docs` OK (19 README, 49 khoá) | commit `docs:` ngay sau `3f1366f` (xem `git log`) |
| 2026-10-18 | **M0b phần 2, bước 1:** `scripts/adapters.py` (`AssetReader`, `Trajectory` nội suy, intrinsics + đổi tỉ lệ, `unproject_depth`, PLY Faro theo chunk, `list_scans`, `voxel_downsample_stream`), `tests/test_adapters.py`; gom `AssetReader` ở `validate_dataset.py`, `explore_dataset.py` (xoá lớp trùng, bỏ import thừa theo `ruff --fix`) | `scripts/adapters.py`, `tests/test_adapters.py`, `scripts/validate_dataset.py`, `scripts/explore_dataset.py`, `scripts/README.md` | `pytest` **169 passed**; `ruff` All checks passed; `check_docs` OK (19 README, 49 khoá); so sánh kết quả hàm validate trước/sau; chạy thật hàm explore | chưa commit |
| 2026-10-18/19 | **M0b phần 2, bước 2:** `scripts/faro_align.py` + `faro_registration.py` + `tests/test_faro_align.py`; chạy thật pha 1 và căn trên 42444738 (lần 1 ra 332 s; lần 2 384 s sau khi sửa thống kê). **Lỗi tôi mắc và đã sửa:** lần 1 so "hai nửa" bằng vector tịnh tiến, bị lever arm (gốc Faro z ≈ 215 m: xoay 0,26° ⇒ 91 cm) làm vô nghĩa; nay dùng độ dời của điểm Faro trong phòng (`transform_difference(..., pts)`, có test) | `scripts/faro_align.py`, `scripts/faro_registration.py`, `tests/test_faro_align.py`, `scripts/README.md`, `data/README.md` | `pytest` **185 passed**; `ruff` All checks passed; `check_docs` OK; chạy thật như checklist; sau khi người dùng duyệt: `faro_align.py --commit --source faro --gt-voxel 0.01` (ghi 1.244.413 điểm); đầu ra `data/scenes/arkitscenes/42444738/ground_truth/faro/` (gitignored) | commit `feat(m0b): faro_align` (xem `git log`) |

**Hash khôi phục các nhánh đã xoá:** `feature/Update` `b14f47e3c9c52c556c792fa9ef07b8abc48f0d39` · `feature/setup-data-scripts` `5dd829aac0cf078ea3fc2b6b7e56a4ab09988f16`
· `feature/extract_frame` cục bộ `fd4cd8b28e7383d7003b7d23504a2d103836f659`, origin `f0bee5b8a9dac9e65064745d5a8204e4f1271b39` · `feature/gitignore` `60580776d5ddcb970978a2b2144278d008069f10`.
Khôi phục: `git branch <tên> <hash>` rồi (nếu cần) `git push origin <tên>`.

## 5. Chưa làm được / đang bị chặn

| Việc | Lý do | Cần gì để gỡ | Ai quyết định |
|---|---|---|---|
| M0b phần 2 và M1 | M0b còn: `adapters.py`, `faro_align.py`, `annotate_segments.py` (1 anchor + ≥ 12 đoạn test); `V_ref`/`G_ref` **đã đo**. M1 bị chặn đến khi xong M0b (cần căn Faro) [PLAN §10, Q20]. Dữ liệu đã sẵn sàng | làm tiếp M0b theo checklist | người dùng chọn thời điểm |
| `create_env.bat` chạy thật | chỉ mới `--dry-run`; chạy thật cài lại gói, `--recreate` xoá env | xác nhận trước khi chạy | người dùng |
| Gói `vggt` và trọng số VGGT-1B chưa có trong env | `check_env.py` cảnh báo "chưa import được vggt"; trọng số chưa trong `~/.cache/huggingface/hub`, kích thước [chưa kiểm chứng] | cài `pip install -e <vggt> --no-deps`; xin tải trọng số | người dùng |
| **(a) Faro held-out chưa tải và chưa vừa ổ** | **Validation đã giải quyết:** người dùng chọn Faro đầy đủ (không `highres_depth`, không giảm một nửa) và đã tải (đợt D, 46,21 GiB). **Còn lại:** Faro 5 held-out (visit 437534, 464746, 466906, 471674, 469226) = **24,44 GiB** đầy đủ (đo HEAD 17/10), chưa tải theo quyết định "quyết sau khi có `splits.csv` và số đo thật". Ổ D trống **25,16 GiB**: tải hết sẽ chỉ còn dư **0,72 GiB**, dưới ngưỡng 15 GiB của wrapper (wrapper sẽ từ chối). Không đợt nào của wrapper có held-out (bị chặn bằng mã) | giải phóng ≥ 14,3 GiB nữa (24,44 + 15 − 25,16), hoặc dùng `highres_depth` cho held-out, hoặc hạ `--min_free_gib` (cần cân nhắc dữ liệu trung gian của M1–M4) | người dùng [Cần xác nhận] |
| **(b) Ngưỡng keyframe cần ở M1 nhưng chỉ khoá ở M2** | `keyframe.blur.q_drop` đang `null` (PLAN §4.1: "khoá trên 6 Validation"; §10 M2: khoá blur/overlap). Stage `keyframe` của M1 lọc blur nên cần một giá trị; `require()` sẽ `raise` khi `null`. `keyframe.overlap.max/min` đã có mặc định (0,8/0,6, [Suy luận]) | chọn giá trị tạm ghi rõ "tạm, M1" (ví dụ chỉ loại q_blur rất thấp theo ví dụ §7.3: 0,005 loại, 0,35 giữ), hoặc đo sớm trên 6 Validation sau đợt C | người dùng [Cần xác nhận] |
| **(c) Số điểm mỗi scan Faro** | **Đã kiểm lại, kế hoạch/README ghi sai:** "mỗi scan 42.348.620 điểm" chỉ đúng cho file 1,863 GB. Đo bằng header PLY (Range): `169892` 42.348.620; `169895` 41.467.500; `169897` 40.935.479 (cả ba khớp `332 + n×44 = kích thước`). Ba scan ≈ 124,75 triệu điểm | **Đã giải quyết 18/10:** `data/README.md` và `docs/PLAN_v4.md` đã sửa; số điểm 33 file từ 39.826.951 đến 43.422.282 | — |
| PR #4 | không có `gh` trên máy; không thấy merge commit của #4 trên `origin/main` (#1, #2, #3, #6, #7, #8 đã merge) | xem trên GitHub | người dùng |
| `main` cục bộ cũ | `main` cục bộ vẫn ở `bbc68bc`, cũ hơn `origin/main` `8a56a9b` (nhánh M0a đã đồng bộ bằng merge `8629ac3`, không còn lệch) | `git switch main && git pull --ff-only` (chưa làm, chờ xác nhận) | người dùng |
| PR "M0a: nền tảng" | chưa mở theo yêu cầu; mô tả PR soạn ở bước cuối của lần chốt M0a (chỉ in ra, không lưu file) | người dùng dán mô tả và mở PR | người dùng |
| Chưa kiểm chứng | `create_env.bat` chỉ chạy `--dry-run`, chưa chạy thật; **chưa có `pipeline.run`** (không có stage nào chạy trên dữ liệu thật). Dữ liệu đợt A–D **đã tải** (xem mục 2). **Chưa kiểm chứng:** ý nghĩa xoay/tịnh tiến trong `_pose.txt` (đã xem 3 dòng 4×4, tịnh tiến ở dòng cuối); xyz của toàn bộ điểm các cặp trùng pose (mới kiểm 100.000 điểm đầu của 3 cặp visit 421267) | M0b (`faro_align.py`), M1 | người dùng |
| Ổ D còn ít | sau cả 4 đợt chỉ còn **25,16 GiB** trống (88% dùng) để làm M0b phần 2, M1 (COLMAP dense, VGGT, GLB), kể cả dữ liệu trung gian chưa ước tính | theo dõi ổ; giải phóng thêm trước M1 nếu dữ liệu trung gian lớn | người dùng |
| Đợt A được tải ở lượt trước, kết quả mất khi phiên đổi | không mất dữ liệu; đã đối chiếu lại bằng log scratchpad phiên `573b717e` và CRC zip | — | — |
| Replica | thiếu `preseg`, `semantic`, `glass.sur`; Habitat-Sim chưa cài, khả năng cài trên Windows [chưa kiểm chứng] | Q6: hoãn đến M5 | người dùng |
| `setup_3dmeph_structure.sh` | nằm **ngoài** repo (`3D_Metric/`), còn tạo `thesis/`, `zotero/` và ghi đè README bằng bản cũ nếu chạy lại | sửa hoặc bỏ file này | người dùng |
| Chưa kiểm chứng (từ kế hoạch) | peak VRAM thật; chất lượng MVS/Poisson trên 640×480; có lệnh `unzip` hay không (wrapper không giải nén nên không còn cần) | làm khi tới mốc liên quan | — |

## 6. Lệch so với kế hoạch

| # | Chỗ lệch | Lý do | Người dùng đã đồng ý? |
|---|---|---|---|
| 1 | `data/README.md` viết lại ở M0a (kế hoạch xếp ở M0b (i)) | README cũ có thông tin sai (`selected_scenes.csv` nằm đâu, danh sách scene); ghi `splits.csv` là "kế hoạch, sinh ở M0b" | Chưa hỏi riêng |
| 2 | `default.yaml` có thêm nhóm `colmap.*` và `export.*` ngoài khung ở PLAN §4.9 | module cần tham số; mô tả ở README module | Chưa hỏi riêng |
| 3 | Lõi toán của 7 module có ngay ở M0a (kế hoạch nói "common/" và test các vector không cần dữ liệu) | test vector cần hàm tương ứng | Chưa hỏi riêng |
| 4 | Dung sai `test_colmap_compat.py` đặt theo đo thật (median 2e-3 px, tương quan > 0,999) thay vì khớp từng điểm | COLMAP lưu `point3D.error` ở bước tối ưu trước; khác nhỏ 0,04% | Chưa hỏi riêng |
| 5 | Cài `pytest` vào env `3d_metric` | cần để chạy test | **Có** (người dùng chọn "Có, cài vào 3d_metric") |
| 6 | `docs/PLAN_v4.md` có thêm 3 dòng ghi chú đầu file so với bản gốc trong thư mục plans | cho agent khác biết trạng thái thật | Theo yêu cầu "sao chép"; ghi chú thêm là của tôi, chưa hỏi riêng |
| 7 | Q11: làm 2/3 (đổi `statistics`, `.gitattributes`); chính sách `reports/` để nhóm quyết | đúng như người dùng ghi ("riêng chính sách reports/ hỏi nhóm") | Có |
| 8 | Dọn nhánh: dùng `-D` cho `feature/extract_frame` và `feature/gitignore` | `-d` từ chối vì so với nhánh hiện tại; người dùng cho phép `-D` | **Có** |
| 9 | **Bộ luật ruff chốt ở E, F, W, I** (thêm `ruff.toml`); **hoãn có chủ ý** UP, PLW1510, RUF, C4 | `ruff check .` không cấu hình dùng bộ luật mặc định rộng của ruff 0.16.3: **70 lỗi** trước khi chốt cấu hình, không có lỗi logic. Phân loại: UP006 25, UP035 16, UP045 5, UP037 2 (= **UP 48**); PLW1510 **4**; RUF059 4, RUF100 4, RUF007 1 (= **RUF 9**); C408 **1** (C4); I001 **8** (đã sửa, `c7fa757`). Còn **62 lỗi hoãn** (48 + 4 + 9 + 1) | **Có** (người dùng chọn tạo `ruff.toml` và chỉ sửa I001) |
| 10 | `ruff.toml` ignore thêm E501, E701, E402 và `line-length = 120` ngoài bộ luật "E, F, W, I" | giữ đúng cấu hình đã chạy xanh từ đầu: README/docstring tiếng Việt dài (E501), property một dòng trong `io.py` (E701), `sys.path.insert` trước import trong `scripts/` (E402) | Chưa hỏi riêng |
| 11 | Đồng bộ `origin/main` bằng **merge** (`8629ac3`), không rebase | rebase buộc force-push `QuangDai_Work` vì 3 commit đã push | **Có** (người dùng chọn merge) |
| 12 | Chốt M0a trong worktree `../3DMeph_m0a` thay vì chuyển nhánh ở thư mục chính | thư mục chính có file M0b chưa commit (`select_scenes.py`, `data/splits.*`, `splits.py`, test) | **Có** (theo yêu cầu) |
| 13 | **Thêm "Đợt D"** ngoài Q16: Faro 6 visit Validation (46,21 GiB). **GT cho Validation = Faro đầy đủ**: bỏ phương án `highres_depth` và bỏ Q18 "giảm một nửa" cho Validation | chỉ 5/38 visit có file trùng nên giảm một nửa gần như không tiết kiệm (Validation 46,21 → 44,48 GiB); quyết định của người dùng | **Có** |
| 14 | Faro held-out **chưa tải**; held-out chọn **chỉ bằng seed 42**, không đổi theo dung lượng Faro | quyết định của người dùng; danh sách đã xác nhận | **Có** |
| 15 | Wrapper **không gọi `download_file`/`download_laser_scanner_point_clouds`** của `download_data.py` như PLAN §4.0c; chỉ dùng quy ước URL và tên file | `download_file` chạy `curl` không `-C -` (không resume), không kiểm `Content-Length`; yêu cầu của người dùng cần cả hai | Chưa hỏi riêng (đã nêu ở báo cáo Bước 3) |
| 16 | Wrapper có thêm **vòng thử lại** (`--retry-all-errors`, `--speed-limit/--speed-time`, `--max_attempts`, `--retry_wait`) ngoài kế hoạch | sự cố curl mã 56 ở đợt B (mục 4, 18/10 13:15) | **Có** (người dùng chọn sửa wrapper) |
| 17 | Chia tập 29/6/5 (kế hoạch v4 Q15) thay vì 30/5/5 của PDF Hình 9 | 6 Validation chính thức làm val; đã ghi ở PLAN v4 | **Có** (Q15) |
| 18 | `--log` của lệnh tải ghi vào scratchpad (theo yêu cầu) thay vì `data/raw/arkitscenes/download_log.csv` mặc định; log mất theo scratchpad khi hết phiên | yêu cầu "ghi log vào scratchpad" | **Có** |
| 19 | `default.yaml` thêm 8 khoá lá dưới `quality.v_ref.*` / `quality.g_ref.*` (`measured_on`, `n_scenes`, `date`, `stride`) ngoài khung PLAN §4.9; tổng 49 khoá | yêu cầu "ghi kèm measured_on, n_scenes, ngày đo"; `stride` thêm để lần đo tái lập được | **Có** (theo yêu cầu; riêng `stride` chưa hỏi) |
| 20 | **`G_ref` = trung vị qua scene của gradient cửa sổ 15×15 trung bình mỗi scene** (toán tử Sobel 3×3 không chuẩn hoá + box 15×15, cùng toán tử với `q_texture`) | PDF (20) chỉ nói "trung vị trên Validation", không nói đơn vị lấy trung vị và không nói toán tử gradient; chọn cùng cách với V_ref theo yêu cầu "trung vị của trung bình từng scene" [Suy luận] | Chưa hỏi riêng về toán tử |
| 21 | Số ảnh mỗi scene Validation ghi ở đợt C (2.316 / 1.640 / 9.034 / 4.354 / 3.179 / 4.283) là số **mục** trong zip, gồm 1 mục thư mục; số ảnh PNG thật là 2.315 / 1.639 / 9.033 / 4.353 / 3.178 / 4.282 (khớp bảng đo `V_ref`) | đếm lại khi đo; số mục intrinsics đã đối chiếu ở đợt C có thể cũng cần tính lại, [chưa kiểm chứng] | — |
| 22 | Số ảnh scene dev đợt A ghi 1.805, thực là **1.804** PNG (và 1.804 `.pincam`); 1.805 là số mục zip. Đã đếm lại 18/10 cho cả 7 zip `vga_wide` (6 Validation khớp dòng 21) | cùng lỗi đếm mục với dòng 21 | — (sửa lỗi ghi chép) |
| 23 | `docs/PLAN_v4.md` (bản sao "nguyên văn") **bị sửa** số điểm Faro + ghi chú đầu file; `data/README.md` sửa đơn vị 1,863 GiB → 1,863 GB | Q23 | **Có** (Q23) |
| 24 | `highres_depth` của scene dev có **104 ảnh**, không phải 105 (PLAN §4.0d: "105 khung"); 105 là số mục zip, gồm 1 thư mục. Cùng lỗi đếm mục như dòng 21 và 22 | đếm lại khi viết test (`tests/test_adapters.py`) | — (sửa lỗi ghi chép) |
| 25 | Sửa `validate_dataset.py` và `explore_dataset.py` (ngoài danh sách file của kế hoạch M0a): chỉ xoá lớp `AssetReader` trùng, thêm `from adapters import AssetReader`, bỏ import thừa | PLAN §4.0d "gom `AssetReader`" | **Có** (người dùng chọn "Có, sửa tối thiểu hai script") |
| 26 | Thêm `scripts/faro_registration.py` (hàm thuần cho căn thô/ICP, để test được) ngoài danh sách file của kế hoạch; ICP tự cài (numpy/scipy) thay vì Open3D để biết rõ số vòng lặp và tiêu chí hội tụ | tiêu chí "không hội tụ thì dừng" cần tín hiệu hội tụ rõ ràng | Chưa hỏi riêng |
| 27 | Căn Faro dùng ràng buộc trọng lực (cả Faro và scene Z-up đã đo): căn thô 4 DoF (yaw + FFT cho xy; tz theo histogram độ cao) rồi ICP 6 DoF, thay vì chỉ "khởi tạo từ Z-up và `_pose.txt`" như PLAN §4.0d; `_pose.txt` **không** áp (giả thuyết A, pha 1) | `_pose.txt` là vị trí máy quét, `.ply` đã ở hệ chung | Theo kế hoạch đã duyệt |
| 28 | Cloud đích dựng từ `highres_depth` với intrinsics ×3 từ `vga_wide_intrinsics` và pose gần nhất (`nearest`), chọn bằng trung vị khoảng cách tới mesh ARKit (2,84 cm so với 2,95 cm của nội suy; nội suy tốt hơn ở p90/p99/≤5 cm) | không có intrinsics riêng cho `highres_depth`; chênh nhỏ giữa nearest và interp chưa phân định | Chưa hỏi riêng |

## 7. Câu hỏi còn mở

**Nhắc người dùng trước khi bắt đầu M1** (18/10: "để sau"): Q22, Q29, Q24, Q27, Q11c, Q25.

| # | Câu hỏi | Mặc định nếu không trả lời |
|---|---|---|
| Q8 | Ngưỡng `blur.q_drop` và cách tính overlap | Khoá trên 6 Validation ở M2 (xem mục 5 điểm b: M1 cần giá trị tạm) |
| Q11c | Chính sách `reports/` trong `.gitignore` (commit CSV hay không) | Hỏi nhóm; giữ nguyên (không commit) |
| ~~Q21~~ | ~~Faro cho Validation~~ **Đã chốt:** Faro đầy đủ, đã tải (đợt D). Còn: Faro 5 held-out (24,44 GiB) với ổ trống 25,16 GiB và ngưỡng dư 15 GiB (mục 5 điểm a) | Chưa tải; dùng `highres_depth` làm dự phòng |
| Q22 | Giá trị tạm của `keyframe.blur.q_drop` cho M1 (mục 5 điểm b) | Chưa chạy M1 cho tới khi có giá trị |
| ~~Q23~~ | ~~Sửa số điểm Faro trong `docs/PLAN_v4.md`~~ **Đã sửa** 18/10 theo yêu cầu | — |
| Q24 | Thêm kiểm tra tiêu đề `WORKING_LOG.md` vào `scripts/check_docs.py` (AGENTS.md mục 10, điểm 7) | Chưa thêm |
| Q25 | Trạng thái PR #4; tên GitHub thật thay `@username1–4` trong CODEOWNERS | Giữ placeholder |
| ~~Q26~~ | ~~Merge hay rebase với `origin/main`~~ **Đã chốt: merge** (`8629ac3`). Còn lại: có cập nhật `main` cục bộ không (xem mục 5) | — |
| Q27 | Khi nào bật lại UP, PLW1510, RUF, C4 (62 lỗi, mục 6 dòng 9): ở M0a hay các mốc sau, sửa tay hay `--fix` | Hoãn; không bật |
| ~~Q28~~ | ~~Push `feature/m0b-data` lên `QuangDai_Work`~~ **Đã push** 2026-10-18 theo yêu cầu (fast-forward `76d9353..d92317a`, không force; `git rev-parse origin/QuangDai_Work` = `d92317a`). Nhánh `feature/m0b-data` chưa có PR | — |
| Q29 | Chấp nhận ổ D chỉ còn 25,16 GiB khi bắt đầu M1, hay giải phóng thêm trước (và Faro held-out cần ≥ 39,4 GiB trống: 24,44 + 15) | Chưa tải held-out |
