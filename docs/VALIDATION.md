# Xác minh cục bộ - 2026-10-09

## Kết quả đã chạy

- Bộ test cục bộ toàn repo: **36 passed**; ruff và các test hợp đồng do nhóm tích hợp chạy. Chưa có GitHub Actions run; workflow được bàn giao dưới dạng mẫu `docs/ci/github-actions.yml`.
- CLI thật: `python -m vnresearch.cli report --ticker FPT --mode demo --start-year 2022 --end-year 2025 --target-pe 20 --output <directory>` đã hoàn tất, tạo PDF/JSON/manifest. Không bật `--ai` hoặc `--jev`.
- Demo chính thức trong `examples/demo-FPT/`: PDF **5 trang**; đã render đủ 5 trang bằng Poppler `pdftoppm` và xem ảnh. Nhãn **MINH HỌA** hiện trên cả 5 trang. Chữ tiếng Việt đọc được; kiểm tra text không gặp ký tự thay thế U+FFFD hoặc ô vuông U+25A0. Các số tài chính dài nằm trong cột giá trị, không bị ngắt dòng/tràn cột; biểu đồ có kỳ và đơn vị.
- Mở lại bản đã chép: SHA-256 và kích thước PDF/JSON khớp `manifest.json`. JSON/manifest dùng LF để hash ổn định sau Git checkout; PDF không thay đổi.
- `python -m build --wheel --no-isolation` thành công. Wheel có đúng **6 tệp BCTC Parquet**, byte hash trùng các tệp nguồn, font DejaVuSans, ba tệp giao diện Web, `snapshot_manifest.json`, danh mục/từ điển, giấy phép MIT/upstream/DejaVu và manifest kế thừa. CSV mẫu được phân phối trong repo `examples/`, không nằm trong wheel.

## Giới hạn bằng chứng

- `demo` dùng BCTC snapshot kế thừa; giá, vĩ mô và tin **giả lập có nhãn**. `report.status=complete` xác nhận đủ luồng demo, không xác nhận chất lượng phân tích đầu tư thực.
- LLM Chat Completions và Jev TypeSafe native có kiểm thử hợp đồng **mock**, bao gồm chọn model tự động và luồng kết hợp. Chưa gọi model LLM/Jev thật bằng khóa nhóm; chưa nghiệm thu chất lượng lập luận live.
- Chưa đối chiếu toàn bộ BCTC snapshot với báo cáo phát hành gốc, ngày công bố và corporate actions; không dùng snapshot làm dữ liệu point-in-time lịch sử.
- Chưa nghiệm thu nguồn giá/tin/vĩ mô live, OCR, nhiều người dùng, khôi phục tác vụ sau dừng tiến trình hoặc toàn bộ ma trận `docs/REQUIREMENTS.md`.

PDF SHA-256: `cdc5899c4c82ebe90bd1d85df9dbd7fa8d5503592e7759f25b4471ae49c86374`.
JSON SHA-256: `9ecfbb71c76f7efe117759b16a6501a03f58e265fdaa901f84e50df94d25d3c5`.
Wheel SHA-256: `564886af0bca01105df07be6cbfbcc5c99424ede95512de403c590f405981d7d`.
