# Quy trình làm chung cho 6 thành viên

1. Đọc README, ma trận yêu cầu và tài liệu vai trò trong `docs/team/`.
2. Clone repo. Chuyển sang nhánh được phân công, ví dụ `git switch member02-market-financial-data`.
3. Trước khi làm việc: `git fetch origin`, sau đó `git merge origin/main` trên nhánh cá nhân. Không dùng force push lên nhánh chung.
4. Thay đổi trong phần sở hữu; sửa contract chung cần TV1 và người nhận dữ liệu review.
5. Chạy `pytest -q`, `ruff check src tests`; với thay đổi dữ liệu/AI/PDF cần bằng chứng riêng theo README.
6. Commit rõ chức năng, push nhánh rồi tạo pull request vào `main`. Dùng mẫu PR, ghi TV phụ trách và yêu cầu đề bài được xử lý.
7. TV1 tích hợp; ít nhất một thành viên khác review. TV6 chạy lại luồng Web và kiểm tra PDF trước chốt bản nộp.

## Trình tự tích hợp

- Mốc 1: TV1 chốt contract; cả nhóm chạy được demo trên máy mình.
- Mốc 2: TV2/TV3/TV4 đưa dữ liệu thật và provenance vào contract; TV5 kiểm tra công thức và phát triển định giá/AI; TV6 hoàn thiện UI/PDF.
- Mốc 3: TV1 + TV5 ghép pipeline; TV6 kiểm tra đa mã và lỗi nguồn; mỗi người bổ sung bằng chứng trong ma trận yêu cầu.
- Mốc 4: nhóm chốt báo cáo/demo, đóng các mục nghiệm thu bắt buộc rồi mới xác nhận bài nộp hoàn thành.

## Quy tắc dữ liệu và bí mật

Không commit `.env`, API key, dữ liệu người dùng trong `var/` hay nhật ký chứa token. Mã kế thừa thay đổi phải cập nhật `third_party/upstream_manifest.json` và ghi lý do. Không sửa asset dữ liệu chỉ để làm test đạt. Không coi dữ liệu demo hoặc model trả lời thành công là bằng chứng chất lượng phân tích.

## Cấp quyền GitHub

Repo được tạo riêng tư. Chủ repo mời tài khoản GitHub của 5 thành viên còn lại qua Settings → Collaborators. Các nhánh TV1–TV6 là nơi nhận việc; chúng không tự cấp quyền truy cập. Tên người và quyền cần được chủ repo gắn theo danh sách nhóm thực tế.

## Bật CI cho repo

Mẫu Windows/Linux đã chuẩn bị trong `docs/ci/github-actions.yml`; bản bàn giao chưa bật/chạy workflow GitHub Actions. TV1 dùng thông tin xác thực có quyền `workflow` để đưa mẫu vào vị trí hoạt động:

```powershell
New-Item -ItemType Directory -Force .github/workflows
Copy-Item docs/ci/github-actions.yml .github/workflows/ci.yml
```

TV1 commit/push thay đổi trên nhánh cá nhân và mở PR, xem kết quả trong tab Actions trước khi ghi CI đạt. Quyền `repo` của token hiện tại chưa đủ để tạo/cập nhật workflow; mẫu nằm trong `docs/ci/` để repo vẫn được bàn giao. Mọi thành viên tiếp tục chạy `pytest -q` và `ruff check src tests` trên máy trước PR.
