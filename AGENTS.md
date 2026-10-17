# AGENTS.md — luật chung cho mọi agent làm việc trong repo 3DMeph

Đọc file này **trước** khi làm bất cứ việc gì. Tiếng Việt, thuật ngữ kỹ thuật giữ tiếng Anh.
Nhãn nguồn: **[ĐC §x]** đề cương PDF, **[Suy luận]** nhóm tự suy ra, **[Cần xác nhận]** chờ người dùng gật đầu,
**[chưa kiểm chứng]** chưa chạy hoặc chưa đo. Kế hoạch đầy đủ: `docs/PLAN_v4.md`. Trạng thái thật: `WORKING_LOG.md`.

## 1. Dự án

3DMeph dựng lại **3D metric trong nhà từ video điện thoại**: COLMAP (hình học) và VGGT (học sâu) chạy độc lập, căn về cùng
hệ toạ độ, đổi sang mét bằng một mốc scale, ghép theo độ tin cậy sáu tín hiệu (fusion), rồi làm phẳng có cổng (plane gate).
**Mục tiêu:** sai số trung vị < 5 cm cho phòng 3–5 m sau một lần neo scale (mục tiêu thử nghiệm, chưa phải kết quả).

**Phạm vi mốc đầu:** CLI chạy 1 scene ARKitScenes (42444738), fusion theo luật. **KHÔNG làm** FastAPI, Unity, train
confidence head, Replica (hoãn đến M5).

## 2. Nguồn sự thật (theo thứ tự ưu tiên)

1. Lệnh trực tiếp của người dùng trong chat.
2. `docs/PLAN_v4.md` (kế hoạch v4).
3. PDF đề cương `Docs/TaiTao3D_Metric_3DMeph.pdf` (ngoài repo, thư mục `3D_Metric/`; 52 trang vật lý, bản Revised 10/2026).
4. Ba file HTML trong `PipelineFlowChart/` (ngoài repo, **không sửa**). Chỗ lệch với PDF đã liệt kê ở §2c của kế hoạch;
   **mặc định theo PDF** (ví dụ: gate theo (24), điểm không qua cổng vẫn giữ; fusion cần 4 đường vào thiếu trên sơ đồ).

Khi hai nguồn mâu thuẫn hoặc kế hoạch mâu thuẫn dữ liệu thật: **dừng, nêu chỗ lệch, hỏi** (xem mục 11).

## 3. Bản đồ module (dataflow → module)

Các stage chỉ giao tiếp **qua file** (GPU 8 GB không giữ VGGT và COLMAP cùng lúc). Chỉ số: i = view, k = điểm.

| Node dataflow | Module `pipeline/…` | Vào → ra (trong thư mục scene) | Công thức PDF |
|---|---|---|---|
| Keyframes Input | `keyframe/` | `raw/source.json`, zip ARKit → `frames/keyframes/*.jpg`, `metadata/keyframes.csv`, `camera.json` | (1)(2)(3)(20) |
| COLMAP SfM, MVS, SfM Output | `colmap/` | keyframes → `baselines/colmap/{sfm,mvs}`, `observations.npz`, `e_reproj_map/`, `sigma_depth/` | (9)–(12) |
| VGGT Inference, Output | `vggt/` | keyframes theo chunk → `baselines/vggt/chunk_XX/{vggt_raw,vggt_out}.npz` | (8)(2) |
| Scale Alignment | `alignment/` | tâm camera `x_i`,`y_i` + `ground_truth/scale_anchor.json` → `proposed/alignment/{chunk_XX_sim3,scale}.json` | (13)–(18)(4) |
| Confidence Fusion | `fusion/` | điểm MVS + 6 tín hiệu → `proposed/fusion/{fused_points.ply,fusion_log.npz}` | (19)–(22) |
| Plane-Gated Filter | `plane_gate/` | `fused_points.ply` → `proposed/plane_refinement/{refined_points.ply,planes.json,gate_log.csv}` | (23)–(25) |
| GLB Mesh Output | `export/` | `refined_points.ply` → `proposed/export/{model.glb,measurements.json}` | (30) |
| *(ngoài dataflow)* Eval | `eval/` | các đầu ra + GT → `evaluation/metrics.csv` | (7)(31)–(37) |
| *(dùng chung)* | `common/` | config, I/O, hình học, chất lượng ảnh | — |

