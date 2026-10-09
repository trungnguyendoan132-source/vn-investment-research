# Audit repo tham khảo và định hướng sản phẩm theo đề bài

Ngày kiểm tra: 09/10/2026, múi giờ Asia/Bangkok.

Repo: [Tumiqa/vn-annual-report-miner](https://github.com/Tumiqa/vn-annual-report-miner). Bản mã đã kiểm tra: `f8cad8d7d4276cd22aee20113fe3214230daf919`.

**Kết luận:** Nhóm cần xây sản phẩm đáp ứng đề bài. Repo là nguồn tham khảo tốt cho việc thu thập, khai phá và tổ chức dữ liệu doanh nghiệp. Nên chọn các mô-đun phù hợp để tái sử dụng sau khi sửa và kiểm chứng; phần phân tích đầu tư là phần nhóm cần thiết kế thêm. Các tính năng ngoài phạm vi repo được liệt kê dưới đây là phạm vi phát triển của nhóm, không phải lỗi của repo.

## 1. Đọc đúng đề bài

Đề yêu cầu thiết kế, xây dựng và vận hành hệ thống phân tích **tổng quan vĩ mô, ngành và cơ hội đầu tư vào cổ phiếu bất kỳ**, rồi **tự động xuất báo cáo phân tích PDF theo nhu cầu người dùng**. Yêu cầu chất lượng là dữ liệu chính xác, kết quả phân tích đáng tin cậy và sự sáng tạo. Hạn nộp ghi trong ảnh: **16:20 ngày 09/10/2026**.

Danh sách giá/giao dịch, báo cáo tài chính, tin doanh nghiệp, báo cáo công ty chứng khoán và nguồn phù hợp khác là các nguồn có thể khai thác. Đề không quy định nhóm phải sao chép repo, dùng đủ mọi nguồn trong danh sách, hay bắt buộc dùng LLM.

Luồng sản phẩm cần có: người dùng chọn mã cổ phiếu và nhu cầu → lấy dữ liệu và kiểm tra chất lượng → phân tích vĩ mô, ngành, doanh nghiệp và cơ hội đầu tư → tạo PDF có căn cứ số liệu và nguồn trích dẫn.

## 2. Repo có gì dùng làm nền

| Thành phần | Bằng chứng trong mã nguồn | Cách sử dụng cho sản phẩm của nhóm |
|---|---|---|
| Kho BCTN và tải PDF nguồn | `data/catalog.py`, `data/zenodo_downloader.py`, `data/bctn_validator.py` | Dùng làm tầng tài liệu nguồn và tra cứu báo cáo. PDF tải về là tài liệu đầu vào. |
| Đọc văn bản và khai phá từ khóa | `ocr/engine.py`, `mining/matcher.py`, `mining/snippet_extractor.py` | Tìm đoạn bằng chứng trong tài liệu doanh nghiệp. Chưa xác nhận toàn bộ đường OCR trên PDF scan thật. |
| Báo cáo tài chính | `data/financial.py`, sáu tệp `data/bctc_data/*/*.parquet` | Tham khảo cách chuẩn hóa BCTC và tạo bảng dữ liệu theo mã/năm. Cần thống nhất một bộ công thức và xử lý dữ liệu thiếu. |
| Tin doanh nghiệp | `data/news_scraper.py` | Tham khảo thu thập đa nguồn, xác nhận doanh nghiệp và loại trùng; cần sửa kiểm tra thời gian. |
| Phân ngành | `data/industry.py` | Dùng ánh xạ mã cổ phiếu sang ngành. Phân loại ngành là đầu vào cho phân tích ngành. |
| Web và tiến độ xử lý | `ui/server.py`, `ui/static/` | Tham khảo FastAPI và SSE; cần tách tác vụ, tệp kết quả và quyền truy cập khi phục vụ nhiều người dùng. |
| Xuất bảng dữ liệu | `export/financial_excel.py`, `export/exporter.py` | Dùng làm đầu ra dữ liệu hoặc phụ lục; phát triển thêm bộ tạo báo cáo phân tích PDF. |

[Các mô-đun dữ liệu tại commit đã kiểm tra](https://github.com/Tumiqa/vn-annual-report-miner/tree/f8cad8d7d4276cd22aee20113fe3214230daf919/src/arminer/data), [giao diện và API](https://github.com/Tumiqa/vn-annual-report-miner/tree/f8cad8d7d4276cd22aee20113fe3214230daf919/src/arminer/ui).

Đã đọc trực tiếp sáu tệp Parquet: **1.921.197 dòng**, bao gồm bảng cân đối, kết quả kinh doanh và lưu chuyển tiền tệ trên HSX/HNX. Các tệp đều có năm lớn nhất là **2025**. Mỗi tệp HSX chứa 409 mã riêng biệt; mỗi tệp HNX chứa 307 mã riêng biệt. Đây là số đếm theo tệp, không phải số doanh nghiệp duy nhất sau khi hợp nhất hai sàn. Không suy ra mọi mã đều có đủ năm hay đủ chỉ tiêu. Dữ liệu có `source_file` và `source_sheet`, thuận tiện truy vết nguồn.

Mã định nghĩa **116 tỷ số**. Con số này là số định nghĩa công thức, không chứng minh 116 tỷ số đều tính được hoặc đều chính xác cho mọi doanh nghiệp. Danh bạ website hiện chứa **1.581 bản ghi**; số bản ghi không chứng minh tất cả website còn truy cập được.

## 3. Các lỗi và rủi ro cần tránh khi tái sử dụng

P1: ưu tiên sửa trước khi dùng kết quả phân tích. P2: sửa để bảo đảm độ tin cậy và vận hành. Các kết quả số dưới đây dùng dữ liệu đối chứng tự tạo; không phải số liệu thực của doanh nghiệp niêm yết.

| Mức | Phát hiện đã xác minh | Ảnh hưởng và cách xử lý |
|---|---|---|
| P1 | **Current ratio của CLI sai và khác Web.** Với tổng tài sản 1.000, tổng nợ 500, tài sản ngắn hạn 300 và nợ ngắn hạn 100: CLI trả **2**, bộ tính của Web trả **3**. | CLI đang dùng tổng tài sản/tổng nợ. Dùng tài sản ngắn hạn/nợ ngắn hạn; thống nhất bộ tính cho mọi giao diện. [Nguồn](https://github.com/Tumiqa/vn-annual-report-miner/blob/f8cad8d7d4276cd22aee20113fe3214230daf919/src/arminer/data/financial.py#L147-L149). |
| P1 | **YoY không kiểm tra năm liền kề.** Chỉ có doanh thu 2022 = 100 và 2024 = 121, hàm vẫn trả YoY 2024 = **21%**. | Mức tăng qua hai năm bị gán nhãn tăng trưởng một năm. Cần nối dữ liệu đúng năm T−1; thiếu năm thì để trống và nêu lý do. [Nguồn](https://github.com/Tumiqa/vn-annual-report-miner/blob/f8cad8d7d4276cd22aee20113fe3214230daf919/src/arminer/export/financial_excel.py#L1126-L1129). |
| P1 | **Thiếu CAPEX vẫn có FCF.** CFO = 30 và CAPEX không có dữ liệu, hàm trả FCF = **30**. | `fillna(0)` biến chưa biết thành bằng không. Cần giữ giá trị thiếu, hoặc cung cấp ước tính được gắn nhãn riêng. [Nguồn](https://github.com/Tumiqa/vn-annual-report-miner/blob/f8cad8d7d4276cd22aee20113fe3214230daf919/src/arminer/export/financial_excel.py#L971-L972). |
| P1 | **Thiếu EBITDA được thay bằng EBIT.** EBIT = 10, doanh thu = 100, không có EBITDA; hàm vẫn trả biên EBITDA = **10%**. | Hai đại lượng bị đánh đồng, ảnh hưởng cả nợ/EBITDA. Cần tính EBITDA từ các thành phần đủ dữ liệu, hoặc để trống; proxy phải có tên và trạng thái riêng. [Nguồn](https://github.com/Tumiqa/vn-annual-report-miner/blob/f8cad8d7d4276cd22aee20113fe3214230daf919/src/arminer/export/financial_excel.py#L959-L960). |
| P2 | **Tin không rõ năm vẫn qua bộ lọc năm.** Chọn 2024–2024, bài có `published_year = null` vẫn được nhận. | Kết quả có thể chứa tin không thuộc kỳ phân tích. Đưa bài không xác định ngày vào nhóm chờ xác minh, không coi là đạt bộ lọc thời gian. [Nguồn](https://github.com/Tumiqa/vn-annual-report-miner/blob/f8cad8d7d4276cd22aee20113fe3214230daf919/src/arminer/data/news_scraper.py#L1363-L1378). |
| P2 | **Có BCTC cục bộ nhưng truy vấn tài chính vẫn cần metadata trên Hugging Face.** Ở cache mới và chế độ offline, truy vấn dừng bằng `DatasetAccessError` tại `vnf.list_items`. | Cần đóng gói cả metadata và kiểm tra khả năng chạy khi mất mạng; trả lỗi SSE có cấu trúc thay vì để ngoại lệ làm đứt tác vụ. Kết quả này không chứng minh truy vấn online cũng thất bại. [Nguồn](https://github.com/Tumiqa/vn-annual-report-miner/blob/f8cad8d7d4276cd22aee20113fe3214230daf919/src/arminer/ui/server.py#L2567-L2569). |
| P1 khi triển khai dùng chung | **API có thể đọc đường dẫn file trên máy chủ, không yêu cầu đăng nhập; CORS chấp nhận Origin ngoài.** Gọi qua TestClient với file TXT do bài audit tạo trả HTTP 200 và đoạn nội dung file. | Đây là khả năng hữu ích cho ứng dụng cục bộ, nhưng cần giới hạn thư mục, xác thực và CORS cụ thể trước khi đưa lên máy chủ dùng chung. Chỉ kiểm tra bằng file thuộc bài audit, không đọc tài liệu cá nhân. [Đọc file](https://github.com/Tumiqa/vn-annual-report-miner/blob/f8cad8d7d4276cd22aee20113fe3214230daf919/src/arminer/ui/server.py#L1525-L1533), [CORS](https://github.com/Tumiqa/vn-annual-report-miner/blob/f8cad8d7d4276cd22aee20113fe3214230daf919/src/arminer/ui/server.py#L193-L199). |
| P1 khi triển khai dùng chung | **Tên tệp xuất dùng chung giữa các tác vụ.** Hai lần lấy đường dẫn `financial_data.csv` trả cùng đường dẫn khi file còn ghi được. | Kết quả có thể bị thay thế giữa các lần chạy hoặc người dùng. Dùng thư mục riêng theo `job_id`, liên kết tải gắn với tác vụ và kiểm tra quyền truy cập. [Nguồn](https://github.com/Tumiqa/vn-annual-report-miner/blob/f8cad8d7d4276cd22aee20113fe3214230daf919/src/arminer/ui/server.py#L172-L184). |
| P1 về quản lý khóa | **Có token Hugging Face fallback nằm trong mã nguồn**, được ghép từ nhiều chuỗi. | Không mang khóa dùng chung này sang sản phẩm mới. Dùng cấu hình bí mật của môi trường triển khai hoặc truy cập không xác thực khi nguồn cho phép. Chỉ xác nhận sự tồn tại trong mã; không thử tính hợp lệ hay quyền của token và không đưa giá trị vào báo cáo. [Nguồn](https://github.com/Tumiqa/vn-annual-report-miner/blob/f8cad8d7d4276cd22aee20113fe3214230daf919/src/arminer/utils/env.py#L17-L18). |

## 4. Phạm vi nhóm cần phát triển theo đề

| Hợp phần sản phẩm | Phần có thể tham khảo | Phần nhóm cần xây |
|---|---|---|
| Giá và giao dịch | Chuẩn tổ chức dữ liệu theo mã | Nguồn giá/khối lượng, lịch giao dịch, đơn vị, ngày cập nhật và xử lý điều chỉnh giá nếu phân tích chuỗi lịch sử. |
| Tổng quan vĩ mô | Tin kinh tế có thể làm bằng chứng phụ | Bộ chỉ tiêu vĩ mô, kỳ dữ liệu và giải thích ảnh hưởng tới ngành/doanh nghiệp. |
| Phân tích ngành | Ánh xạ ICB | Nhóm doanh nghiệp so sánh, chỉ tiêu phù hợp ngành, xu hướng và vị thế doanh nghiệp. |
| Phân tích doanh nghiệp và cơ hội đầu tư | BCTC, tin, đoạn trích và bảng tỷ số | Phân tích tăng trưởng, sinh lời, dòng tiền, đòn bẩy; phương pháp định giá phù hợp; nhận định có giả định, rủi ro và căn cứ. |
| Báo cáo theo nhu cầu | Xuất dữ liệu và tiến độ SSE | Mẫu báo cáo PDF tích hợp, biểu đồ, nguồn trích dẫn, kỳ phân tích, nhu cầu người dùng và ngày chốt dữ liệu. |
| Độ tin cậy | `source_file`, `source_sheet`, context snippets | Kiểm tra chất lượng dữ liệu, thông báo thiếu nguồn, trạng thái lỗi/từng phần và phép đối chiếu với báo cáo gốc. |

Chưa tìm thấy bộ lấy OHLCV, bộ phân tích vĩ mô, luồng định giá/nhận định đầu tư hay bộ tạo PDF phân tích tích hợp trong mã đã kiểm tra. Khai phá từ khóa, phân loại ICB và tải PDF gốc là những thành phần đầu vào hữu ích cho các phần này.

## 5. Thiết kế sản phẩm tối thiểu đề xuất

Một ứng dụng Web cho phép nhập mã cổ phiếu, ngày chốt dữ liệu và nội dung cần phân tích. Tác vụ tạo báo cáo có mã riêng và hiển thị tiến độ thu thập, kiểm tra, tính toán, tổng hợp, xuất PDF.

Tầng dữ liệu lưu bản chụp đầu vào kèm nguồn, thời điểm tải, kỳ báo cáo, đơn vị và trạng thái chất lượng. Tầng tính toán dùng một bộ công thức có kiểm thử cho mọi giao diện. Tầng phân tích kết hợp vĩ mô → ngành → doanh nghiệp → định giá và rủi ro. Tầng báo cáo dùng các kết quả đã kiểm tra để dựng PDF và danh mục nguồn.

LLM là tùy chọn để tổng hợp diễn giải từ bằng chứng. Các con số, tỷ số và kết quả định giá phải được tính và truy vết độc lập. Thiếu dữ liệu phải hiện rõ; không tự điền bằng không hoặc tạo số thay thế không có nhãn.

Ưu tiên triển khai một luồng từ đầu đến cuối trước: nhập mã → dữ liệu có nguồn → phân tích có căn cứ → tải PDF thực. Sau đó mở rộng độ phủ nguồn và hình thức trình bày. Các test nghiệm thu nên bao gồm nhiều mã thuộc các ngành khác nhau, một mã không hỗ trợ, một kỳ thiếu năm trước và một lần nguồn dữ liệu không truy cập được.

## 6. Phạm vi kiểm chứng thực tế

- Đã clone và đọc mã tại commit nêu trên; `git status --short` và `git diff --stat` không có thay đổi tracked sau kiểm tra. Không sửa mã nguồn của repo.
- Đã chạy **32 test được chọn từ 6 tệp**: tài chính/Excel, chống khớp sai, trích đoạn, xác minh BCTN, tin doanh nghiệp và ZIP. **31 đạt, 1 thất bại**: `test_full_702_indicators_guarantee`, do metadata Hugging Face chưa có trong cache khi khóa kết nối ngoài. Đây không phải kết quả toàn bộ test suite.
- Đã chạy 7 phép đối chứng riêng: 4 sai lệch tài chính, bộ lọc năm tin tức, trùng đường dẫn xuất và API đọc file do audit sở hữu. Đầu vào và kết quả nằm trong `repo_audit_evidence.json`.
- Đã xác nhận truy vấn tài chính không hoàn tất trên cache mới ở chế độ offline. Không coi việc import server hoặc HTTP 200 của một API khác là bằng chứng luồng tạo báo cáo đã chạy thành công.
- Chưa kiểm tra crawler với các website tin tức thật, OCR trên báo cáo scan thật, dữ liệu BCTC đối chiếu với tài liệu phát hành của doanh nghiệp, hay vận hành nhiều người dùng qua trình duyệt.
- Môi trường kiểm tra: Python 3.12.14, pandas 3.0.6, NumPy 2.5.3, pyarrow 25.0.1, FastAPI 0.143.0, vnfinancialdata 0.1.2. Môi trường audit được tạo riêng; không cài toàn bộ đường EasyOCR/Torch.
