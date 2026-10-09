# TV4 - Tin, tài liệu và bằng chứng

Nhánh: `member04-news-documents`. Sở hữu `intelligence/`, `_vendor/`, từ điển. Nhận universe TV2; bàn giao bài/tài liệu có nguồn cho TV5.

## Kế thừa / có sẵn

Dictionary, matcher, snippet extractor, scraper đa nguồn, bộ kiểm tra BCTN và danh bạ website. Đã bỏ fallback tắt TLS và loại tin không rõ ngày trong adapter mới. PDF text được trích theo trang; trang scan hiện đánh dấu cần OCR.

## Công việc cần hoàn thiện

1. Kiểm tra các nguồn tin thật còn hoạt động; giới hạn truy vấn, chuẩn ngày công bố và xác nhận đúng doanh nghiệp.
2. Thu thập BCTN/BCTC và báo cáo CTCK nhóm chọn sử dụng; lưu tổ chức phát hành, ngày, ticker, trang và hash.
3. Hoàn thiện OCR cho trang scan; đo chất lượng trên PDF thật và không coi text trống là không có thông tin.
4. Trích bằng chứng liên quan catalyst, rủi ro, chiến lược và sự kiện vốn; giữ nguyên văn và ngữ cảnh. Tần suất từ khóa không đại diện cho khuyến nghị hay sentiment đã xác nhận.
5. Chống trùng URL/nội dung, xử lý bài không rõ ngày, tài liệu sai ticker và prompt injection trong văn bản khi chuyển sang TV5.

## Bàn giao / điều kiện đạt

Tin cập nhật và tài liệu thật đa mã, có ngày/trang/URL; test sai ngày, sai doanh nghiệp, scan, trùng bài và lỗi nguồn. Thay mã vendor phải ghi thay đổi trong manifest.

Chạy: `vnresearch inspect-pdf path/to/report.pdf`; thêm `--annual-report` chỉ khi là BCTN.
