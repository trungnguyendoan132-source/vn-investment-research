# Luồng tự động và chất lượng đầu ra

Mặc định AnalysisRequest và CLI là live. Người dùng nhập mã; hệ thống tự chuẩn bị filing có nguồn, lấy OHLCV, vĩ mô/tin theo nội dung yêu cầu, tính từ số đủ điều kiện, gọi LLM/Jev và công bố PDF/JSON/manifest. Demo mặc định tắt provider; có thể tắt từng provider bằng flag/UI.

Auto có nghĩa pipeline không dừng để yêu cầu upload hoặc review thủ công khi nguồn lỗi. `review_required` của Jev là metadata đầu ra, không phải popup chặn việc tạo PDF. Auto không có nghĩa hệ thống tự xác nhận số chưa có bằng chứng thành đúng; báo cáo thiếu dữ liệu vẫn được xuất dưới trạng thái partial.

## Cấu hình một lần

Copy `.env.example` thành `.env`. Dùng bốn URL/key và model phù hợp tài khoản. Mẫu gateway localhost nhóm dùng ở `examples/local-gateways.env` không chứa khóa. Mỗi máy cần gateway thực sự chạy ở các cổng đó; localhost của thành viên khác không trỏ về máy trưởng nhóm. Triển khai một server nhóm thì key/gateway cấu hình trên server, trình duyệt chỉ dùng key truy cập ứng dụng.

## Nguồn tự lấy

- KBS daily OHLCV: một request có giới hạn, archive raw response/hash và không đổi nguồn hay tài khoản khi bị chặn. Cơ sở điều chỉnh giá chưa xác minh được ghi unknown; không tự coi chuỗi đó là raw cho P/E.
- Filing gốc đã đối chiếu: chọn theo mã/kỳ/ngày công bố; reuse cache đúng SHA-256, hoặc tải từ URL issuer HTTPS có giới hạn. Chỉ nguồn gốc khớp hash mới được cài thành release. 403/hash đổi/ngoài phạm vi có quality issue.
- World Bank và tin: các adapter sẵn có theo yêu cầu; TV3/TV4 tiếp tục chịu trách nhiệm mở rộng nguồn/định nghĩa và chất lượng nghiệp vụ.

## Bảo toàn số đúng

Ngoài Demo, số legacy chưa verified được giữ trong `fact_metadata.observed_value`, còn `facts` dùng tính toán là null. Không dùng số đó cho ratio/P/E/giá kịch bản. Mọi số tính trung bình/YoY cần hai kỳ cùng basis, đơn vị và loại kỳ. Kỳ SSI bán niên 2026 được trình bày riêng; không nhân đôi hoặc trộn với số năm 2025.

Tự động tải các original seed không mở rộng phạm vi đã kiểm chứng ra mọi mã. Thêm issuer/kỳ mới cần evidence metadata và adapter/validator phù hợp. Khi chưa có nguồn đủ điều kiện, báo cáo chỉ rõ phần chưa có; không tự bịa số để tạo báo cáo đầy.

## Vận hành

Queue hữu hạn, principal riêng, input immutable và idempotency giữ tác vụ rõ ràng. Status completed nói bộ artifact đã công bố, độc lập report.status. Job interrupted được giữ bằng chứng; chạy lại cần một yêu cầu mới rõ ràng, tránh lặp chi phí AI không rõ kết quả.
