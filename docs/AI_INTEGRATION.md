# API AI và ranh giới bằng chứng

Chủ trì TV5; TV1 quản lý cấu hình/khóa; TV4 cung cấp bằng chứng; TV6 trình bày kết quả có dẫn nguồn.

## Cấu hình

Ứng dụng đọc `.env` trong thư mục chạy hoặc biến môi trường có sẵn. Không có khóa fallback. Mẫu gồm `VNRESEARCH_AI_BASE_URL`, `VNRESEARCH_AI_API_KEY`, `VNRESEARCH_AI_MODEL`. Base URL phải HTTPS và có schema Chat Completions tương thích. Model do nhóm chọn theo tài khoản và khả năng hỗ trợ JSON.

Lời gọi gửi model, messages, response_format JSON object và max_completion_tokens=1200. Timeout kết nối 8 giây, đọc 45 giây. Không tự retry khi nhà cung cấp lỗi để tránh lặp chi phí. Bật `use_ai=true` hoặc `--ai` là yêu cầu gọi AI; mặc định tắt.

## Dữ liệu được gửi

Mã/nhóm ngành, hai kỳ tài chính cuối, các bảng tóm tắt giới hạn số dòng, danh sách nguồn và vấn đề chất lượng. Không gửi file `.env`, token tác vụ, API key trong prompt, hoặc tài liệu cá nhân. Lời gọi AI là thao tác bên ngoài hệ thống; nhóm lựa chọn endpoint phù hợp.

## Kiểm tra đầu ra

JSON gồm tối đa 6 claims. Mỗi claim có text và source_ids. Pydantic kiểm tra cấu trúc/độ dài, source_ids phải thuộc bằng chứng đã gửi; nhận xét có chữ số bị loại. Số liệu tính toán được trình bày bằng bộ tính riêng và giữ nguyên trong Report.

Nguồn dẫn tồn tại không tự chứng minh nguồn hỗ trợ nội dung. TV5 cần đánh giá đối chiếu từng claim, thiếu dữ liệu, suy diễn ngành, prompt injection và mâu thuẫn tài liệu. Kết quả hiện kèm ghi chú chưa thay thế review.

## Nghiệm thu của TV5

- Kiểm tra thiếu khóa/model, HTTP lỗi, timeout, JSON sai, nguồn giả, số AI tự tạo và phản hồi trống.
- Chạy model thật trên nhiều ngành và lưu tên model, thời gian, token/chi phí do provider trả nếu có, cùng bộ đánh giá claim → nguồn.
- Bổ sung adapter cấu trúc JSON Schema khi provider hỗ trợ; nếu gateway có schema khác phải viết adapter riêng, không tự bỏ kiểm tra để nhận phản hồi.
- Không tuyên bố chất lượng AI live từ các test mock của sườn.

Tham chiếu chính thức: https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create .
