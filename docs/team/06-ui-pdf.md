# TV6 - Web, PDF và kiểm thử sản phẩm

Nhánh: `member06-ui-pdf-qa`. Sở hữu `static/`, `reports/`, demo và hồ sơ QA. TV6 trình bày đúng dữ liệu có trong Report từ TV5; không tính lại tỷ số trong trình duyệt.

## Đã tích hợp

- Web tiếng Việt: chọn ticker, chế độ/ngày chốt, mục báo cáo và CSV tùy chọn; theo dõi trạng thái job tách biệt chất lượng dữ liệu.
- Dashboard có bảng lọc, biểu đồ tài chính/ngành, source modal và nút tải PDF/JSON/manifest.
- Cấu hình LLM và Jev bằng Base URL, model và API key ở màn hình; khóa chỉ được gửi đến backend local và giữ trong RAM theo phiên hết hạn, không ghi ra báo cáo hay lưu trong trình duyệt.
- PDF gắn nhãn minh họa, hiển thị vấn đề dữ liệu và nguồn; biểu đồ đặt khoản lỗ dưới mốc 0.
- Lệnh khởi chạy một lần bấm cho Windows: `start_windows.bat`; xem hướng dẫn người mới trong README.

## Kiểm tra có thể lặp lại

```powershell
$env:PYTHONUTF8 = "1"
python -m pytest tests/test_jobs_and_pdf.py tests/test_tv6_demo_artifacts.py tests/test_tv6_ui_contract.py -q
python demo/create_demo_pdf.py
```

Lệnh demo tạo `var/demo-FPT/report.pdf`, `report.json`, `manifest.json` và ảnh ở `var/demo-FPT/images/`. So sánh hash với manifest và xem toàn bộ ảnh sau khi thay layout.

## Ranh giới nghiệm thu

Fixture/sample PDF là demo, không chứng minh dữ liệu live hay độ đúng đầu tư. Mẫu chứa snapshot BCTC legacy `unverified` và dữ liệu giá/vĩ mô/tin `synthetic`; xem `docs/evidence/tv6-demo/`. UI test tự động kiểm tra contract/asset, không thay cho kiểm thử trình duyệt thủ công. Trước nộp, chạy một luồng UI thật từ chọn ticker đến tải đủ ba file; kiểm tra các màn hình lỗi API, thiếu nguồn, nhiều job và cấu hình provider.
