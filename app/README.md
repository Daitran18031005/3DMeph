# app/ — app Android quét phòng + backend GPU (M6)

Cơ chế giống các app quét 3D trên điện thoại: **quay có hướng dẫn trên máy → upload → PC có GPU dựng 3D → xem mô hình và đo hai điểm**.
Điện thoại không chạy VGGT/COLMAP. Hợp đồng theo ĐC §19 (Hình 23–24), không dùng Redis.

- `backend_fastapi/main.py`: FastAPI, hàng đợi một job (GPU 8 GB), mỗi stage chạy `python -m pipeline.run` ở process riêng. **Trạng thái: có test với runner giả; chạy thật qua HTTP trên gói kiểm từ scene dev.**
- `unity_app/`: project Unity 6000.5 (Android, AR Foundation 6.5 + ARCore, glTFast). Scene và cài đặt build được tạo bằng code (`Assets/Editor/BuildApp.cs`).
  Script chạy trên máy: `Assets/Scripts/{AppMain,CaptureRecorder,ModelViewer}.cs`. **Trạng thái: [chưa kiểm chứng trên điện thoại thật].**

## Chạy backend (PC, env 3d_metric, từ thư mục gốc repo)

```bash
# skip (server chạy mãi, không kết thúc)
python -m uvicorn app.backend_fastapi.main:app --host 0.0.0.0 --port 8000
```

Điện thoại và PC cùng Wi-Fi; mở cổng 8000 trên tường lửa Windows; trong app nhập `http://<IP LAN của PC>:8000`.

| Endpoint | Việc |
|---|---|
| `POST /jobs` | multipart `capture` = zip gói quay → `{job_id}` |
| `GET /jobs/{id}` | `{status, stage, progress, error_code, message}`; `status`: `queued → keyframe → colmap+vggt → fusion → plane → export → done` hoặc `failed` |
| `GET /jobs/{id}/result` | `model.glb` (mét, +Y lên) |
| `GET /jobs/{id}/measurements` | `measurements.json` |

Kết quả mỗi job ở `data/scenes/app/<job_id>/` (cùng cây thư mục với các scene khác; `job.json` lưu trạng thái).

## Gói quay (`capture.zip`)

`frames/NNNNNN.jpg` + `capture.json`:
`{"device", "scale_mode": "ar" | "tape", "anchor": {"L_real", "A": [x,y,z], "B": [x,y,z]} (chỉ tape), "frames": [{"name", "t", "w", "h", "fx", "fy", "cx", "cy", "T_cam_world": 4×4}]}`.
`T_cam_world` là world→camera, quy ước camera OpenCV (x phải, y xuống, z tới), world tay phải, mét (app đổi từ hệ Unity: lật y camera, lật z world).

**Hai chế độ scale** (người dùng chọn trên app):
- `ar`: `s_m` = scale Umeyama bền giữa tâm camera COLMAP và tâm camera ARCore (`pipeline/alignment/ar_metric.py`). **Lệch ĐC §8.1** (không phải mốc (4)); đã ghi WORKING_LOG.
- `tape`: người dùng chạm hai đầu mút một đoạn 1–2,5 m trên màn hình AR và nhập số đo thước dây; server chiếu A, B vào keyframe, tam giác hoá bằng camera COLMAP → `L_model`, `s_m = L_real / L_model` theo (4). AR chỉ định vị đầu mút.

**Hạn chế đã đo (kiểm chức năng trên 42444738, pose ARKit đóng vai ARCore, 17/11; WORKING_LOG):**
- `tape`: đầu mút định vị bằng pose AR nên mang sai số hướng của pose. Mốc S06 (2,41 m) chiếu từ AR rồi tam giác hoá cho **+3,9%** (đầu mút lệch tới ~18 cm), trong khi click tay trên ảnh (CLI) cho −2,2% và độ dài eval ≈ 1 cm. Chế độ này **chưa chính xác hơn `ar`**; muốn chính xác như CLI cần click đầu mút trên ảnh (`scripts/click_anchor_2d.py`).
- `ar`: scale quỹ đạo ARKit tự lệch ~2% ở scene này. Chưa đo trên ARCore thật.

Mã lỗi: `E_TOO_FEW_KEYFRAMES`, `E_SFM_FAILED`, `E_AR_SCALE` (không đủ camera chung, mốc không đủ view), `E_STAGE_FAILED` (lỗi khác).

## Build APK (Windows)

```bash
# skip (build APK mất ~10 phút, cần Unity)
"C:\Program Files\Unity\Hub\Editor\6000.5.6f1\Editor\Unity.exe" -batchmode -quit -projectPath app/unity_app -executeMethod BuildApp.Build -logFile build.log
```

Ra `app/unity_app/Build/Room3D.apk` (ARM64, Android ≥ 8.0, cần máy hỗ trợ ARCore). Cài: `adb install -r app/unity_app/Build/Room3D.apk`.
App khoá màn hình ngang (LandscapeLeft) để hướng camera khớp ảnh CPU của ARCore.

## Kiểm không cần điện thoại

`python scripts/arkit_to_capture.py --scene 42444738 --mode ar|tape [--tape S06] --out cap.zip` đóng gói một scene ARKitScenes (pose ARKit đóng vai ARCore)
rồi gửi `curl -F capture=@cap.zip http://127.0.0.1:8000/jobs`. Chỉ là kiểm chức năng, không phải kết quả đánh giá.
