# WORKING_LOG.md — nhật ký đối chiếu với kế hoạch v4

- **Ngày tạo:** 2026-10-17
- **Nhánh:** `feature/m0a-foundation` (theo dõi `origin/QuangDai_Work`)
- **Commit khi tạo file:** `6a7ea50` (commit chứa chính file này sẽ đứng ngay sau)
- **Đối chiếu với:** kế hoạch **v4** (`docs/PLAN_v4.md`), PDF đề cương `Docs/TaiTao3D_Metric_3DMeph.pdf`
- **Quy tắc cập nhật:** `AGENTS.md` mục 10. Chỉ ☑ khi có bằng chứng (lệnh đã chạy + kết quả hoặc commit); dry-run không tính.

Ký hiệu: ☑ xong có bằng chứng · ☐ chưa làm · ◐ làm dở. Nhãn nguồn: [ĐC §x], [Suy luận], [Cần xác nhận], [chưa kiểm chứng].

## 1. Bảng tổng quan mốc

| Mốc | Trạng thái | Nhánh | Commit | Tiêu chí đạt (PLAN §10) | Đã đạt chưa, bằng chứng |
|---|---|---|---|---|---|
| M0a Nền tảng | **Xong** (code); chưa merge vào `main` | `feature/m0a-foundation` (sao lưu `origin/QuangDai_Work`) | `5ffd429`, `6a7ea50` | `check_env.py` exit 0; `pytest` xanh cho vector không cần dữ liệu; `check_docs.py` exit 0 | **Đạt**: check_env exit 0 (0 lỗi, 3 cảnh báo); pytest 95 passed; check_docs OK (19 README, 41 khoá); ruff All checks passed. **Chưa đạt phần phụ:** `create_env.bat` mới chỉ chạy `--dry-run` |
| M0b Dữ liệu | Chưa bắt đầu | — | — | `splits.csv` 29/6/5, 0 venue ở 2 tập, chạy lại cho cùng held-out; mỗi đợt tải khớp dung lượng HEAD; residual căn Faro được log; `measurements.csv` ≥ 1 anchor + ≥ 12 đoạn test; `v_ref.vga`, `g_ref.vga` trong config | Chưa |
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
- ☑ `AGENTS.md`, `CLAUDE.md`, `WORKING_LOG.md`, `docs/PLAN_v4.md` — 2026-10-17 — commit kế tiếp (xem mục 4)

### M0b (PLAN §4.0, §10 M0b)

