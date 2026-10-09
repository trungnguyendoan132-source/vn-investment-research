# Audit và kế hoạch TV1 + TV2

Baseline: `a4a64586282a877af9980eef2f134dcc05596fc4`, audit ngày 09/10/2026. Cả hai nhánh bắt đầu từ cùng commit; baseline 36 test đạt nhưng chưa bao phủ các lỗi dưới đây.

## Kết quả ưu tiên

| Phạm vi | Sai lệch đã tái hiện | Hướng sửa và bằng chứng nghiệm thu |
|---|---|---|
| TV1 | Instance B đổi job A đang chạy sang interrupted; worker A sau đó vẫn completed | Khóa hệ điều hành theo data directory, claim có điều kiện, state transitions và test kill/restart tiến trình thật |
| TV1 | Hàng thread queue không giới hạn; lỗi submit để lại job queued không có worker | Queue SQLite bền vững, tiếp nhận có giới hạn, idempotency, dispatcher đọc DB, không tự replay lời gọi AI dở dang |
| TV1 | Upload không có owner; multipart giới hạn sau khi đã spool; CSV sai vẫn được nhận | Registry owner/hash/expiry, chặn body trước parse, validate cấu trúc CSV, giữ input của job đang chạy |
| TV1 | Mất artifact trả 500 nhưng health ok; invalid header/schema không bị từ chối đúng | Error codes/request ID, artifact checksums/schema, readiness khác liveness; reject ticker không phải chuỗi và nguồn không hợp lệ |
| TV1 | HTTPS guard chặn gateway loopback; auto model không giữ model yêu cầu | Cho HTTP chỉ loopback được kiểm tra; không theo redirect; ghim gpt-6-luna và jev-1.13-free trong cấu hình riêng, key không vào Git |
| TV2 | Cache trả giá trị cũ 100 kèm hash file mới 999 | Parse/cache theo cùng bytes và release bất biến; hash nguồn phải khớp dữ liệu thực được đọc |
| TV2 | EPS SSI bị gán tổng lợi nhuận hàng nghìn tỷ, vẫn tạo giá kịch bản; thiếu code bank/broker/insurance | Quarantine theo mâu thuẫn/đơn vị, mapping theo template, đối chiếu tài liệu phát hành gốc từng fact |
| TV2 | Alias/sign chưa giải đúng basis; không có publication/basis/period/fact lineage | Giữ raw/canonical/transform, metadata theo fact và bản filing, cắt ngày công bố, không trộn riêng lẻ/hợp nhất hoặc năm/quý |
| TV2 | Volume 10,9 bị cắt thành 10; URL https:// hợp lệ; giá cũ/synthetic gắn ok | Validation volume/URL/date/overflow, freshness, synthetic flag và raw/adjusted basis rõ; chặn lợi suất khi basis unknown |

## Trình tự thực hiện

1. TV1 chốt contract nguồn và config; version API/report/DB riêng. Trường mới có default unknown để giữ tương thích, không tự nâng metadata cũ thành verified.
2. TV1 thực hiện queue/quyền/ready; TV2 chuẩn dữ liệu, cache và importer cùng lúc. Giữ producer signatures và section keys cho TV3–TV6.
3. TV2 đưa dữ liệu chính thức đã kiểm chứng vào filing release mới; không sửa hàng loạt raw snapshot theo suy đoán. Cột so sánh/restated dùng đúng kỳ và cùng ngày công bố tài liệu gốc.
4. Pipeline truyền as_of/dataset_dir/filing_dir thống nhất. Ngoài Demo, fact chưa verified nằm trong bằng chứng và không cấp cho tỷ số/định giá. Giá unknown/adjusted không dùng làm giá raw cho P/E.
5. Nghiệm thu contract/queue bằng test lỗi và tiến trình thật, dữ liệu bằng URL/hash/trang/kỳ/đơn vị, báo cáo bằng PDF/JSON/manifest thực. LLM/Jev phải test riêng mock và live với model người dùng yêu cầu.
6. Build wheel, cài vào môi trường sạch ngoài source. CI template Windows/Linux × Python 3.11/3.12; kích hoạt GitHub Actions cần credential có quyền workflow, không dùng key provider trong PR tests.

## Điều kiện đóng TV1/TV2

Không ghi hoàn tất dựa trên HTTP 200 hoặc test mock. Phần dữ liệu đã verified chỉ bao gồm facts có bằng chứng cụ thể; độ phủ các mã chưa kiểm tra hiện rõ. Không cam kết toàn bộ dữ liệu thị trường đúng tuyệt đối từ vài tài liệu mẫu. Mã phải từ chối/đánh dấu số chưa kiểm chứng, và báo cáo chất lượng phải cho thấy số nào đang được sử dụng.

TV3, TV4, TV5 và TV6 vẫn sở hữu phân tích chuyên sâu/ngành, nguồn tin/OCR, mô hình định giá/lập luận và UI/PDF. Các chỉnh sửa ở consumer trong hai nhánh này chỉ phục vụ contract/config và quality gating, không thay phạm vi của bốn người còn lại.
