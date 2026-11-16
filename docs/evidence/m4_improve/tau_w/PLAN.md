# Chọn lại τ_w (plane.tau_w, công thức (24)) theo leave-one-scene-out — GHI TRƯỚC KHI CHẠY

Ngày 2026-11-16, người dùng yêu cầu ("Chạy τ_w ngay"). Mốc: cấu hình mặc định hiện tại (đã gồm sửa cổng đợt 3d), τ_w = 0,5 (số ví dụ §17.1).
Lý do: `../gate_diagnosis/` đo được τ_w = 0,5 nằm trên ~95% `w_k` (trung vị 0,15–0,23, p95 0,45–0,60), nên cổng gần như không mở.
Chỉ đổi τ_w; τ_r, τ_n, α giữ nguyên. Không ảnh hưởng độ phủ (điểm không qua cổng vẫn giữ theo (24)).

**Lưới (đặt trước, không thêm sau khi xem số):** τ_w ∈ {0,2; 0,3; 0,4} so với mốc 0,5.
**Cách chạy:** `scripts/gate_variants.py --name tw0XX --set plane.tau_w=0.X --out-root data/sweeps/m4_tauw`, 6 scene (5 Validation + dev), chỉ chạy lại `gate`, không đụng `proposed/`.
Chỉ số và ngưỡng dùng lại đúng hàm `check()` của `gate_variants.py` (đã dùng cho đợt 3d), so với mốc `tw050`.

**Một giá trị "đạt" trên một tập scene khi ĐỒNG THỜI:**
- Lợi ích: tỉ lệ điểm qua cổng trung bình ≥ 1,5 × mốc.
- A2: độ chính xác của điểm qua cổng (≤ 5 cm so với Faro) giảm không quá 0,02.
- A3: số scene có sai số trung vị điểm bị kéo giảm không ít hơn mốc; tỉ lệ điểm cải thiện giảm không quá 0,02.
- A4: ΔF trung bình ≥ −0,005; Chamfer không tệ hơn +2%; không scene nào ΔF < −0,010.
Giữa các giá trị đạt, chọn giá trị NHỎ NHẤT (cổng mở nhiều nhất).

**Leave-one-scene-out:** với mỗi scene X (6 lần): chọn giá trị trên 5 scene còn lại theo quy tắc trên, rồi kiểm trên X: độ chính xác điểm qua cổng không giảm quá 0,02 và ΔF ≥ −0,010.
**Nhận đổi mặc định** khi cùng một giá trị được chọn ở ≥ 5/6 lần bỏ VÀ giá trị đó qua kiểm trên scene bỏ ra ở ≥ 5/6 lần. Ngược lại giữ 0,5.
Giới hạn: lợi ích thật của cổng (P2Plane, plane recall) chỉ đo được trên Replica (M5); ở đây chỉ chứng minh "mở cổng mà không hại".
