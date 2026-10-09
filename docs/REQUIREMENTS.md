# Ma trận yêu cầu và nghiệm thu

Đề gốc: “Xây dựng hệ thống phân tích cơ hội đầu tư cổ phiếu”. Link repo trong đề là nguồn tham khảo. Nhóm chịu trách nhiệm về sản phẩm mới và chất lượng dữ liệu/kết quả.

| Yêu cầu | Sườn đã có | Chủ trì | Điều kiện nghiệm thu sản phẩm |
|---|---|---|---|
| Giá và dữ liệu giao dịch | CSV OHLCV, kiểm tra đơn vị/ngày, chỉ báo, adapter live tùy chọn | TV2 | Nguồn thật hoạt động; đối chiếu một tập phiên; đơn vị rõ; xử lý sự kiện vốn và tình trạng giá điều chỉnh. |
| BCTC và tỷ số doanh nghiệp | 6 Parquet, exact mapping, bộ công thức có test | TV2 + TV5 | Số liệu chính khớp BCTC gốc ở nhiều ngành; ngày công bố, loại BCTC và kỳ rõ; các tỷ số đúng định nghĩa. |
| Tin doanh nghiệp cập nhật | Scraper kế thừa, CSV, ngày chặt chẽ, trích đoạn | TV4 | Đúng doanh nghiệp/ngày, nguồn truy cập được, loại trùng; tin sai/không rõ ngày bị loại hoặc đánh dấu. |
| Báo cáo công ty chứng khoán | Đọc PDF text, trích đoạn theo trang | TV4 | Nguồn được nhóm chọn có tài liệu thật; ghi tên CTCK, ngày, trang; OCR kiểm tra mẫu khi cần. |
| Tổng quan vĩ mô | World Bank năm + CSV | TV3 | Có tăng trưởng, lạm phát, lãi suất/tỷ giá hoặc chỉ tiêu phù hợp khác; phân tích tác động và giới hạn theo kỳ. |
| Phân tích ngành | Phân ngành ICB, peer same-year, trung vị | TV3 + TV5 | Có động lực ngành, đối thủ, vị thế, đặc thù ngành và lý do chọn nhóm so sánh. |
| Cơ hội đầu tư | Tài chính, P/E/P/B, giả định, điều kiện cơ hội/rủi ro | TV5 | Phương pháp phù hợp, kịch bản và độ nhạy, catalyst/rủi ro, tầm nhìn, căn cứ cho nhận định; không suy diễn từ tỷ số đơn lẻ. |
| Cổ phiếu bất kỳ | Chuẩn ticker chung, danh mục và thông báo thiếu dữ liệu | TV1 + TV2 | Không hardcode một mã; nhiều mã/đa ngành chạy; mã thiếu nguồn được xử lý rõ; định nghĩa phạm vi thị trường hỗ trợ. |
| PDF theo nhu cầu | Tùy chọn mục, tiếng Việt, biểu đồ, nguồn, JSON/manifest | TV6 | Nội dung bám lựa chọn; PDF đọc được, không mất chữ/tràn bảng, có ngày chốt và nguồn chứng minh kết luận. |
| Chính xác dữ liệu | Check schema, đơn vị, ngày, null và source IDs | TV2 + TV4 | Báo cáo đối chiếu nguồn thật; lỗi nguồn không thành số 0; cập nhật/điều chỉnh được theo dõi. |
| Chính xác phân tích | Công thức riêng, test hồi quy, AI bị ràng buộc | TV5 | Kiểm tra số học và định nghĩa; đánh giá AI trên bằng chứng thật; người review xác nhận lập luận được nguồn hỗ trợ. |
| LLM + Jev API | LLM Chat Completions, model auto; Jev native `/v1/systemone` Choice/Noul, điều kiện review, test mock | TV5 + TV1 | Hai bộ URL/key riêng hoạt động bằng tài khoản nhóm; lưu provider/model, usage/thời gian và claim → nguồn; thử đa mã/đa ngành; Jev không bỏ qua demo/thiếu dữ liệu. Chưa có bằng chứng xác thực live trong sườn. |
| Vận hành và sáng tạo | Web, tùy chọn nhu cầu, job token, SQLite, PDF có chứng cứ | TV1 + TV6 | Demo người dùng từ đầu đến cuối, nhiều tác vụ không ghi đè, khởi động lại rõ trạng thái, tài liệu vận hành và trải nghiệm hoàn chỉnh. |

## Bộ nghiệm thu bắt buộc

1. Chọn tối thiểu một doanh nghiệp công nghệ, một ngân hàng, một doanh nghiệp sản xuất, một mã nhỏ và một mã không có dữ liệu trong snapshot.
2. Với mỗi mã có dữ liệu thật, đối chiếu doanh thu, LNST, tài sản, vốn chủ, dòng tiền và các tỷ số liên quan với nguồn gốc; lưu URL/trang/kỳ.
3. Kiểm tra thiếu năm trước, CAPEX, EPS, giá, tin, dữ liệu ngành và lỗi nhà cung cấp. Đầu ra phải phân biệt thiếu dữ liệu với bằng không.
4. Kiểm tra ngày chốt, dữ liệu công bố sau ngày chốt và corporate actions. Không coi snapshot hiện tại là point-in-time lịch sử.
5. Chạy luồng Web chọn nhu cầu → xem kết quả → tải PDF/JSON; kiểm tra PDF thật và manifest.
6. Chạy LLM/Jev tắt, riêng từng dịch vụ và cùng bật; thiếu khóa, phản hồi lỗi, JSON sai, nguồn giả, model discovery và model thật. Dùng `LLM_BASE_URL`, `LLM_API_KEY`, `JEV_BASE_URL`, `JEV_API_KEY`; mặc định `LLM_MODEL=auto` và Jev `/v1/systemone`. Ghi rõ kết quả nào là mock, kết quả nào là live; không suy tính hợp lệ của key từ trạng thái đã cấu hình.
7. Mỗi yêu cầu được đánh dấu đạt chỉ khi có hiện vật/bằng chứng tương ứng. Không dùng HTTP 200, test mock hay lời AI tự báo thành công làm nghiệm thu toàn hệ thống.

## Chốt bài nộp

TV1 tổng hợp ma trận bằng chứng; TV2–TV5 ký phần dữ liệu/phân tích mình sở hữu; TV6 kiểm tra PDF và demo. Khung mã bao phủ cấu trúc của toàn bộ đề; chất lượng sản phẩm cuối cần hoàn tất các việc được liệt kê, không có cam kết độ chính xác tuyệt đối chỉ từ mã nguồn.
