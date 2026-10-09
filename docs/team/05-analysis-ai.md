# TV5 - Phân tích, định giá và API AI

Nhánh: `member05-analysis-ai`. Sở hữu `analysis/`. Nhận dữ liệu TV2, vĩ mô/ngành TV3, bằng chứng TV4; trả Report cho TV6.

## Có sẵn

Bộ tính tài chính có test hồi quy, so sánh ngành, P/E/P/B theo dữ liệu có sẵn, bội số kịch bản người dùng nhập, điều kiện cơ hội/rủi ro và pipeline. `analysis/ai.py` tích hợp LLM Chat Completions, kiểm tra JSON/source IDs và chữ số trong diễn giải. `analysis/jev.py` tích hợp Jev TypeSafe native `/v1/systemone`, kiểm tra Choice/Noul và giữ điều kiện review cho dữ liệu demo/thiếu/lỗi chất lượng.

Đây là mã sườn và test mock; chưa có bằng chứng xác thực bằng key live của nhóm, chưa nghiệm thu chất lượng nhận định đầu tư.

## Công việc cần hoàn thiện

1. Kiểm chứng công thức và mapping cùng TV2; chốt định nghĩa theo ngành và loại BCTC. Không phục hồi bộ 116 tỷ số cũ nguyên trạng khi chưa kiểm chứng.
2. Bổ sung phương pháp định giá phù hợp: bội số ngành và DCF/FCFE hoặc mô hình phù hợp ngân hàng/chứng khoán; giả định có căn cứ và không lẫn EPS năm với TTM.
3. Xây kịch bản tăng/cơ sở/giảm, độ nhạy, catalyst, rủi ro và tầm nhìn; nhận định có điều kiện, không cam kết lợi nhuận.
4. Phối hợp TV1 cấu hình `LLM_BASE_URL`, `LLM_API_KEY`, `JEV_BASE_URL`, `JEV_API_KEY`; mặc định `LLM_MODEL=auto`, `JEV_MODEL=jev-latest`, `JEV_MIN_CONFIDENCE=0.85`. LLM khám phá model qua `/models`; đặt model cụ thể nếu gateway không hỗ trợ. Jev dùng hợp đồng TypeSafe riêng, không gửi qua Chat Completions. Đánh giá trên dữ liệu thật đa ngành; bổ sung giới hạn chi phí, cache theo bằng chứng và kiểm chứng từng lập luận với nguồn.
5. Đánh giá prompt injection, nguồn dẫn không hỗ trợ nội dung, dữ liệu thiếu và mâu thuẫn; AI không tự tính lại số hoặc tạo thông tin bù thiếu.

## Bàn giao / điều kiện đạt

Report có đủ mạch vĩ mô → ngành → doanh nghiệp → cơ hội/định giá/rủi ro. Test số học đạt và có báo cáo đánh giá LLM/Jev thật; lưu provider/model, thời gian, usage khi provider trả, claim → nguồn và quyết định trước/sau điều kiện review. Source ID tồn tại không đủ để kết luận lập luận đúng; confidence của Jev không phải xác suất sinh lời.

Chạy: `pytest tests/test_financial.py tests/test_ai.py tests/test_jev.py -q`. Đọc [API AI](../AI_INTEGRATION.md), [Jev](../JEV_INTEGRATION.md) và README; `.env` không được commit. TV2 kiểm chứng dữ liệu/công thức, TV3 cung cấp vĩ mô/ngành, TV4 đối chiếu nguồn, TV1 giữ contract/khóa, TV6 hiển thị và kiểm tra PDF; TV5 chịu trách nhiệm tổng hợp phân tích và chất lượng AI.
