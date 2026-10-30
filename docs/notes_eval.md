# Ghi chú luồng 1 — stage `eval` + biến thể (M3), nhánh `feature/m3-eval`

Để gộp vào `WORKING_LOG.md` sau (luồng này không sửa file đó). Ngày chạy: 2026-10-31. **Một scene (42444738, train) ⇒ không phải kết luận thống kê.**

## Đã làm (có bằng chứng)
- Stage `eval` cài xong: `pipeline/eval/{lengths,b1,geometry,variants,stage}.py`; `pipeline.run` có `--variant B0|B1|B3|proposed|abl_quality`; `README` module cập nhật.
- Kiểm tra: `pytest tests -q` → **290 passed, 11 skipped** (skip có từ trước, cần dữ liệu); `ruff check .` → All checks passed; `check_docs.py --no-run` → OK (19 README, 74 khoá).
  Test mới: `test_eval_lengths.py`, `test_eval_b1.py` (3 chunk tổng hợp, Sim(3) và scale biết trước, khôi phục đúng), `test_eval_stage.py` (cảnh tổng hợp + `pipeline.run --variant`).
- **Chạy thật trên scene dev** qua cây scratch dùng directory junction (không copy dữ liệu, không ghi đè kết quả có sẵn; đã kiểm `ls`: `evaluation/` và `baselines/vggt/` của dữ liệu gốc không đổi):
  `--variant abl_quality --from-stage fuse --to-stage gate` (17 s, CPU) rồi `--from-stage eval --to-stage eval` (32 s). Không GPU, không SfM/MVS/VGGT, không tải dữ liệu, không đụng held-out.
  Dữ liệu dev là đầu ra M1 (SfM cũ, trước thay đổi M2).

## Số đo thật (chế độ `auto`, bán kính snap 2 cm, 12 đoạn test; mốc S05 đã loại)

| Biến thể | ATE cứng (cm) | ATE Sim(3) (cm) | Đoạn hợp lệ | MAE / median (cm) | Đầu mút không snap | Điểm gần nhất trung vị (cm) | Chamfer sau ICP / sau Kabsch (cm) | F-score (δ 5 cm) |
|---|---|---|---|---|---|---|---|---|
| B0 | 8,2 | 8,0 | 0/12 | — | 23/24 | 18,3 | 21,0 / 23,0 | 0,263 |
| B1 | 21,0 | 16,4 | 1/12 | 0,3 / 0,3 | 19/24 | 12,8 | 8,2 / 12,7 | 0,550 |
| B3 | 8,2 | 8,0 | 1/12 | 1,1 / 1,1 | 21/24 | 21,1 | 22,3 / 24,7 | 0,270 |
| proposed | 8,2 | 8,0 | 1/12 | 1,1 / 1,1 | 21/24 | 21,1 | 22,3 / 24,7 | 0,271 |
| abl_quality | 8,2 | 8,0 | 1/12 | 0,0 / 0,0 | 21/24 | 21,1 | 22,2 / 24,7 | 0,278 |

- **Tập chung = 0 đoạn** (không đoạn nào hợp lệ ở mọi biến thể) ⇒ cột `*_common` và `delta_pct_*_vs_B0` trống. **Không có so sánh chiều dài giữa các biến thể từ lần chạy này.**
- Quét bán kính snap (chỉ chẩn đoán, **không đổi** `eval.snap_radius_m`): số đoạn hợp lệ ở 2 / 5 / 10 / 15 / 25 cm: B0 0/2/3/4/7, B1 1/2/3/5/9, B3 và proposed 1/2/5/5/6, abl_quality 1/2/5/5/6.
  MAE tương ứng của B0 tại 5 / 10 / 15 / 25 cm: 1,3 / 2,7 / 2,7 / 10,5 cm (rất ít đoạn, dễ lệch).
- Ablation 1 (bỏ `q_*`): qua cổng 8.970/144.863 (6,2%) so với proposed 1.680 (1,2%); `w_k > τ_w` 37,2% so với 11,1%. Bỏ các thừa số q (đều ≤ 1) làm `w` lớn hơn nên nhiều điểm qua `τ_w`. Chamfer/F gần như không đổi.
- B1: nối chunk 10 liên kết, scale mỗi liên kết dao động 0,71–2,16 (VGGT chuẩn hoá scale riêng từng chunk), tích luỹ ⇒ ATE cứng 21,0 cm trên 110 camera; mốc S05 trong hệ VGGT: `L_vggt` 1,4114 đv ⇒ `s` = 1,3602 m/đv, **sai số chiếu lại mốc lớn nhất 10,5 px** (mốc kém tin cậy hơn ở hệ COLMAP: 5 px).
  B1 có 1,26 triệu điểm (stride 4), B0/B3/proposed chỉ 144.863 điểm MVS ⇒ so sánh snap/Chamfer **không công bằng về mật độ**; F-score cao hơn của B1 phần lớn do mật độ (Recall 0,50 so với 0,17).

