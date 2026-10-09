# TV6 - Web, PDF và kiểm thử sản phẩm

Nhánh: `member06-ui-pdf-qa`. Sở hữu `static/`, `reports/`, demo và QA sản phẩm. Nhận Report từ TV5 và API từ TV1.

## Có sẵn

Web tiếng Việt, chọn nhu cầu/nội dung, upload CSV, theo dõi tác vụ, tải PDF/JSON/manifest; font tiếng Việt, biểu đồ doanh thu và danh mục nguồn trong PDF.

## Công việc cần hoàn thiện

1. Hoàn thiện trải nghiệm đa mã: biểu đồ giá, tài chính, ngành, vĩ mô và phân biệt trạng thái tác vụ với chất lượng dữ liệu.
2. Bổ sung nguồn dẫn dễ mở, hiển thị đơn vị rõ, bảng dài có lọc; không tự tính tỷ số khác backend.
3. Hoàn thiện PDF theo nhu cầu: vĩ mô, ngành, doanh nghiệp, cơ hội, định giá, catalyst, rủi ro và nguồn; bố cục đẹp, không mất dấu hoặc tràn bảng.
4. Kiểm tra mỗi bản PDF thay đổi bằng render ảnh thật; kiểm tra JSON và SHA-256 trong manifest.
5. Chạy demo người dùng từ nhập mã đến tải file, lỗi nguồn, thiếu dữ liệu, API AI, nhiều tác vụ và khởi động lại. Lập hồ sơ bằng chứng bàn giao.

## Bàn giao / điều kiện đạt

Web hoạt động và PDF thực cho các ca nghiệm thu. Demo luôn có nhãn giả lập trên mọi trang; dữ liệu thật thiếu không được trình bày như kết luận đã xác nhận. TV6 tổng hợp QA, TV1 quyết định ghép bản nộp cùng cả nhóm.

Chạy: `pytest tests/test_jobs_and_pdf.py -q`; `vnresearch serve` và kiểm tra luồng Web.
