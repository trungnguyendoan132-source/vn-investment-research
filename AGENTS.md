# Hướng dẫn cho người và trợ lý làm việc trong repo

- Đọc README, docs/REQUIREMENTS.md, docs/contracts/README.md và tài liệu vai trò trước khi sửa.
- Giữ phạm vi sở hữu 6 thành viên. Không tự đổi contract chung mà chưa ghi rõ ảnh hưởng trong PR.
- Mọi số tài chính phải có đơn vị, kỳ, nguồn và cách xử lý thiếu dữ liệu; không dùng LLM làm máy tính.
- Không thay null bằng zero, không dùng EBIT thay EBITDA, không tính YoY qua năm bị khuyết.
- Không đưa token/key upstream vào repo; giữ .env và dữ liệu người dùng ngoài Git.
- Dữ liệu demo phải được gắn nhãn ở Web, JSON và mọi trang PDF.
- API AI cần nguồn dẫn hợp lệ; test mock phải ghi là mock; không tuyên bố chất lượng live khi chưa kiểm tra.
- Chạy ruff và test liên quan; PDF thay đổi phải render và xem ảnh thật.
- Không tuyên bố đáp ứng toàn bộ đề khi ma trận nghiệm thu còn thiếu bằng chứng.
