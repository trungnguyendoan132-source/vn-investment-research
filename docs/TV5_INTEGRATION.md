# TV5 - định giá kịch bản và tổng hợp AI

PR #8 bổ sung kịch bản Bull/Base/Bear, bảng độ nhạy, tham chiếu P/E ngành khi được bên gọi cung cấp, ghi nhận yếu tố tăng trưởng/dòng tiền/rủi ro và cache tổng hợp AI theo bằng chứng.

## Định giá

Giữ các tham số `is_bank`, `sector_pe` và `require_verified=True`. Ngoài Demo, P/E/P/B, các kịch bản và tham chiếu ngành chỉ được tính khi fact liên quan đã verified, không quarantined, giá hữu hạn/dương, ngày giá tại hoặc trước ngày chốt và không cũ quá 7 ngày, cùng cơ sở raw tương thích. P/B có thể dùng khi EPS âm nếu vốn thuộc cổ đông mẹ và số cổ phiếu có nguồn đủ điều kiện.

Bull/Bear +15%/-15% và sensitivity +10%/-10% là thay đổi giả định trên bội số; không phải dự báo giá hoặc cam kết lợi nhuận. `sector_pe` là đầu vào của bên gọi, không phải trung vị ngành được bộ tính tự thu thập/xác minh. Giá trị không hữu hạn hoặc không dương bị từ chối; phép tính tràn số được bỏ và kết quả partial.

## AI

Giữ cấu hình gateway của TV1, HTTP chỉ loopback, HTTPS xác minh TLS và không theo redirect. Giữ kiểm tra source IDs và loại nhận xét tự thêm chữ số. Chỉ các nhận xét hợp lệ được đưa vào báo cáo/cache; phản hồi lỗi không cache.

Cache nằm trong process, tối đa 128 mục, TTL 300 giây. Key gồm request, bằng chứng/phiên bản nguồn, endpoint, model, phiên bản prompt và scope credential đã hash. Không lưu key thô. Kết quả trả là bản sao độc lập; `cache_hit` và thời gian phản hồi phân biệt hit với lời gọi mới. Cache không bảo đảm gộp những lời gọi đang chạy đồng thời.

## Kiểm chứng

- Toàn suite: **212 passed**, Ruff đạt, không còn conflict marker hoặc lỗi whitespace.
- Test giữ kịch bản/độ nhạy/ghi chú ngân hàng; chặn unverified/quarantined, giá unknown/adjusted, giá cũ/tương lai, số không hữu hạn và sector multiple không hợp lệ.
- Test cache hit, TTL, thay nguồn/request/model/endpoint/credential, lỗi không cache và bản sao kết quả không làm biến đổi cache.
- CLI Demo thực tạo PDF/JSON/manifest; hash khớp, PDF 5 trang hiển thị 12 dòng định giá gồm các kịch bản/độ nhạy. Đã render và kiểm tra phần thay đổi, không thấy tràn bảng hoặc thiếu glyph.
- Test tác vụ dùng giới hạn thời gian thực 20 giây thay số lần poll cố định, vẫn kiểm tra đúng trạng thái/hiện vật. Lượt đầu chạy đồng thời suite và CLI có một timeout; ca riêng đạt và toàn suite tuần tự sau thay đổi đạt.
- Không gọi API AI thật trong lượt sửa xung đột này; các test provider là mock. Bằng chứng live của TV1/TV2 được giữ nguyên, không dùng để tự xác nhận chất lượng mới của TV5.

Consumer giữ automatic defaults, ngày công bố/cutoff, nguồn từng fact, lớp loại số chưa xác minh và đầu ra Jev. CLI UTF-8 tương thích Windows, đồng thời kiểm tra khả năng `reconfigure` khi stdout/stderr được test thay thế.
