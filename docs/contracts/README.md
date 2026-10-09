# Contract chung - phiên bản 1.0.0

TV1 quản lý `src/vnresearch/domain/models.py`. Thay contract phải cập nhật test, tài liệu và thông báo trong pull request trước khi ghép.

## API

- `POST /api/uploads/{prices|macro|news}`: multipart `file`, CSV UTF-8 tối đa 2 MB; trả `{id,kind,bytes}`.
- `POST /api/jobs`: JSON `AnalysisRequest`; trả 202 và `{id,token,status}`. 202 chỉ xác nhận xếp tác vụ.
- `GET /api/jobs/{id}`: header `X-Job-Token`; khi hoàn tất có `report`. Phân biệt `job.status=completed` với `report.status=partial`.
- `GET /api/jobs/{id}/files/{report.pdf|report.json|manifest.json}`: cùng token; chỉ tải khi tác vụ đã hoàn tất.
- Nếu cấu hình API key, mọi API nghiệp vụ còn cần `X-API-Key`. Không truyền key AI xuống trình duyệt.

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

`Report`: request, ticker, company_name, sector_name, status, decision, financial_years, sections, news, sources, issues, opportunities, risks, ai.

`Source`: id, title, url, kind, retrieved_at, period, sha256, note. `kind` gồm `snapshot/live/synthetic/user_supplied`. Mọi `source_ids` của section/metric/tin phải tồn tại. Việc nguồn tồn tại không tự chứng minh nội dung suy luận đúng; TV5 kiểm chứng lập luận.

`Metric.value=null` là thiếu/không tính được. Số 0 là giá trị quan sát bằng 0. Không đổi null thành 0 để tạo tỷ số. Tỷ số lưu dưới dạng phần số: 0.1 tương đương 10%; frontend/PDF phải chỉ rõ đơn vị trước khi đổi định dạng.

## Giao diện module

- TV2: `load_raw(tickers,start,end) -> (DataFrame,list[Source])`; `extract_facts(raw,ticker) -> list[dict]`; `load_prices(...) -> (DataFrame,list[Source],Section)`.
- TV3: `load_macro(...) -> (list[Source],Section)`; `compare_sector(...) -> (list[Source],Section)`.
- TV4: `load_news(...) -> (list[NewsArticle],list[Source],Section)`; `inspect_document(...) -> dict` có số trang và hash.
- TV5: `analyze(AnalysisRequest,input_paths,progress) -> Report`; AI chỉ tổng hợp bằng chứng đã có.
- TV6: `export_report(Report,directory) -> manifest`; tạo đúng PDF/JSON/hash và không gọi nguồn ngoài.

Không để UI gọi trực tiếp provider hoặc tự tính lại tỷ số. Không để prompt tự thay đổi công thức định lượng.