## Phát hiện quan trọng (cần quyết định)
1. **Chế độ `auto` gần như không đo được độ chính xác chiều dài.** Phép căn cứng scale = 1 giữ nguyên khoảng cách GT, snap chỉ dời mỗi đầu mút ≤ 2 cm ⇒ lỗi chiều dài `auto` ≤ 4 cm bất kể mô hình đúng hay sai scale (test tổng hợp xác nhận: giãn mô hình 5% không làm lỗi tăng). Thông tin thật nằm ở: tỉ lệ đầu mút không snap, ATE cứng (8,2 cm), Chamfer/F. Phép đo chiều dài thật cần chế độ `manual` (chọn tay trên point cloud). Đây là hệ quả của protocol ở PLAN §4.8 điểm 2.
2. **Bán kính 2 cm quá chặt so với sai số căn 8,2 cm (tối đa 34 cm ở một số camera)** và mật độ MVS thưa: B0 0/12 đoạn hợp lệ. Đề xuất (chưa làm): giữ 2 cm cho báo cáo, thêm cột ở bán kính lớn hơn; hoặc chờ luồng chấm tay.
3. **ICP cứng scale = 1 dịch mô hình 25–39 cm, xoay 4–6°** (fitness 0,74–0,87): lớn bất thường, có thể do mô hình chỉ phủ một phần phòng và mặt phẳng trượt; số Chamfer sau ICP **chưa đáng tin**, ưu tiên cột `*_kabsch`. `Comp` của B0 34 cm vì MVS thưa không phủ hết Faro.
4. `metrics.csv` có **5 cấu hình**, không đủ "6" của tiêu chí M3 (Ablation 2 → Replica/M5 theo PDF).

## Lệch so với kế hoạch (đã nêu trong kế hoạch được duyệt)
| Chỗ lệch | Lý do | Đã đồng ý? |
|---|---|---|
| Sửa 1 dòng cũ của `pipeline/run.py` (`--variant`: `choices` và `default=None`) | không thêm biến thể được nếu không đổi dòng đó | Có |
| Sửa `tests/test_run.py` (2 chỗ `monkeypatch.delitem(pr.IMPLEMENTED, "eval")`) — ngoài danh sách file được phép | hai test cũ giả định `eval` chưa cài; giữ nguyên kiểm tra đường `E_NOT_IMPLEMENTED` | Chưa hỏi riêng |
| Thêm 6 khoá vào khối `eval:`; **5 khoá là TẠM [Suy luận]**: `eval.b1.stride` 4, `eval.b1.c_min` 0,5, `eval.crop_margin_m` 1,0, `eval.voxel_m` 0,02, `eval.icp_max_dist_m` 0,10 (`eval.delta_m` 0,05 theo ĐC (35)) | không có trong đề cương | Cần xác nhận giá trị |
| B1 scale = tam giác hoá mốc (click 2D) trong hệ VGGT đã nối chunk; nối chunk bằng Umeyama cắt tỉa trên điểm cùng pixel ở ảnh gối | ĐC không nêu | Có (hướng) |
| Ablation 1 = `fuse(use_quality=false)` + `gate` | ĐC không nêu rõ so với B3 hay Proposed | Có |
| `MAX_POSE_GAP_S = 0,5` s (không nội suy pose GT qua khoảng trống) | an toàn khi lấy tâm camera GT | Chưa hỏi riêng |

## Chưa làm / chưa kiểm chứng
- Ablation 2 (`abl_gate`), P2Plane, PlaneRecall: chuyển sang Replica (M5) theo PDF.
- Chế độ `manual` mới được test bằng dữ liệu tổng hợp; **định dạng `endpoints_<variant>.json` chưa được luồng 3 xác nhận** (định dạng đề xuất ở `pipeline/eval/README.md`: `scene, variant, unit=m, frame=variant_cloud, endpoints{id:{a,b}}`).
- Chưa cài bảng chéo scene `outputs/eval_results/`; chưa chạy Validation/held-out; chưa kiểm B1 trên scene khác.
- `run_meta.json` của lần chạy thật nằm ở cây scratch (không phải dữ liệu gốc).
