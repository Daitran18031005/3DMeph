# Bảng chuẩn công bằng trên MVS d3 (M4 đợt 3, bước 1–2)

Mốc: git rev đợt 2 `55300c72d5a1de34f42cb18ab3f7e2291b53ed7a`. Từ nay `stereo_fusion` mặc định là d3 (`colmap.stereo_fusion.*` trong `configs/default.yaml`: min_num_pixels 2,
max_reproj_error 8, max_depth_error 0,05, max_normal_error 30, check_num_images 100) cho B0, B3, proposed, abl_quality. Quyết định của người dùng (13/11); ĐC không nêu số `stereo_fusion`.
Lý do: ở d3, B0 đạt F 0,4926 ≈ proposed_d3 0,4907 (đợt 2), tức phần lớn mức tăng đến từ việc nới bộ lọc COLMAP; so proposed với B0 lọc chặt là không công bằng.

**Cách làm:** `python scripts/refuse_mvs.py --scene <id>` (chạy lại CHỈ `stereo_fusion` ~10 s, không GPU; sao lưu bản cũ) rồi
`pipeline.run --from-stage align --to-stage gate`, `--variant abl_quality --from-stage fuse --to-stage gate`, `--from-stage eval --to-stage eval`. `fused.ply.vis` vẫn theo thứ tự image_id (lệch #44).
Bản MVS cũ (lọc chặt) giữ ở `baselines/colmap/mvs/fused_strict.ply(.vis)`, `metric/fused_metric_strict.ply`, `proposed/variants/strict_old/` và `evaluation/variants/strict_old/`;
`../baseline_truoc_doi/` giữ nguyên làm mốc "MVS lọc chặt". 47204552 vẫn loại (SfM vỡ). Chưa chạy lại `export` (Poisson trên ~1 triệu điểm): `proposed/export/` còn là bản MVS lọc chặt.
**B1 không phụ thuộc MVS**: `eval` tính lại và ra đúng từng chữ số như cũ (F 0,50627; 0,30227; 0,31139; 0,64811). Không có B1 ở 42897599, 42898849 (không nối được chunk).

Số liệu: `baseline_d3.csv` (variant × scene × acc, comp, precision, recall, F, Chamfer), `<scene>/metrics.csv`, ảnh `<scene>/{proposed,B0}_{topdown,view}.png` cùng khung hình với `../baseline_truoc_doi/`.

## proposed so với B0 trên d3 (cùng MVS), theo từng scene

| Scene | B0 F | proposed F | ΔF | ΔChamfer (cm) | Δprecision | Δrecall | Δacc (cm) |
|---|---|---|---|---|---|---|---|
| 42897599 | 0,275 | 0,271 | −0,004 | −1,17 | −0,283 | +0,014 | +3,32 |
| 42897566 | 0,549 | 0,523 | −0,026 | −0,24 | −0,092 | +0,002 | +0,28 |
| 42898849 | 0,544 | 0,436 | −0,109 | −11,40 | −0,290 | −0,024 | −18,63 |
| 42445022 | 0,523 | 0,614 | +0,090 | +1,73 | +0,101 | +0,081 | −2,14 |
| 45662981 | 0,571 | 0,612 | +0,041 | −0,72 | −0,007 | +0,072 | −1,09 |
| 42444738 (dev) | 0,493 | 0,507 | +0,014 | −1,45 | −0,017 | +0,031 | −1,68 |
| **Trung bình** | **0,4927** | **0,4939** | **+0,0012** | **18,86 → 16,65 (−11,7%)** | 0,710 → 0,612 | 0,398 → 0,427 | 9,42 → 6,10 |

Trung bình 6 scene: B3 0,4938 / 16,65 cm; abl_quality 0,4943 / 16,66 cm; B1 (4 scene có B1) F 0,442, Chamfer 14,78 cm.

## Kết luận trung thực: fusion/gate đóng góp gì trên d3
- **F-score: gần như không đóng góp** (+0,0012 trung bình; thắng ở 3 scene 42445022 +0,090, 45662981 +0,041, 42444738 +0,014; thua ở 3 scene, nặng nhất 42898849 −0,109).
- **Hình học (Chamfer, acc): có đóng góp** (Chamfer −11,7%, acc 9,42 → 6,10 cm), phần lớn từ một scene (42898849: acc 27,3 → 8,7 cm; với MVS nhiễu VGGT kéo điểm về bề mặt). Chamfer tốt hơn ở 5/6 scene.
- **Plane gate: không đóng góp** (B3 vs proposed: ΔF +0,0001, Chamfer như nhau); `abl_quality` (bỏ q_blur/q_texture/q_exposure) chỉ lệch +0,0004 F.
- **Cái giá: precision giảm** (0,710 → 0,612; ở 42897599 −0,283, 42898849 −0,290): điểm nhiễu của MVS dày được giữ lại. Vì thế bước 3 (giảm nhiễu) nhắm vào precision ở hai scene này.
- Đây là kết quả phát triển: cả 5 Validation đã được nhìn khi quét ngưỡng; chưa phải bằng chứng cuối (held-out một lần).
