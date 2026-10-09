# LLM + Jev và ranh giới bằng chứng

TV5 sở hữu `analysis/ai.py`, `analysis/jev.py` và chất lượng phân tích; TV1 quản lý cấu hình/khóa/contract; TV2 cung cấp số liệu đã đối chiếu; TV3 cung cấp vĩ mô/ngành; TV4 cung cấp bằng chứng; TV6 trình bày kết quả và kiểm tra Web/PDF.

## Cấu hình hai dịch vụ

CLI/server có thể đọc `.env` trong thư mục chạy hoặc biến môi trường. Với web local, người dùng có thể nhập riêng URL/model/key cho từng dịch vụ trong giao diện. GUI tạo provider session qua `POST /api/provider-sessions`; sau khi gửi, key được giữ trong RAM server, session id chỉ trong biến RAM tab, job snapshot cũng chỉ ở RAM server. Không ghi key vào SQLite, report, manifest hoặc file cấu hình. Session hết hạn sau 8 giờ hoặc khi server dừng. Route chỉ nhận client loopback; nếu Origin được gửi thì phải cùng-origin.

```dotenv
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=
JEV_BASE_URL=https://api.typesafe.ai
JEV_API_KEY=
LLM_MODEL=auto
JEV_MODEL=jev-latest
JEV_MIN_CONFIDENCE=0.85
```

- **LLM:** base HTTPS phục vụ `/models` và `/chat/completions`, thường kết thúc bằng `/v1`. `LLM_MODEL=auto` chọn model đầu tiên từ `/models` sau khi loại một số loại model không phải chat. Đây không phải kiểm tra tương thích; đặt model cụ thể nếu gateway không hỗ trợ khám phá hoặc model được chọn không hỗ trợ JSON. Các tên `VNRESEARCH_AI_BASE_URL`, `VNRESEARCH_AI_API_KEY`, `VNRESEARCH_AI_MODEL` được giữ để tương thích cũ; ưu tiên tên `LLM_*` khi có cả hai.
- **Jev / TypeSafe AI:** dùng native `/v1/systemone`, không dùng Chat Completions. Base là host, host `/v1` hoặc full endpoint đều được client chuẩn hóa. Model mặc định `jev-latest`; `TYPESAFE_API_KEY` là tên key tương thích cũ khi chưa đặt `JEV_API_KEY`. Gateway khác phải phục vụ cùng hợp đồng TypeSafe.

### Nhập cấu hình qua giao diện local

Nhóm có thể nhập URL/model/key tại hai ô riêng trong UI. Mặc định giao diện dùng:

| Provider | Base URL | Model |
|---|---|---|
| LLM | `http://localhost:61392/v1` | `gpt-6-luna` |
| Jev TypeSafe | `http://127.0.0.1:8795/v1/systemone` | `jev-1.13-free` |

Bấm **Lưu kết nối vào phiên** để gửi JSON `{"providers":{"llm":{"base_url":"...","api_key":"...","model":"..."},"jev":{"base_url":"...","api_key":"...","model":"..."}}}` tới `POST /api/provider-sessions`. Chỉ gửi provider có key; các provider bị bỏ qua dùng cấu hình backend nếu có. Response chỉ trả session id, model, trạng thái `configured_unverified` và TTL, không trả key. UI giữ session id trong biến RAM tab, không dùng localStorage/sessionStorage; refresh trang thì cần nhập lại.

Server giữ key trong `ProviderSessionStore` process-local tối đa 8 giờ/256 session. Job lấy snapshot cấu hình trong RAM (tối đa 512, TTL 8 giờ); snapshot bị xóa sau thành công và được giữ tạm cho retry lỗi. Không ghi key/session cấu hình vào SQLite, report hay manifest. Route provider session và request có `X-Provider-Session` chỉ chấp nhận client loopback; nếu Origin được gửi thì phải cùng-origin. Nếu server bật `VNRESEARCH_API_KEY`, GUI còn phải gửi application key đó. Nhập key LLM/Jev trong trình duyệt gửi key qua HTTP loopback tới process server; provider remote bắt buộc dùng HTTPS. Chỉ dùng endpoint mà nhóm tin cậy.

Web chọn provider theo `/api/capabilities` và cấu hình trong phiên; sau khi lưu, checkbox của dịch vụ đã cấu hình được bật ở `snapshot`/`live` và có thể tắt riêng. API/CLI `AnalysisRequest` mặc định `use_ai=true`, `use_jev=true` ở chế độ không phải demo; CLI hỗ trợ `--no-ai` và `--no-jev`. Demo tự tắt provider nếu không bật rõ ràng; giao diện demo khóa checkbox. Có key/configuration status chưa chứng minh endpoint hoạt động.

```powershell
vnresearch report --ticker FPT --mode snapshot --ai --jev --output var/FPT
```