- ☐ `scripts/select_scenes.py` (seed 42) → `data/splits.csv`, `data/splits.lock`, `rejected.csv` (§4.0b)
- ☐ `pipeline/common/splits.py`: đọc `splits.csv`, `raise` khi tính ngưỡng trên scene held-out (§4.0b mục 4, §4.9)
- ◐ Viết lại `data/README.md` (§7c) — đã viết lại ở M0a (xem mục 6, lệch #1); phần `splits.csv` còn là "kế hoạch"
- ☐ `scripts/download_arkitscenes.py` (wrapper, không giải nén, `--dry-run`, bắt buộc `--yes`) (§4.0c)
- ☐ Đợt A: `vga_wide` + intrinsics scene 42444738 (≈ 0,74 GB) — đã duyệt (Q16), chưa tải
- ☐ Đợt B: Faro visit 421267, 6 file (≈ 10,98 GB) — đã duyệt (Q16, Q18), chưa tải
- ☐ `scripts/adapters.py` (gom `AssetReader`) (§4.0d)
- ☐ `scripts/faro_align.py` (§4.0d)
- ☐ `scripts/annotate_segments.py`: 1 anchor + ≥ 12 đoạn test → `ground_truth/measurements.csv`, `scale_anchor.json` (§4.0d)
- ☐ Đợt C: `vga_wide` + intrinsics 6 Validation (≈ 10,23 GB) — đã duyệt (Q16), chưa tải
- ☐ Đo `V_ref`, `G_ref` trên `vga_wide` của 6 Validation → `default.yaml` (kèm `measured_on`)

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

- ☐ Sửa `data/README.md` và kế hoạch: "42.348.620 điểm mỗi scan" chỉ đúng cho 1 file (xem mục 5, điểm c)
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
| 2026-10-17 | Tạo `AGENTS.md`, `CLAUDE.md`, `WORKING_LOG.md`, sao chép kế hoạch vào `docs/PLAN_v4.md`; kiểm chứng 3 điểm hở của kế hoạch (mục 5) | 4 file mới | xem mục 5 và phần kiểm tra cuối của commit | commit kế tiếp |

**Hash khôi phục các nhánh đã xoá:** `feature/Update` `b14f47e3c9c52c556c792fa9ef07b8abc48f0d39` · `feature/setup-data-scripts` `5dd829aac0cf078ea3fc2b6b7e56a4ab09988f16`
· `feature/extract_frame` cục bộ `fd4cd8b28e7383d7003b7d23504a2d103836f659`, origin `f0bee5b8a9dac9e65064745d5a8204e4f1271b39` · `feature/gitignore` `60580776d5ddcb970978a2b2144278d008069f10`.
Khôi phục: `git branch <tên> <hash>` rồi (nếu cần) `git push origin <tên>`.

## 5. Chưa làm được / đang bị chặn

| Việc | Lý do | Cần gì để gỡ | Ai quyết định |
|---|---|---|---|
| Toàn bộ M0b trở đi | chưa bắt đầu; M1 bị chặn bởi M0b (cần Faro, đợt C, `v_ref.vga`) [PLAN §10, Q20] | làm M0b theo checklist | người dùng chọn thời điểm |
| `create_env.bat` chạy thật | chỉ mới `--dry-run`; chạy thật cài lại gói, `--recreate` xoá env | xác nhận trước khi chạy | người dùng |
| Gói `vggt` và trọng số VGGT-1B chưa có trong env | `check_env.py` cảnh báo "chưa import được vggt"; trọng số chưa trong `~/.cache/huggingface/hub`, kích thước [chưa kiểm chứng] | cài `pip install -e <vggt> --no-deps`; xin tải trọng số | người dùng |
| **(a) Faro ngoài ngân sách ổ đĩa** | Kế hoạch chỉ tính Faro cho scene dev (đợt B). Nhưng M3/M4 cần GT cho 6 Validation + 5 held-out (mốc scale, 12–20 đoạn test mỗi scene, Chamfer/F-score). **Đã đo bằng HEAD (17/10):** Faro 6 venue Validation = **49,62 GB** (5,60 / 7,53 / 10,61 / 9,28 / 7,49 / 9,11 GB), Training 32 venue trung bình 6,06 GB (1,87–11,0 GB), tổng Training 193,8 GB. Ổ D: còn ≈ 55 GB; sau 3 đợt A+B+C còn ≈ **33 GB** < 49,62 GB. Giảm một nửa nếu mỗi cặp pose trùng có xyz giống nhau như ở venue dev (**[chưa kiểm chứng]** cho 6 venue này) | chọn: (1) dùng `highres_depth` (đã có cho cả 40 scene) làm GT dự phòng; (2) chỉ tải 1 file mỗi cặp pose trùng; (3) giải phóng/thêm ổ; (4) giảm số scene có Faro | người dùng [Cần xác nhận] |
| **(b) Ngưỡng keyframe cần ở M1 nhưng chỉ khoá ở M2** | `keyframe.blur.q_drop` đang `null` (PLAN §4.1: "khoá trên 6 Validation"; §10 M2: khoá blur/overlap). Stage `keyframe` của M1 lọc blur nên cần một giá trị; `require()` sẽ `raise` khi `null`. `keyframe.overlap.max/min` đã có mặc định (0,8/0,6, [Suy luận]) | chọn giá trị tạm ghi rõ "tạm, M1" (ví dụ chỉ loại q_blur rất thấp theo ví dụ §7.3: 0,005 loại, 0,35 giữ), hoặc đo sớm trên 6 Validation sau đợt C | người dùng [Cần xác nhận] |
| **(c) Số điểm mỗi scan Faro** | **Đã kiểm lại, kế hoạch/README ghi sai:** "mỗi scan 42.348.620 điểm" chỉ đúng cho file 1,863 GB. Đo bằng header PLY (Range): `169892` 42.348.620; `169895` 41.467.500; `169897` 40.935.479 (cả ba khớp `332 + n×44 = kích thước`). Ba scan ≈ 124,75 triệu điểm | sửa `data/README.md` và ghi chú trong `docs/PLAN_v4.md` (chưa sửa, ngoài phạm vi nhiệm vụ này) | người dùng [Cần xác nhận] |
| PR #4 | không có `gh` trên máy; không thấy merge commit của #4 trên `origin/main` (#1, #2, #3, #6, #7, #8 đã merge) | xem trên GitHub | người dùng |
| Nhánh chưa đồng bộ với `origin/main` | `feature/m0a-foundation` cách `origin/main` 10 commit (merge #1–#8, xoá 2 CSV trong `reports/`); `main` cục bộ `bbc68bc` cũ hơn `origin/main` `8a56a9b` | quyết định merge/rebase khi mở PR | người dùng |
| Replica | thiếu `preseg`, `semantic`, `glass.sur`; Habitat-Sim chưa cài, khả năng cài trên Windows [chưa kiểm chứng] | Q6: hoãn đến M5 | người dùng |
| `setup_3dmeph_structure.sh` | nằm **ngoài** repo (`3D_Metric/`), còn tạo `thesis/`, `zotero/` và ghi đè README bằng bản cũ nếu chạy lại | sửa hoặc bỏ file này | người dùng |
| Chưa kiểm chứng (từ kế hoạch) | ý nghĩa xoay/tịnh tiến trong Faro `_pose.txt`; xyz toàn bộ các cặp Faro khớp nhau; peak VRAM thật; chất lượng MVS/Poisson trên 640×480; có lệnh `unzip` hay không | làm khi tới mốc liên quan | — |

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

## 7. Câu hỏi còn mở

| # | Câu hỏi | Mặc định nếu không trả lời |
|---|---|---|
| Q8 | Ngưỡng `blur.q_drop` và cách tính overlap | Khoá trên 6 Validation ở M2 (xem mục 5 điểm b: M1 cần giá trị tạm) |
| Q11c | Chính sách `reports/` trong `.gitignore` (commit CSV hay không) | Hỏi nhóm; giữ nguyên (không commit) |
| Q21 | Faro cho 6 Validation + 5 held-out (≈ 50 GB + ≈ 30 GB ước tính) vượt ngân sách ổ: chọn phương án nào (mục 5 điểm a)? | Chưa tải gì; dùng `highres_depth` làm dự phòng |
| Q22 | Giá trị tạm của `keyframe.blur.q_drop` cho M1 (mục 5 điểm b) | Chưa chạy M1 cho tới khi có giá trị |
| Q23 | Sửa số điểm Faro sai trong `data/README.md` và kế hoạch (mục 5 điểm c) | Chưa sửa |
| Q24 | Thêm kiểm tra tiêu đề `WORKING_LOG.md` vào `scripts/check_docs.py` (AGENTS.md mục 10, điểm 7) | Chưa thêm |
| Q25 | Trạng thái PR #4; tên GitHub thật thay `@username1–4` trong CODEOWNERS | Giữ placeholder |
| Q26 | Merge hay rebase `QuangDai_Work` với `origin/main` trước khi mở PR; có cập nhật `main` cục bộ không | Chờ quyết định |
