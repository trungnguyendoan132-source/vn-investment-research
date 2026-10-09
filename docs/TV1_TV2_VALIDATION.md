# Kiểm chứng TV1/TV2 - 09/10/2026

- 175 test offline đạt, Ruff và kiểm tra cú pháp JS đạt. Test provider mock được tách khỏi phép gọi thật.
- TV1: queue SQLite có giới hạn, idempotency, owner upload/job, migration DB, process lock, kill/restart thật, retention và kiểm tra artifact/readiness.
- TV2: cache/hash cùng bytes, mapping đa ngành, quarantine EPS/alias/sign, OHLCV và corporate-action basis, immutable filing release theo ngày công bố và sources từng fact.
- 51 số được đối chiếu trực quan trong 7 envelope nguồn FPT/SSI/VCB, bao gồm SSI bán niên 2026. Các cột so sánh 2024 giữ ngày công bố của báo cáo gốc, không backdate.
- Live SSI: tự lấy nguồn, không upload CSV, đúng gpt-6-luna + jev-1.13-free, chạy đủ 6 phần và tạo PDF/JSON/manifest trong khoảng 44 giây. Báo cáo partial vì World Bank timeout, peer verified chưa đủ, giá chưa rõ basis điều chỉnh.
- PDF thực 5 trang đã render và xem đủ trang; không thiếu glyph, tràn bảng hay cắt số. Đã sửa cột đơn vị và render lại từ bằng chứng lưu, không gọi lại provider.
- Wheel được cài trong venv sạch ngoài checkout, import từ site-packages và chạy Demo offline. Sáu Parquet, bảy seed JSON, font/static/licenses và manifest khớp. Sau cập nhật consumer cuối, cần build lại wheel trước phát hành package.
- GitHub Actions chưa chạy vì credential hiện tại không có quyền workflow; có template và script kiểm tra wheel. Không đồng nhất test cục bộ với CI.

Mã kiểm chứng và kết quả không chứa API key. `.env` cục bộ đã cấu hình cho máy trưởng nhóm và bị Git ignore; các máy khác cần cấu hình gateway của mình hoặc dùng server nhóm. Báo cáo partial được xuất tự động; Jev review không dừng việc tạo/tải PDF.

PR #8 của TV5 còn xung đột sau khi ghép TV1/TV2. Không ghi đè nhánh của thành viên: giữ kịch bản/độ nhạy/cache của TV5, đồng thời giữ helper gateway, publication cutoff, verification gate và nguồn khi giải quyết xung đột.

Bằng chứng máy đọc được ở [TV1_TV2_EVIDENCE.json](validation/TV1_TV2_EVIDENCE.json).