## Pipeline và dữ liệu gửi

Pipeline tính số liệu trước → LLM tổng hợp nếu bật → Jev đánh giá hành động nghiên cứu nếu bật → ứng dụng áp dụng điều kiện review → xuất Web/PDF/JSON. Hai dịch vụ có thể bật độc lập.

LLM nhận mã/nhóm ngành, hai kỳ tài chính cuối, tối đa tám dòng mỗi bảng tóm tắt, danh sách source IDs và vấn đề chất lượng. Không tự tải tài liệu nguồn từ source ID. Lời gọi gửi `model`, `messages`, `response_format` JSON object và `max_completion_tokens=1200`. Timeout kết nối/đọc là 8/45 giây; khám phá model là 8/10 giây.

Jev TypeSafe SystemOne nhận payload native `{model,state,questions}` tại `/v1/systemone`, gồm trạng thái báo cáo, tóm tắt/source IDs, kỳ tài chính cuối, vấn đề chất lượng, cơ hội/rủi ro và claims LLM nếu có. Câu hỏi `research_action` là Choice đóng gồm `insufficient_data`, `needs_review`, `watchlist`, `risk_caution`; response cần `choice`, `confidence`, `probabilities`. Câu `requires_review` là Noul; response cần `noul` trong `[0,1]`. Client đòi đúng hai câu trả lời và `usage.input_tokens/output_tokens` dạng số nguyên không âm. Timeout kết nối/đọc là 8/30 giây; không redirect, không retry.

Không gửi `.env`, token tác vụ hoặc key trong prompt. Dữ liệu phân tích được gửi tới endpoint đã cấu hình; nhóm phải chọn endpoint phù hợp dữ liệu mình sử dụng. Cả hai không tự retry khi lỗi để tránh lặp chi phí.

## Kiểm tra đầu ra có sẵn

LLM trả JSON từ một đến sáu claims; mỗi claim có `text` và `source_ids`. Pydantic kiểm tra cấu trúc/độ dài; source IDs phải tồn tại trong bằng chứng đã gửi; claim có chữ số bị loại. Bộ tính riêng giữ quyền tính số liệu, tỷ số và giá kịch bản.

Jev kiểm tra tên câu hỏi, kiểu Choice/Noul, các lựa chọn khai báo, confidence, phân phối xác suất và usage. Choice chỉ nhận `insufficient_data`, `needs_review`, `watchlist`, `risk_caution`. Báo cáo demo, `partial` hoặc còn issues phải review; confidence dưới `JEV_MIN_CONFIDENCE` (mặc định `0.85`) hoặc Noul từ `0.5` cũng dẫn tới `applied_decision=needs_review`. Khi thiếu key/lỗi phản hồi, Jev ghi `unavailable/error` và giữ `needs_review`. Confidence là confidence của model, không phải xác suất lợi nhuận; output không phải khuyến nghị giao dịch.

Source ID tồn tại chưa chứng minh nguồn hỗ trợ nhận định; chữ số bị chặn chưa ngăn mọi suy diễn sai. Confidence/probabilities của Jev không phải xác suất sinh lời. Các kiểm tra có sẵn không thay việc review hoặc tạo lệnh giao dịch.

## Việc phải nghiệm thu trước bài nộp

Sườn có adapter và test mock, chưa có kết quả kiểm tra bằng thông tin xác thực live của nhóm. TV5 phối hợp TV1 và các chủ dữ liệu hoàn tất:

1. Kiểm tra riêng từng dịch vụ và cả hai: thiếu key, model discovery lỗi, HTTP lỗi, timeout, JSON/schema sai, nguồn giả, số AI tự đưa vào và phản hồi trống.
2. Chạy provider/model thật trên nhiều mã và ngành; ghi rõ mode dữ liệu, provider/model, thời gian, usage/chi phí nếu provider trả, trạng thái và hiện vật. Không ghi key vào log.
3. Đánh giá từng claim → nguồn; dữ liệu thiếu/mâu thuẫn; prompt injection; lựa chọn Jev và ngưỡng review. Bổ sung giới hạn chi phí/cache theo bằng chứng trước sử dụng rộng.
4. Xác nhận AI không sửa công thức, không biến null thành zero, không ghi đè điều kiện demo/thiếu dữ liệu; TV6 kiểm tra thể hiện trong PDF/JSON.

Chạy contract mock: `pytest tests/test_ai.py tests/test_jev.py -q`. Kết quả mock chỉ chứng minh hành vi client dưới phản hồi mô phỏng, không chứng minh API live hoặc chất lượng đầu tư.

Tham chiếu: [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), [TypeSafe OpenAPI](https://api.typesafe.ai/openapi.json), [contract Jev đã lưu](contracts/jev_contract.json).