**9 stage CLI:** `keyframe, sfm, mvs, vggt, align, fuse, gate, export, eval`. Lệnh dự kiến:
`python -m pipeline.run --scene arkitscenes/<video_id> --config configs/default.yaml --from-stage X --to-stage Y [--variant B0|B1|B3|proposed|abl_quality|abl_gate]`
— **chưa tồn tại** (dự kiến M1). README module nào cũng ghi trạng thái (cái gì có, cái gì chưa).

## 4. Cấu trúc thư mục

```
3DMeph/  AGENTS.md CLAUDE.md WORKING_LOG.md README.md CONTRIBUTING.md requirements.txt
├─ pipeline/{keyframe,colmap,vggt,alignment,fusion,plane_gate,export,eval,common}/  mỗi module có README.md
├─ configs/default.yaml   ├─ environment/   ├─ tests/   ├─ scripts/   ├─ docs/ (PLAN_v4.md, khoá luận)
├─ data/{raw,scenes,processed,self_collected,splits.csv}   ├─ outputs/eval_results/   ├─ reports/   └─ app/
```
`outputs/` chỉ còn `eval_results/` (bảng chéo scene). Đầu ra từng scene nằm trong cây Mục 9 [ĐC §9] tại
`data/scenes/<dataset>/<scene_id>/`:
`raw/ frames/{candidates,keyframes}/ metadata/ ground_truth/ baselines/{colmap,vggt}/ proposed/{alignment,fusion,plane_refinement,export}/ evaluation/{metrics.csv,figures,logs}`.
(`proposed/alignment`, `proposed/export`, `ground_truth/faro` không có trong đề cương; nhóm thêm.)

## 5. Lệnh chuẩn (chỉ lệnh đã tồn tại và đã chạy thật)

Env conda `3d_metric` (Python 3.12). Python của env: `C:\Users\GIGA\anaconda3\envs\3d_metric\python.exe` (hoặc `conda activate 3d_metric`).

| Việc | Lệnh | Ghi chú |
|---|---|---|
| Kiểm tra môi trường (chỉ đọc) | `python environment/check_env.py` | đã chạy: 0 lỗi, 3 cảnh báo |
| Xem lệnh dựng env (không chạy) | `environment\create_env.bat --dry-run` | **chỉ dry-run đã chạy**; chạy thật cần xác nhận (mục 7) |
| Test | `python -m pytest tests -q` | đã chạy: 95 passed |
| Lint | `python -m ruff check .` (cấu hình cố định ở `ruff.toml`: E, F, W, I) | UP, PLW1510, RUF, C4 hoãn có chủ ý (WORKING_LOG.md) |
| Kiểm README ↔ config | `python scripts/check_docs.py` (`--no-run` bỏ qua lệnh trong README) | đã chạy: OK (19 README, 41 khoá) |
| Đo hai điểm | `python -m pipeline.export.measure --a x y z --b x y z` | đã chạy |
| EDA / validate dữ liệu | `python scripts/explore_dataset.py`, `python scripts/validate_dataset.py` | chạy lâu; mới chạy `--help` sau khi đổi đường dẫn mặc định sang `reports/statistics/`, [chưa kiểm chứng] chạy đầy đủ |

**Bắt buộc:** `pipeline/__init__.py` `import torch` **trước** `pycolmap`/`open3d`/`cv2`, nếu không `import pycolmap` lỗi
"DLL load failed" (đã kiểm chứng). Luôn import module qua gói `pipeline`.
COLMAP chạy bằng CLI 4.2 (`../colmap/bin/colmap.exe`, hoặc biến `COLMAP_EXE`); pycolmap 3.10 chỉ đọc model và căn Sim(3).

## 6. Quy tắc dữ liệu (bắt buộc)

- **Danh sách scene = thư mục thật + `data/raw/arkitscenes/metadata.csv`.** `selected_scenes.csv` chỉ để tham khảo
  (lệch: 2 dòng không có trên đĩa, 6 Validation không nằm trong file).
