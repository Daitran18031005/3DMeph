# pipeline/

Lõi kỹ thuật của 3DMeph: **hai nhánh độc lập** (COLMAP hình học và VGGT học sâu) rồi căn, ghép, làm phẳng, xuất mesh.
Mỗi thư mục là một node hoặc nhóm node của `3dmeph-dataflow.html` và có README riêng (vai trò, input/output, công thức,
tham số, cách chạy, test vector, lỗi thường gặp, người phụ trách). Công thức chi tiết nằm ở README từng module, không lặp lại ở đây.

| Thư mục | Node dataflow | Làm gì | Trạng thái |
|---|---|---|---|
| [keyframe](keyframe/README.md) | Keyframes Input | xoay đứng theo `sky_direction`, lọc, `q_blur`, `q_exposure` | xoay ảnh + test; chưa có lọc |
| [colmap](colmap/README.md) | COLMAP SfM, MVS, SfM Output | SfM + MVS bằng CLI 4.2; tín hiệu `e_reproj`, `σ_depth` | đã kiểm tương thích; chưa có stage |
| [vggt](vggt/README.md) | VGGT Inference, VGGT Output | VGGT theo chunk; `c_model` | chia chunk + `c_model`; chưa có infer |
| [alignment](alignment/README.md) | Scale Alignment | Umeyama + RANSAC trên tâm camera, mốc scale → mét | lõi toán + test; chưa có stage |
| [fusion](fusion/README.md) | Confidence Fusion | trọng số sáu tín hiệu, `P̂_k`, `w_k` | lõi toán + test; chưa có stage |
| [plane_gate](plane_gate/README.md) | Plane-Gated Filter | cổng bốn điều kiện, kéo về mặt phẳng | lõi toán + test; chưa có RANSAC mặt phẳng |
| [export](export/README.md) | GLB Mesh Output | Poisson → GLB; đo hai điểm | đo hai điểm; chưa có mesh |
| [eval](eval/README.md) | *(ngoài dataflow)* | chỉ số, bảng B0…Proposed | hàm chỉ số + test; chưa có stage |
| [common](common/README.md) | *(dùng chung)* | cấu hình, I/O, hình học, chất lượng ảnh | đủ |

**Quy ước chung**
- Các stage giao tiếp **qua file**, không qua RAM (GPU 8 GB không giữ VGGT và COLMAP cùng lúc). Tên file và schema: README gốc,
  mục "Cây một scene", và `common/schema.py`.
- Chỉ số: **i = view**, **k = điểm/correspondence**. Theo (i,k): `c_model, e_reproj, σ_depth, q_texture`; theo view i: `q_blur, q_exposure`.
- Ký hiệu theo đề cương: `w` là trọng số **thô** (19), `w̃` là **đã chuẩn hóa** (22); thang đổi sai số là `τ_e, τ_σ`.
- Tham số nằm ở `configs/default.yaml`; README module liệt kê khoá đúng tên (kiểm bởi `scripts/check_docs.py`). Tham số `null` nghĩa là chưa
  có căn cứ và phải khoá trên 6 scene Validation.
- Luôn `import pipeline` (đã `import torch` trước) trước `open3d`/`cv2`/`pycolmap`.

Lệnh chạy cả pipeline (`python -m pipeline.run --scene …`) chưa có; dự kiến M1.
