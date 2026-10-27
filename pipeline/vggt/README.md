# pipeline/vggt/

Trạng thái (M1b): có `chunks.py` (chia chunk), `outputs.py` (`c_model`) và `infer.py` (chạy VGGT theo chunk, ảnh đứng chế độ `pad`,
ánh xạ pixel `original_to_vggt`/`vggt_to_original`), cùng test (phần không cần GPU dùng mô hình giả). Trọng số `facebook/VGGT-1B`
(`model.safetensors` 5.026.367.224 B + `config.json` 62 B, cc-by-nc-4.0) nằm ngoài repo, trỏ bằng `vggt.weights_dir`; không commit.

## Vai trò

Các node **VGGT Inference** và **VGGT Output** của dataflow. VGGT (~1,2 tỷ tham số, đóng băng) đọc N ảnh một lượt và
trả camera, depth, độ tin cậy; không lặp tối ưu như COLMAP (ĐC §13). Là baseline B1 và nguồn của `c_model`.
Mọi dự đoán nằm trong hệ camera **đầu chunk**, scale đã chuẩn hóa, **chưa phải mét**.

## Input/Output

| | Đường dẫn (trong thư mục scene) | Nội dung | Đơn vị |
|---|---|---|---|
| vào | `frames/keyframes/` | keyframe, chia chunk `c` ảnh gối `o` ảnh | — |
| ra | `baselines/vggt/chunk_XX/vggt_raw.npz`: `extrinsic (N,3,4)`, `intrinsic (N,3,3)`, `depth (N,H,W)`, `depth_conf (N,H,W)` | đầu ra thô | hệ camera đầu chunk, chưa mét; `depth_conf` ∈ [1, ∞) |
| ra | `baselines/vggt/chunk_XX/vggt_out.npz`: `c_model (N,H,W)`, `points (N,H,W,3)` | `c_model` và điểm unproject từ depth | `c_model` ∈ [0,1); điểm đv VGGT |
| ra | `baselines/vggt/metric/` | baseline B1 (VGGT thuần, mét) | m |

Chỉ số: view i trong chunk; `(i, pixel)` cho bản đồ.

## Công thức

- Hàm VGGT `f((I_i)) = (g_i, D_i, P_i, T_i)` (8), `g_i = [q_i, t_i, f_i]`.
- Số chunk `N_chunk = ⌈(N_kf − o)/(c − o)⌉` (2): N_kf=72, c=12, o=2 cho 7 chunk (1–12, 11–22, …, 61–72, ĐC Hình 7).
- **`c_model = 1 − 1/conf`**. VGGT trả `conf = 1 + exp(x)` ∈ [1, ∞) (`vggt/heads/head_act.py`, `conf_activation="expp1"`);
  đề cương cần `c_model` ∈ [0,1] cho (19) nhưng không nêu cách đổi, đây là quyết định của nhóm. Ví dụ conf=1→0; 2,2→0,55;
  50→0,98. Đây là aleatoric confidence tỷ lệ với uncertainty, **không phải xác suất đã hiệu chuẩn** (ĐC §13, §23).
- Dùng depth head rồi unproject (README VGGT: thường chính xác hơn nhánh point map).

## Tham số

| Khoá | Giá trị | Nguồn |
|---|---|---|
| `vggt.chunk` | 12 | ĐC §7: c = 8–16 ảnh trên GPU 8 GB |
| `vggt.overlap` | 2 | ĐC §7.1: o = 2 |
| `vggt.dtype` | bf16 | nhóm chọn cho RTX 4060: aggregator ép về bf16, head giữ fp32, chạy autocast: chunk 12 ảnh peak 6.021 MiB (27/10); aggregator fp32 peak 9.486,7 MiB, vượt GPU 8 GB |
| `vggt.vram_fraction` | 0.95 | trần VRAM PyTorch (7,6 GiB trên 8 GiB); không có trần thì WDDM tràn sang RAM, `reserved` 10.024 MiB và chậm gấp ~2 lần (đo 27/10); 0.80 thì OOM do phân mảnh; 0 tắt trần |
| `vggt.weights_dir` | `../vggt_weights/VGGT-1B` | thư mục có `config.json` và `model.safetensors`, tương đối so với gốc repo, ngoài git |
| `vggt.c_model_map` | one_minus_inv | Suy luận (đã xác nhận) |

## Cách chạy riêng

```bash
# skip (cần GPU, trọng số VGGT-1B và keyframe của scene)
python -m pipeline.run --scene arkitscenes/42444738 --from-stage vggt --to-stage vggt
```

## Test vector và tiêu chí đạt

- `tests/test_chunks_and_vggt.py`: N_kf=72, c=12, o=2 → 7 chunk; khoảng chỉ số khớp Hình 7; hai chunk liền kề gối 2 ảnh; phủ
  mọi khung; `conf_to_c_model(1, 2,2, 50) = 0; 0,55; 0,98`; từ chối `conf < 1`.
- Tiêu chí đạt (M1–M2): peak VRAM < 8 GB (đo 6.021 MiB trên 42444738, chunk 12); camera 1 của chunk là gốc (q = [0,0,0,1], t = 0, ĐC §13).

## Lỗi thường gặp

- Đọc `depth_conf` như xác suất trong [0,1]: nó ở thang [1, ∞).
- Coi đầu ra VGGT là mét: bàn 1,40 m ra 0,215 đv VGGT (ĐC §13); cần mốc scale ([alignment](../alignment/README.md)).
- Nạp 40–80 ảnh thẳng vào VGGT: GPU 8 GB chỉ chịu 8–16 view mỗi lượt (ĐC §23).
- Cài `vggt` bằng `pip install -r vggt/requirements.txt` sẽ hạ torch xuống 2.3.1; dùng `pip install -e <vggt> --no-deps`.
- Đề cương không nêu cách nối chunk cho baseline B1; nhóm dùng chuỗi Umeyama trên ảnh gối (suy luận).

## Người phụ trách

@username2 (theo `.github/CODEOWNERS`).
