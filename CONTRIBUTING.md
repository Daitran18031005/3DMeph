# Quy trình làm việc nhóm — 3DMeph (4 người)

## 1. Nhánh
- `main` luôn chạy được, KHÔNG push trực tiếp lên main.
- Mỗi việc = 1 nhánh: `feature/<mo-ta-ngan>` (vd: feature/colmap-uncertainty-export)
- Làm xong mở Pull Request vào main, cần tối thiểu 1 approve mới được merge.

## 2. Trước khi bắt đầu code mỗi ngày
    git checkout main
    git pull --rebase origin main
    git checkout -b feature/ten-viec-cua-ban

## 3. Trong lúc làm
- Commit nhỏ, message rõ ràng, theo dạng: feat(fusion): them q_blur threshold
- Báo trong nhóm chat nếu đang sửa file/thư mục có khả năng trùng người khác.

## 4. Trước khi mở PR
    git pull --rebase origin main    # đồng bộ sớm, xử lý conflict khi còn nhỏ
    git push origin feature/ten-viec-cua-ban

## 5. Review
- CODEOWNERS sẽ tự gợi ý đúng người theo thư mục bạn sửa.
- Không tự merge PR của chính mình trừ khi cả nhóm đã đồng ý trước.

## 6. File đặc biệt — KHÔNG đồng biên tập qua git
- .docx khoá luận: dùng Google Docs khi cần 2+ người sửa cùng lúc, export lại
  .docx định kỳ để lưu vào thesis/. Không dùng git để đồng biên tập văn bản.
- Notebook .ipynb: cài nbstripout trước khi commit để tránh conflict giả:
      pip install nbstripout && nbstripout --install
- File Unity (.unity, .prefab): Edit > Project Settings > Editor >
  Asset Serialization > Force Text — để lưu dạng text, dễ diff hơn binary thật.
  Asset nhị phân lớn (texture, fbx) nên dùng Git LFS.
