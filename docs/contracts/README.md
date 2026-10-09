# Contract chung - phiên bản 1.1.0

TV1 quản lý `src/vnresearch/domain/models.py`. Thay contract phải cập nhật test, tài liệu và thông báo trong pull request trước khi ghép.

## API

- `POST /api/uploads/{prices|macro|news}`: multipart `file`, CSV UTF-8 tối đa 2 MB; trả `{id,kind,bytes}`.
- `POST /api/jobs`: JSON `AnalysisRequest`; trả 202 và `{id,token,status}`. 202 chỉ xác nhận xếp tác vụ.
- `AnalysisRequest` mặc định `live`, `use_ai=true`, `use_jev=true`. Khi chọn Demo, các flag bị bỏ qua trong yêu cầu mặc định tắt để chạy offline; flag được gửi rõ ràng vẫn giữ giá trị người dùng. `GET /api/capabilities` trả trạng thái cấu hình theo sự hiện diện của key; không trả key hoặc tự kiểm tra thông tin xác thực live.
- `GET /api/jobs/{id}`: header `X-Job-Token`; khi hoàn tất có `report`. Phân biệt `job.status=completed` với `report.status=partial`.
- `GET /api/jobs/{id}/files/{report.pdf|report.json|manifest.json}`: cùng token; chỉ tải khi tác vụ đã hoàn tất.
- Nếu cấu hình API key, mọi API nghiệp vụ còn cần `X-API-Key`. Không truyền key AI xuống trình duyệt.

## Bổ sung TV1 (1.1.0)

- `X-API-Key` ánh xạ principal theo `VNRESEARCH_USER_TOKENS_JSON={"tv1":"token-riêng",...}`. Chế độ cũ không auth/shared key dùng principal `local`; không tự coi shared key là danh tính 6 người khác nhau.
- Upload có owner, SHA-256, hạn dùng và `validation_status=header_validated`. Điều này xác nhận cấu trúc CSV; không xác nhận số liệu đúng với nguồn phát hành. Chỉ cùng owner có thể gắn upload vào job.
- `Idempotency-Key` trên POST jobs: cùng owner/yêu cầu trả cùng job; tái dùng key cho yêu cầu khác trả 409. Queue hữu hạn trả 429 thay vì chấp nhận không giới hạn.
- `POST /api/jobs/{id}/cancel` dừng queued hoặc yêu cầu running dừng tại ranh giới an toàn. Không tự replay job chạy dở có thể đã gọi AI. `retry` là thao tác rõ ràng, giữ parent_job_id và bằng chứng lần trước.
- Job status cũ được giữ: queued/running/completed/failed/interrupted. SQLite schema version 2 migrates dữ liệu và token job cũ. `completed` vẫn độc lập `Report.status=partial`.
- `/api/health/live` là liveness; `/api/health/ready` kiểm tra DB, data directory, assets và dispatcher. Health không gọi API tính phí.
- Error body có code và request_id; API không lặp lại giá trị key/token trong lỗi validation. File thiếu/hỏng sau completed thành lỗi artifact có mã.
- Chỉ một process dùng một data directory. Tăng worker qua setting bên trong process; không chạy nhiều Uvicorn process chung thư mục.

## Metadata nguồn và số liệu

`Source` thêm `published_on`, `published_at`, `publication_precision`, `period_start/end/type`, `report_basis`, `unit`, `currency`, `mapping_version`, `dataset_version`, `verification_status`. Default là unknown. Date-only giữ `published_at=null`; retrieved_at không thay ngày công bố.

`FinancialYear` thêm `fact_metadata` và `quality_issues`. Mỗi số cần metadata theo field; output 1.1 không tương thích với reader 1.0 có `extra=forbid`, nên các consumer phải cập nhật cùng bản contract. Reader mới vẫn đọc các report1.0 với defaultunknown. Không mặc định dùng số legacy để ra kết luận thực.

LLM/Jev dùng helper URL chung: HTTPS giữ xác thực TLS; HTTP chỉ localhost được kiểm tra phân giải hoặc IP loopback. Không theo redirect khi gửi key. Explicit model được giữ nguyên; model auto chỉ dùng khi không yêu cầu model cụ thể.

## CSV giá

`ticker,date,open,high,low,close,volume,price_unit,source_url`

Ngày `YYYY-MM-DD`; đơn vị `VND` hoặc `thousand_VND`. Một mã/ngày không trùng, giá dương, low ≤ open/close ≤ high, volume không âm. Không tự đoán đơn vị. Nguồn nhập phải ghi rõ việc điều chỉnh giá/cổ tức/chia tách khi dùng phân tích lịch sử.

## CSV vĩ mô

`indicator,label,year,value,unit,source_url,retrieved_at`

