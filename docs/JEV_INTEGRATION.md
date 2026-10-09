# Jev / TypeSafe AI - native typed decisions

Đã đối chiếu với OpenAPI chính thức ngày 09/10/2026: https://api.typesafe.ai/openapi.json . Hash của schema đã đọc và các trường client sử dụng nằm ở `docs/contracts/jev_contract.json`.

## Chỉ điền kết nối

```dotenv
JEV_BASE_URL=https://api.typesafe.ai
JEV_API_KEY=
JEV_MODEL=jev-latest
JEV_MIN_CONFIDENCE=0.85
```

Chỉ URL/key cần thay theo tài khoản nhóm; model/threshold có mặc định. Cũng nhận `TYPESAFE_API_KEY` để tương thích cách đặt tên của TypeSafe. Base URL host, `/v1` hoặc full `/v1/systemone` đều được chuẩn hóa. Gateway khác cần phục vụ hợp đồng TypeSafe này.

## Vai trò trong sản phẩm

Pipeline tính dữ liệu trước → LLM tổng hợp nếu bật → Jev nhận trạng thái và quyết định có cấu trúc → mã nguồn áp dụng điều kiện dữ liệu/confidence/review → Web/PDF hiển thị cả đề xuất và quyết định sau kiểm tra.

Một lời gọi có hai câu hỏi:

- `research_action` - Choice trong tập đóng: `insufficient_data`, `needs_review`, `watchlist`, `risk_caution`.
- `requires_review` - Noul, xác suất model đánh giá cần review.

Client kiểm tra tên câu hỏi, kiểu câu trả lời, lựa chọn được khai báo, phân phối xác suất và usage. `confidence` và `probabilities` được giữ riêng; confidence không phải xác suất lợi nhuận đầu tư. Noul không được ép thành integer hay làm tròn trước khi so ngưỡng.

Mã nguồn bắt buộc review khi dữ liệu/demo/chất lượng còn vấn đề, hoặc confidence dưới `JEV_MIN_CONFIDENCE`, hoặc Noul review từ 0.5. Ngưỡng là chính sách ứng dụng, cần TV5 đánh giá trên dữ liệu thật. Jev không tạo số tài chính, không tự giao dịch và không thay việc đối chiếu dữ liệu.

## Vận hành và kiểm thử

Bật trên Web hoặc thêm `--jev` vào CLI. Key chỉ dùng ở backend. Timeout đọc 30 giây; không tự retry lời gọi tính phí; lỗi xác thực/schema/timeout dẫn đến `needs_review` và ghi rõ `unavailable/error`.

`pytest tests/test_jev.py -q` kiểm tra endpoint, thiếu key, kiểu phản hồi, lựa chọn không khai báo, xác suất sai và việc Jev không bỏ qua guard của dữ liệu demo. Đây là test mock. Nhóm cần chạy authenticated smoke bằng key riêng và lưu bằng chứng model/usage/latency trước nghiệm thu live.

Phân công: TV5 sở hữu `analysis/jev.py` và chất lượng quyết định; TV1 cấu hình/quản lý key; TV6 hiển thị Jev trong UI/PDF. LLM và Jev dùng hai bộ URL/key độc lập.
