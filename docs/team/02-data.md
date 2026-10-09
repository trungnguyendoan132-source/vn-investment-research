# TV2 - Giá, giao dịch và báo cáo tài chính

Nhánh: `member02-market-financial-data`. Sở hữu `data/`, `assets/bctc/`, `assets/companies.csv`. Đầu ra cho TV3/TV5; provenance cho TV6.

## Kế thừa / có sẵn

Sáu Parquet BCTC, danh mục doanh nghiệp/phân ngành; adapter mới exact item-code mapping, kiểm tra giá trị xung đột. CSV OHLCV có chuẩn đơn vị; live gọi KBS trực tiếp theo contract ghim từ mã nguồn vnstock. Package `vnstock` không phải dependency runtime.

## Công việc cần hoàn thiện

1. Xác nhận nguồn KBS, điều kiện truy cập, đơn vị và độ ổn định. Đối chiếu adapter trực tiếp với contract nguồn đã ghim trước khi đánh dấu live đạt.
2. Cập nhật BCTC vượt snapshot 2025, lưu nguồn báo cáo gốc, kỳ, ngày công bố, hợp nhất/riêng lẻ và tình trạng điều chỉnh.
3. Đối chiếu doanh thu, LNST, tài sản, nợ, vốn chủ, CFO, CAPEX, EPS và số cổ phiếu với tài liệu gốc ở nhiều ngành.
4. Xử lý corporate actions/giá điều chỉnh; kiểm tra phiên giao dịch thiếu, trùng, ngoại lệ và mã chuyển sàn.
5. Tạo báo cáo chất lượng dữ liệu và danh sách mã/kỳ có/thiếu dữ liệu. Không tự kéo số dư hoặc số EPS không cùng kỳ vào định giá.

## Bàn giao / điều kiện đạt

Provider có test và bộ dữ liệu kiểm chứng; nguồn thật cho tối thiểu các mã nghiệm thu trong REQUIREMENTS. Thiếu dữ liệu phải là null có lý do. Gửi TV5 ví dụ đầu vào có đơn vị và ngày công bố.

Chạy: `pytest tests/test_market.py tests/test_financial.py -q`.