- **Chia tập theo `visit_id`: 29 train / 6 val / 5 held-out, seed 42**, khoá bằng `data/splits.csv` + `data/splits.lock`
  (sinh ở M0b, [chưa có]). Val = 6 scene `Validation`. Venue 472473 và 466899 (mỗi venue 2 scene) phải cùng một tập.
  Scene dev 42444738 luôn ở train. Held-out nội bộ, **không gọi là official test**.
- **Held-out chạy đúng một lần.** Mọi hàm tính `V_ref`, `G_ref`, ngưỡng phải `raise` nếu thấy scene held-out
  (`common/splits.py`, [chưa cài, M0b]). **Không bao giờ chỉnh tham số dựa trên held-out** (và không chỉnh trên Replica).
- **`V_ref`, `G_ref` chỉ đo trên `vga_wide` của 6 Validation.** Không dùng số 581 làm giá trị cấu hình (đo trên 256×192, gồm cả
  scene sẽ là held-out). Tham số `null` nghĩa là chưa có căn cứ; `require()` báo lỗi thay vì đoán.
- **Không dùng pose GT để suy ra scale.** Mốc scale = một đoạn 1–2 m, dễ thấy, không trên gương/kính; `used_as_anchor=1`
  và **bị loại khỏi chỉ số test** [ĐC §8.1].
- **`*_3dod_mesh.ply` KHÔNG phải Faro** (là mesh ARKit). Faro là `laser_scanner_point_clouds` (`.ply` + `_pose.txt`).
- **Không ghi đè, không copy, không giải nén dữ liệu raw.** Raw nằm ngoài git. Tải bằng wrapper không giải nén
  (`scripts/download_arkitscenes.py`, [chưa có, M0b]); **không** dùng `download_data.py` gốc cho `vga_wide` (nó tự `unzip` và xoá zip).
- Ảnh ARKit xoay đứng theo `sky_direction` (Up→0°, Left→90° CW, Down→180°, Right→90° CCW); `NA` thì dừng, báo.

## 7. Quy tắc an toàn (cần người dùng xác nhận trước khi làm)

- **Tải dữ liệu:** luôn `--dry-run` trước, rồi mới `--yes`, đúng từng đợt đã duyệt: A (≈0,74 GB), B (≈10,98 GB), C (≈10,23 GB).
  Mọi tải khác (Faro cho scene khác, Replica, trọng số VGGT) cần xin riêng. Ổ D: còn khoảng 55 GB.
- **Git:** push, mở/đóng PR, xoá hoặc đổi tên nhánh, rebase, xoá file, sửa `.gitignore`. Không dùng `--force`,
  không `git push --delete` với ký tự đại diện, không `branch -D` khi chưa được phép.
- **Môi trường:** không chạy `create_env.bat` thật (đặc biệt `--recreate`, có thể xoá env `3d_metric`) khi chưa xác nhận.
- **Không commit:** `.env`, khoá, trọng số (`*.pt, *.pth, *.safetensors, *.ckpt`), dữ liệu, file > 5 MB.
- Không sửa 3 file HTML, không sửa dữ liệu raw.

## 8. Quy ước code

- Type hint và docstring tiếng Việt cho hàm công khai; trích **số công thức PDF** trong docstring.
- Lỗi theo mã của kế hoạch: `E_TOO_FEW_KEYFRAMES` (dưới 40 keyframe), `E_SFM_FAILED` (SfM không hội tụ) [ĐC Hình 24].
- Mỗi stage ghi `run_meta.json` (thời gian, peak VRAM, hash config, mã lỗi). Stage chỉ giao tiếp qua file.
- Đầu ra hình học ở **mét**; `σ_depth` đổi từ đv COLMAP sang mét (nhân `s_m`) trước khi dùng `τ_σ = 0,20 m`.
- Ký hiệu theo PDF: `τ_e`, `τ_σ` (**không dùng λ**); `w` là trọng số **thô** (19), `w̃` là **đã chuẩn hóa** (22); `plane.alpha` (25)
  khác `loss.alpha_r` (29). Tham số ở `configs/default.yaml`, README module ghi đúng tên khoá (`check_docs.py` kiểm hai chiều).
- Script CLI ép stdout UTF-8 (console Windows cp1252 không in được tiếng Việt).