Mỗi chỉ tiêu/năm duy nhất; đơn vị bắt buộc. `retrieved_at` ISO-8601 có múi giờ. Snapshot theo năm chỉ dùng kỳ đã hoàn tất. TV3 mở rộng contract sang tháng/quý bằng pull request có version và test.

## CSV tin

`ticker,title,text,url,published_at`

Ngày đầy đủ `YYYY-MM-DD` hoặc datetime ISO. Không gán ngày từ một năm nhắc trong nội dung. Chỉ nhận tin tại/trước ngày chốt và không quá 365 ngày trong adapter hiện tại.

## Report và nguồn

`Report`: request, ticker, company_name, sector_name, status, decision, financial_years, sections, news, sources, issues, opportunities, risks, ai, jev.

`Source`: id, title, url, kind, retrieved_at, period, sha256, note. `kind` gồm `snapshot/live/synthetic/user_supplied`. Mọi `source_ids` của section/metric/tin phải tồn tại. Việc nguồn tồn tại không tự chứng minh nội dung suy luận đúng; TV5 kiểm chứng lập luận.

`Metric.value=null` là thiếu/không tính được. Số 0 là giá trị quan sát bằng 0. Không đổi null thành 0 để tạo tỷ số. Tỷ số lưu dưới dạng phần số: 0.1 tương đương 10%; frontend/PDF phải chỉ rõ đơn vị trước khi đổi định dạng.

## Giao diện module

- TV2: `load_raw(tickers,start,end) -> (DataFrame,list[Source])`; `extract_facts(raw,ticker) -> list[dict]`; `load_prices(...) -> (DataFrame,list[Source],Section)`.
- TV3: `load_macro(...) -> (list[Source],Section)`; `compare_sector(...) -> (list[Source],Section)`.
- TV4: `load_news(...) -> (list[NewsArticle],list[Source],Section)`; `inspect_document(...) -> dict` có số trang và hash.
- TV5: `analyze(AnalysisRequest,input_paths,progress) -> Report`; `synthesize(Report) -> dict` ghi kết quả LLM vào `Report.ai`; `evaluate(Report) -> dict` ghi kết quả Jev vào `Report.jev`. TV2 cấp số liệu, TV3 cấp vĩ mô/ngành, TV4 cấp nguồn; AI chỉ dùng bằng chứng đã có.
- TV6: `export_report(Report,directory) -> manifest`; tạo đúng PDF/JSON/hash và không gọi nguồn ngoài.

Không để UI gọi trực tiếp provider hoặc tự tính lại tỷ số. Không để prompt tự thay đổi công thức định lượng.

## Contract AI và cấu hình backend

TV1 quản lý `LLM_BASE_URL`, `LLM_API_KEY`, `JEV_BASE_URL`, `JEV_API_KEY`; TV5 quản lý adapter/prompt và đánh giá; TV6 hiển thị trạng thái, nguồn và kết quả review. `LLM_MODEL=auto` khám phá qua `/models` trước khi gọi `/chat/completions`; provider không hỗ trợ phải đặt model cụ thể. Jev mặc định `JEV_MODEL=jev-latest`, endpoint native `/v1/systemone`; không chuyển Jev sang schema Chat Completions.

- `ai`: trạng thái `disabled/unavailable/error/ok`; khi hợp lệ có model, claims `{text,source_ids}`, latency và note. Source IDs hợp lệ chưa chứng minh nội dung claim đúng.
- Cache AI chỉ lưu đầu ra đã qua kiểm tra, trong bộ nhớ process tối đa 128 mục trong 300 giây. Định danh gồm endpoint, model, request, bằng chứng/phiên bản nguồn, phiên bản prompt và scope credential đã hash; không lưu key thô. Cache trả bản sao độc lập và ghi `cache_hit`, không coi hit là một lời gọi provider mới.
- `jev`: trạng thái `disabled/unavailable/error/ok`; khi hợp lệ có proposed/applied decision, confidence, probabilities, requires_review_probability, review_required, deterministic_guard, usage, latency và note. Choice giới hạn ở `insufficient_data/needs_review/watchlist/risk_caution`; Noul giữ số thực trong `[0,1]`.
- Dữ liệu demo, báo cáo `partial` hoặc còn issues chặn việc bỏ qua review; confidence dưới `JEV_MIN_CONFIDENCE=0.85` hoặc Noul từ `0.5` áp dụng `needs_review`. Confidence không phải xác suất lợi nhuận.

Test AI/Jev trong sườn là mock. TV5/TV1 phải lưu bằng chứng kiểm tra với key/model thật và TV6 kiểm tra đầu ra trước đánh dấu nghiệm thu tích hợp live. Xem [API AI](../AI_INTEGRATION.md) và [Jev](../JEV_INTEGRATION.md).
