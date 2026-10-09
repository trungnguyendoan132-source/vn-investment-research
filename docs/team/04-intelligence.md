# TV4 - Tin, tài liệu và bằng chứng

Nhánh sở hữu: `member04-news-documents`. TV4 phụ trách `intelligence/`, từ điển trích bằng chứng và các adapter vendor được ghi nhận trong manifest. Đầu ra là nguồn có ngày, URL/trang và nội dung truy vết được cho TV5.

## Kế thừa có chọn lọc

Repo giữ dictionary, matcher, snippet extractor, scraper đa nguồn và bộ kiểm tra BCTN từ nguồn upstream. Adapter mới dùng đường dẫn trong package, giữ xác minh TLS và chỉ áp bộ kiểm tra BCTN khi người gọi xác định đúng loại tài liệu. Không đưa server cũ, khóa nhúng hoặc quy trình bootstrap upstream vào ứng dụng.

## Đã triển khai trên nhánh TV4

- Tin nhận ngày ISO hoặc `DD/MM/YYYY`, loại tin thiếu ngày, quá ngày chốt hoặc cũ hơn 365 ngày; kiểm tra ticker theo token và alias ranh giới từ danh mục TV2.
- Chuẩn hóa URL HTTP(S), loại tracking khỏi khóa chống trùng nhưng vẫn giữ URL gốc trong nguồn. Giới hạn kết quả sau khi sắp xếp tin mới nhất.
- Giữ nguyên tiêu đề, nội dung và đoạn trích nguồn. SHA-256 tin băm các trường bài đã trích; đây không phải hash byte HTML gốc. Mẫu giống chỉ thị được gắn cờ heuristic, không được coi là đã làm sạch hay bảo đảm an toàn cho mô hình.
- PDF được mở từ đúng byte đã băm và kiểm định BCTN. Metadata tác giả/ngày tạo không được dùng làm tổ chức phát hành/ngày công bố. Tổ chức, ngày và ticker chỉ được gán khi có nhãn/ngữ cảnh tường minh; còn lại để unknown hoặc liệt kê ứng viên.
- Evidence giữ nguyên văn theo trang. Trang scan chưa đọc được được liệt kê; trang OCR trích được vẫn trả trạng thái `partial` để yêu cầu đối chiếu người thật.

## Còn phải nghiệm thu trước khi nộp

1. Kiểm tra nguồn live trên thời điểm chạy và lưu ví dụ nhiều mã/ngành, gồm URL, ngày công bố và nội dung truy xuất được. Test offline không xác nhận nguồn đang hoạt động.
2. Đối chiếu PDF/BCTC/BCTN và báo cáo CTCK thật: tổ chức phát hành, ngày, ticker, số trang, byte hash; kiểm tra thủ công OCR trên mẫu scan đại diện.
3. Soát alias cho danh mục toàn thị trường và các mã dễ nhầm; hiệu chỉnh theo dữ liệu báo có nguồn thay vì coi heuristic là xác minh tuyệt đối.
4. TV5 phải xem mọi văn bản ngoài là dữ liệu không tin cậy và không thực thi chỉ thị trong nguồn. Mask heuristic của TV4 không phải hàng rào prompt-injection.

Test nhánh: `python -m pytest tests/test_intelligence.py -q`; lint: `python -m ruff check src tests`. Kết quả kiểm thử mock/offline không chứng minh chất lượng nguồn live.

Chạy kiểm tra PDF: `vnresearch inspect-pdf path/to/report.pdf`; thêm `--annual-report` chỉ khi tài liệu là BCTN.
