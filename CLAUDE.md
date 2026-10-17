@AGENTS.md

AGENTS.md là luật chung; file này chỉ thêm phần riêng cho Claude, không được mâu thuẫn với AGENTS.md.
Mâu thuẫn xảy ra thì AGENTS.md thắng, rồi báo cho người dùng.

## Cách làm việc

- **Việc lớn** (nhiều module, tải dữ liệu, đổi cấu trúc, đổi hợp đồng file giữa stage): vào chế độ **Plan** trước, chờ duyệt.
  **Việc nhỏ** (sửa lỗi, một hàm, một README): làm thẳng.
- Theo dõi bằng danh sách nhiệm vụ (TaskCreate/TaskUpdate; trong Claude desktop app công cụ này là `update_plan`).
  Bước cuối của mỗi nhiệm vụ là **kiểm tra** (`pytest`, `ruff`, `scripts/check_docs.py`, hoặc tiêu chí đo được của việc đó)
  rồi **cập nhật `WORKING_LOG.md`** (quy tắc ở AGENTS.md mục 10): chỉ ☑ khi có bằng chứng, dry-run không tính là xong.
- Dùng Read/Edit/Write/Grep/Glob cho việc file thông thường, không dùng lệnh shell thay thế. Không tạo file ngoài phạm vi nhiệm vụ.
- Tải dữ liệu, push, PR, xoá nhánh/file, sửa `.gitignore`, `create_env.bat` thật: **hỏi trước** (AGENTS.md mục 7). **Không bật
  auto-accept** cho các thao tác đó.

## Khi gặp chỗ lệch

Kế hoạch mâu thuẫn PDF hoặc dữ liệu thật: **dừng, nêu rõ chỗ lệch (nguồn nào nói gì), hỏi**. Không tự quyết rồi im lặng.
Ghi chỗ lệch vào `WORKING_LOG.md` mục "Lệch so với kế hoạch".

## Báo cáo

- Cuối mỗi nhiệm vụ: **2–3 câu** kết quả, file đã đổi, **một** bước tiếp theo hợp lý. Không kể lại từng bước.
- Nói rõ cái gì đã chạy thật, chỉ dry-run, hay chưa kiểm chứng.
- Tiếng Việt, giải thích dễ hiểu, có ví dụ số khi hợp lý. Dẫn nguồn theo [ĐC §x] / số công thức (n) của PDF.
- Chỉ commit khi được yêu cầu; commit kết thúc bằng dòng `Co-Authored-By` theo hướng dẫn của app.