## 9. Quy trình git và mốc

Mỗi mốc một nhánh `feature/<tên>` và một PR vào `main` (≥ 1 approve), theo `CONTRIBUTING.md`. Commit nhỏ, thông điệp rõ.
`QuangDai_Work` (origin) chỉ để **sao lưu** cá nhân. **Nhánh hiện tại:** `feature/m0a-foundation` (theo dõi `origin/QuangDai_Work`).
`origin/main` đã tiến thêm so với nhánh này (khi mở PR có thể phải merge/rebase; chờ quyết định).

| Mốc | Việc | Tiêu chí đạt [PLAN §10] |
|---|---|---|
| M0a | env, config, common, lõi toán, README | `check_env.py` exit 0; pytest xanh; `check_docs.py` exit 0 |
| M0b | chia scene, tải A/B/C, căn Faro, chấm mốc và đoạn test, đo `V_ref`/`G_ref` | `splits.csv` 29/6/5, 0 venue ở 2 tập, chạy lại cho cùng held-out; tải khớp dung lượng HEAD; residual căn Faro được log; ≥ 1 anchor + ≥ 12 đoạn test; `v_ref.vga`, `g_ref.vga` ghi vào config |
| M1 | cả 9 stage chạy 1 lệnh trên 42444738 (`vga_wide`), chỉ bắt đầu sau M0b | `pipeline.run` exit 0, `model.glb` mở được, `measure` đo được 1 đoạn, `run_meta.json` đủ |
| M2 | khoá ngưỡng keyframe trên 6 Validation | 40 ≤ N_kf ≤ 80; ≥ 90% keyframe đăng ký SfM; peak VRAM < 8 GB (có số đo) |
| M3 | `eval/` đủ chỉ số, B0/B1/B3/Proposed/Ablation 1–2 | `metrics.csv` đủ 6 cấu hình; Δ% theo (31) |
| M4 | nhiều scene ARKit | ngưỡng khoá ghi vào config; bảng val và held-out riêng |
| M5 | Replica, tự thu pilot | 18 scene chạy một lần; báo theo 13 không gian |
| M6 | FastAPI + Unity, báo cáo | theo ĐC §21 |

Mục tiêu đo (ĐC §21): median < 5 cm; giảm 15–20% plane error mà F-score không giảm đáng kể. Không đạt thì báo số thật.

## 10. Cập nhật WORKING_LOG.md (bắt buộc)

Sau **mỗi** công việc hoàn thành thành công, trước khi commit:
1. Chạy kiểm tra liên quan (pytest, ruff, check_docs, hoặc tiêu chí đo được của việc đó).
2. Chỉ đánh ☑ khi có **bằng chứng**: lệnh đã chạy và kết quả. Dry-run không tính là xong việc thật; ghi "chỉ dry-run".
3. Cập nhật bảng tổng quan, checklist, mục "Đã làm", và dời/xoá mục tương ứng ở "Chưa làm được / đang bị chặn".
4. Việc vừa làm khác kế hoạch → ghi vào "Lệch so với kế hoạch" (kèm đã được người dùng đồng ý chưa).
5. Việc thất bại hoặc làm dở → ghi vào "Chưa làm được" kèm lỗi thật, không đánh ☑.
6. Cập nhật `WORKING_LOG.md` **cùng commit** với code của việc đó.
7. Thêm check cho `WORKING_LOG.md` vào `scripts/check_docs.py` chỉ sau khi người dùng đồng ý.

## 11. Trung thực khi báo cáo

- Không nói "xong" nếu chưa chạy kiểm tra. Nói rõ cái gì **đã chạy thật**, cái gì **chỉ dry-run**, cái gì **chưa kiểm chứng**.
- Báo số thật kể cả khi xấu; không che failure. Số của đề cương dùng làm ví dụ không phải kết quả thí nghiệm.
- Không bịa lệnh, đường dẫn, số liệu. Không biết thì ghi "[chưa kiểm chứng]" hoặc hỏi.
- Gặp kế hoạch mâu thuẫn PDF hoặc dữ liệu thật: nêu chỗ lệch và hỏi, không tự quyết rồi im lặng.
