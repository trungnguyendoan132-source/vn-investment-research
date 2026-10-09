# TV5 - Phân tích, định giá và API AI

Nhánh: `member05-analysis-ai`. Sở hữu `analysis/`. Nhận dữ liệu TV2, vĩ mô/ngành TV3, bằng chứng TV4; trả Report cho TV6.

## Có sẵn

Bộ tính tài chính có test hồi quy, so sánh ngành, P/E/P/B theo dữ liệu có sẵn, bội số kịch bản người dùng nhập, điều kiện cơ hội/rủi ro, pipeline và adapter Chat Completions có kiểm tra JSON/source IDs.

## Công việc cần hoàn thiện

1. Kiểm chứng công thức và mapping cùng TV2; chốt định nghĩa theo ngành và loại BCTC. Không phục hồi bộ 116 tỷ số cũ nguyên trạng khi chưa kiểm chứng.
2. Bổ sung phương pháp định giá phù hợp: bội số ngành và DCF/FCFE hoặc mô hình phù hợp ngân hàng/chứng khoán; giả định có căn cứ và không lẫn EPS năm với TTM.
3. Xây kịch bản tăng/cơ sở/giảm, độ nhạy, catalyst, rủi ro và tầm nhìn; nhận định có điều kiện, không cam kết lợi nhuận.
4. Cấu hình API AI/model của nhóm; đánh giá trên dữ liệu thật đa ngành. Giới hạn chi phí, lỗi provider, timeout, cache theo bằng chứng và kiểm chứng từng lập luận với nguồn.
5. Đánh giá prompt injection, nguồn dẫn không hỗ trợ nội dung, dữ liệu thiếu và mâu thuẫn; AI không tự tính lại số hoặc tạo thông tin bù thiếu.

## Bàn giao / điều kiện đạt

Report có đủ mạch vĩ mô → ngành → doanh nghiệp → cơ hội/định giá/rủi ro. Test số học đạt và có báo cáo đánh giá AI thật; source ID tồn tại không đủ để kết luận lập luận đúng.

Chạy: `pytest tests/test_financial.py tests/test_ai.py -q`. Cấu hình AI đọc trong README; `.env` không được commit.
