# TV1 - Nền tảng, API và tích hợp

Nhánh: `member01-platform`. Sở hữu `api/`, `platform/`, `domain/`, CI. Review cùng TV5 khi sửa pipeline và cùng TV6 khi sửa contract Web.

## Có sẵn

FastAPI, schema Pydantic, SQLite lưu tác vụ, token từng tác vụ, file kết quả riêng, API upload CSV, kiểm tra mã tác vụ/loại file và cấu hình khóa truy cập mạng.

## Công việc cần hoàn thiện

1. Chốt contract 1.0.0 với cả nhóm; kiểm tra provider trả đúng đơn vị/kỳ/nguồn.
2. Bổ sung tài khoản nhóm, phân quyền nguồn upload và chính sách xóa/lưu dữ liệu nếu triển khai dùng chung.
3. Quản lý giới hạn hàng đợi, hủy tác vụ và chạy lại có kiểm soát. Worker hiện dùng thread; SQLite giữ trạng thái nhưng không tự tiếp tục tác vụ sau restart.
4. Cấu hình môi trường phát triển/triển khai, kiểm tra sức khỏe nguồn, ghi lỗi không lộ key và giám sát thời gian từng giai đoạn.
5. Tích hợp PR của TV2–TV6; cập nhật ma trận nghiệm thu và báo cáo kiểm chứng cuối.

## Bàn giao / điều kiện đạt

API contract ổn định, test token/quyền và nhiều tác vụ, không ghi đè file, restart đánh dấu đúng việc dở dang. Lưu bằng chứng build, CI và luồng thực; HTTP 202 không được coi là tác vụ hoàn tất.

Chạy: `pytest tests/test_jobs_and_pdf.py tests/test_contracts.py -q`.
