# VN Equity Lab - repo chung cho nhóm 6 thành viên

**Mục tiêu:** xây hệ thống phân tích tổng quan vĩ mô, ngành và cơ hội đầu tư vào cổ phiếu Việt Nam; tạo báo cáo PDF theo nhu cầu người dùng, có số liệu chính xác và bằng chứng kiểm tra.

**Đây là sườn có mã chạy được để cả nhóm phát triển tiếp.** Repo đã có luồng Web/CLI → dữ liệu → phân tích → PDF/JSON. Các dữ liệu thật cần cập nhật, đối chiếu và nghiệm thu theo [ma trận yêu cầu](docs/REQUIREMENTS.md). Việc tạo được PDF hoặc gọi được AI không tự chứng minh sản phẩm đã đáp ứng yêu cầu về độ chính xác.

## Bắt đầu ngay

Python 3.11 hoặc 3.12. Không cần khóa AI để chạy Demo.

```powershell
git clone https://github.com/trungnguyendoan132-source/vn-investment-research.git
cd vn-investment-research
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m vnresearch.cli serve
```

Mở `http://127.0.0.1:8000`. Chọn **Demo minh họa, chạy offline** để kiểm tra đủ các phần và tải PDF ngay. API tự mô tả ở `/docs`.

Tạo báo cáo qua CLI:

```powershell
.\.venv\Scripts\python.exe -m vnresearch.cli report --ticker FPT --mode demo --start-year 2022 --end-year 2025 --target-pe 20 --output var/demo-FPT
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
```

Linux/macOS: thay đường dẫn Python trong `.venv\Scripts` bằng `.venv/bin/python`.

## Đã có trong sườn

- Web tiếng Việt: chọn mã, ngày chốt, giai đoạn, hồ sơ rủi ro, nội dung PDF, CSV bổ sung và bật API AI.
- BCTC sẵn có: **6 tệp Parquet / 1.921.197 dòng upstream**, kỳ lớn nhất 2025; danh mục doanh nghiệp và phân ngành ICB. Số dòng không chứng minh độ phủ hay độ chính xác từng doanh nghiệp.
- Bộ tính tài chính thống nhất cho Web và CLI: ROA/ROE bình quân, thanh toán hiện hành, tỷ lệ nợ, biên lợi nhuận, CFO, FCF và YoY đúng năm liền kề. Ngân hàng không nhận tỷ số thanh khoản của doanh nghiệp sản xuất.
- Giá và giao dịch: nhập CSV với đơn vị rõ, kiểm tra OHLCV, loại dữ liệu sau ngày chốt, SMA20, lợi suất, biến động và drawdown. Có adapter tùy chọn `vnstock` và thông báo thiếu cấu hình.
- Vĩ mô: adapter World Bank theo năm và CSV có nguồn. Ngành: so sánh doanh nghiệp cùng phân ngành, cùng kỳ, dùng trung vị và số lượng dữ liệu thực.
- Tin và tài liệu: kế thừa bộ thu thập tin, xác nhận doanh nghiệp, khai phá từ khóa và trích đoạn; chỉ nhận bài có ngày hợp lệ. CLI `inspect-pdf` trích bằng chứng theo trang và đánh dấu trang scan cần OCR.
- Định giá: P/E theo EPS năm, P/B khi có số cổ phiếu lưu hành kèm nguồn; giá kịch bản từ bội số người dùng nhập. Không tự suy số cổ phiếu từ vốn điều lệ.
- API AI: LLM tương thích Chat Completions + Jev TypeSafe native /v1/systemone; endpoint tương thích Chat Completions, khóa riêng trong môi trường; đầu ra JSON được kiểm tra mã nguồn và chặn số liệu AI tự đưa vào phần diễn giải.
- PDF tiếng Việt, biểu đồ doanh thu, danh mục nguồn; JSON đầy đủ và manifest SHA-256.
- Tác vụ có UUID, token truy cập riêng, SQLite lưu tiến độ; khởi động lại đánh dấu tác vụ dở dang. Không nhận đường dẫn file máy chủ qua API.
- CI Windows/Linux, test hồi quy, contract dữ liệu và quy trình ghép nhánh.

## Phân công 6 thành viên

Chưa có tên/GitHub username nên dùng TV1–TV6. Trưởng nhóm điền tên thật theo vai trò này. Mỗi người nhận một nhánh riêng, không đẩy thẳng vào `main`.

| Thành viên | Phần sở hữu | Việc phải hoàn thiện | Nhánh |
|---|---|---|---|
| **TV1** | `api/`, `platform/`, `domain/`, CI | Tích hợp hệ thống, API contract, quản lý tác vụ, quyền truy cập, chuẩn dữ liệu và review ghép nhánh | `member01-platform` |
| **TV2** | `data/`, `assets/bctc/`, `assets/companies.csv` | Giá/giao dịch thật; BCTC mới; chuẩn đơn vị; corporate actions; đối chiếu báo cáo gốc và truy vết nguồn | `member02-market-financial-data` |
| **TV3** | `macro/`, `sector/`, `assets/macro/` | Vĩ mô cập nhật, lãi suất/tỷ giá; động lực ngành; peer group cùng kỳ; giải thích có bằng chứng | `member03-macro-sector` |
| **TV4** | `intelligence/`, `_vendor/`, từ điển | Tin doanh nghiệp, BCTN/BCTC và báo cáo CTCK; OCR, trích dẫn theo trang/ngày, xác thực doanh nghiệp và chống trùng | `member04-news-documents` |
| **TV5** | `analysis/` | Tỷ số, định giá theo ngành, kịch bản, rủi ro, bộ tổng hợp API AI và kiểm chứng lập luận | `member05-analysis-ai` |
| **TV6** | `static/`, `reports/`, demo/QA | Trải nghiệm người dùng, biểu đồ, nội dung PDF, kiểm thử luồng người dùng và hồ sơ bàn giao | `member06-ui-pdf-qa` |

**Đọc tài liệu nhận việc:** [TV1](docs/team/01-platform.md), [TV2](docs/team/02-data.md), [TV3](docs/team/03-macro-sector.md), [TV4](docs/team/04-intelligence.md), [TV5](docs/team/05-analysis-ai.md), [TV6](docs/team/06-ui-pdf.md).

## Kế thừa có chọn lọc

Nguồn: [Tumiqa/vn-annual-report-miner](https://github.com/Tumiqa/vn-annual-report-miner), commit `f8cad8d7d4276cd22aee20113fe3214230daf919`.

| Thành phần | Cách kế thừa / nâng cấp |
|---|---|
| Từ điển, fuzzy matcher, trích đoạn | Chép mã vào `_vendor/`, đổi import sang namespace mới; dùng trong phân tích tin/PDF. |
| News scraper | Chép có chỉnh sửa: đường dẫn asset theo package; loại tin không rõ năm khi lọc năm; bỏ fallback tắt kiểm tra TLS. Adapter mới yêu cầu ngày công bố đầy đủ. |
| Bộ kiểm tra BCTN | Giữ để dùng riêng khi người dùng xác định loại tài liệu là BCTN. Không áp ngưỡng BCTN cho mọi PDF tài chính. |
| Parquet, danh mục công ty, website và từ điển mẫu | Có sẵn trong package; dùng được khi chạy từ wheel, không phụ thuộc máy tác giả. |
| Bộ tính tỷ số cũ | **Thay bằng bộ tính mới**, sửa các sai lệch đã audit và giới hạn ở các tỷ số có định nghĩa rõ. |
| Server cũ, token nhúng, bootstrap môi trường và script bảo trì | Không đưa sang. API, lưu tác vụ và quyền tải file được viết mới. |

Chi tiết từng tệp, hash và phần bị loại ở [manifest kế thừa](third_party/upstream_manifest.json). Giữ thông tin tác giả và giấy phép upstream trong `third_party/`.

## Phần phải thêm/hoàn thiện để đạt đề bài

Các việc dưới đây là **backlog bắt buộc trước nghiệm thu bài nộp**, đã gán cho 6 thành viên; không coi sườn hiện tại là sản phẩm đã nghiệm thu.

1. **Dữ liệu thật và chính xác (TV2 + TV4):** chốt nguồn giá được sử dụng, cập nhật BCTC, kiểm tra đơn vị, điều chỉnh chia tách/cổ tức, phân biệt hợp nhất/riêng lẻ và lưu ngày công bố. Đối chiếu số liệu chính với báo cáo phát hành của doanh nghiệp.
2. **Vĩ mô (TV3):** bổ sung chuỗi tháng/quý, lãi suất, tỷ giá và chính sách phù hợp; trình bày thời kỳ và cơ chế ảnh hưởng tới ngành. World Bank theo năm là một nguồn đầu vào, không đại diện đầy đủ bối cảnh hiện tại.
3. **Ngành (TV3 + TV5):** peer group có lý do lựa chọn, động lực/chu kỳ ngành và chỉ tiêu riêng; không so trực tiếp tỷ số ngân hàng với sản xuất.
4. **Cơ hội đầu tư (TV5):** định giá theo mô hình phù hợp từng ngành, bội số có căn cứ, kịch bản tăng/giảm, độ nhạy, catalyst và rủi ro. Nhận định phải gắn với bằng chứng, giả định và thời hạn.
5. **Tin và tài liệu (TV4):** cập nhật nguồn hoạt động, kiểm tra đúng doanh nghiệp/ngày, đọc báo cáo CTCK khi nguồn được sử dụng, OCR trang scan và trích đúng trang. Tin không rõ ngày không được gán vào kỳ phân tích.
6. **AI (TV5 + TV1):** cấu hình nhà cung cấp/model thật, kiểm tra trên đa mã/đa ngành, giới hạn chi phí, đánh giá hỗ trợ của nguồn cho từng lập luận, prompt injection và lỗi nhà cung cấp. Test mô phỏng không chứng minh chất lượng model thật.
7. **PDF và vận hành (TV6 + TV1):** báo cáo theo nhu cầu có đủ vĩ mô → ngành → doanh nghiệp → cơ hội/rủi ro, biểu đồ đúng đơn vị, nguồn dẫn và ngày chốt. Kiểm tra PDF thực, luồng tải file, đồng thời nhiều tác vụ và phục hồi sau dừng tiến trình.

Ma trận đầy đủ và điều kiện đạt: [REQUIREMENTS](docs/REQUIREMENTS.md). Giao diện dữ liệu chung: [CONTRACTS](docs/contracts/README.md). Quy trình làm chung: [CONTRIBUTING](CONTRIBUTING.md).

## LLM + Jev - điền cấu hình của nhóm

Sửa **4 dòng kết nối** trong `.env`:

```dotenv
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=
JEV_BASE_URL=https://api.typesafe.ai
JEV_API_KEY=
```

Điền URL và key nhóm đang có, khởi động ứng dụng và chạy báo cáo. Web tự bật hai lựa chọn AI khi phát hiện key đã cấu hình; có thể bỏ chọn từng dịch vụ. Khóa nằm ở backend, không đưa xuống trình duyệt hay commit Git.

- **LLM** tổng hợp nội dung từ số liệu/bằng chứng. Base URL theo schema OpenAI-compatible, thường kết thúc `/v1`. `LLM_MODEL=auto` mặc định tìm model qua `/models`; nếu gateway không có endpoint này hoặc cần model cụ thể thì đặt `LLM_MODEL` theo nhà cung cấp.
- **Jev / TypeSafe AI** đánh giá hành động nghiên cứu bằng Choice + Noul qua `/v1/systemone`, dùng `JEV_MODEL=jev-latest`. Base có thể là host gốc, `/v1` hoặc full endpoint; client chuẩn hóa đường dẫn.
- LLM không tự tính tỷ số. Jev không được ghi đè kiểm tra dữ liệu thiếu/demo; quyết định có confidence thấp hoặc cần đối chiếu đi vào review. Không có thao tác đặt lệnh giao dịch.
- Chạy CLI với cả hai: `vnresearch report --ticker FPT --mode snapshot --ai --jev --output var/FPT`.
- Cả hai có timeout, kiểm tra schema, không tự retry lời gọi tính phí. Test hợp đồng hiện dùng mock; cần cấu hình key/model và kiểm tra nguồn thật trước khi nghiệm thu live.

Chi tiết: [API AI và Jev](docs/AI_INTEGRATION.md), [tích hợp Jev native](docs/JEV_INTEGRATION.md). Nguồn hợp đồng: [OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), [TypeSafe OpenAPI chính thức](https://api.typesafe.ai/openapi.json).

## Dữ liệu và chế độ chạy

| Chế độ | Dữ liệu / kết quả |
|---|---|
| `demo` | BCTC snapshot thật + giá/vĩ mô/tin **giả lập có nhãn**. Dùng kiểm tra đường ống, không dùng làm phân tích đầu tư thực. |
| `snapshot` | BCTC có sẵn; CSV thật của nhóm; snapshot World Bank nếu đã tải. Thiếu mục thì báo `partial`, không tạo số lấp chỗ trống. |
| `live` | Adapter nguồn ngoài + BCTC snapshot. Cần xác nhận nguồn, đơn vị và khóa khi nhà cung cấp yêu cầu. Lỗi nguồn được ghi vào chất lượng báo cáo. |

Định dạng CSV có mẫu trong `examples/` và contract. `report.json` giữ toàn bộ bảng ngành; PDF hiển thị bảng rút gọn và chỉ rõ nơi lấy đầy đủ. `manifest.json` lưu hash PDF/JSON và thông tin nguồn.

Không bật dịch vụ ra mạng khi chưa có `VNRESEARCH_API_KEY`. Tác vụ có token riêng; thư mục `var/`, file upload và `.env` không được commit. Cần bổ sung tài khoản người dùng và phân quyền phù hợp trước triển khai rộng.

## Cây repo

```text
src/vnresearch/
  api/            Web API và tạo tác vụ                      TV1
  platform/       cấu hình, SQLite, file kết quả             TV1
  domain/         schema chung, validation                   TV1 + review cả nhóm
  data/           BCTC, danh mục công ty, giá và giao dịch    TV2
  macro/          nguồn và phân tích vĩ mô                   TV3
  sector/         so sánh doanh nghiệp trong ngành           TV3
  intelligence/   tin tức, tài liệu và trích bằng chứng       TV4
  _vendor/        mã kế thừa có ghi nhận nguồn                TV4
  analysis/       tài chính, định giá, AI, pipeline           TV5
  reports/        PDF, JSON, manifest                        TV6
  static/         giao diện Web                              TV6
  assets/         BCTC, danh mục, từ điển, font
tests/            hồi quy, contract, API, AI, PDF
docs/team/        6 gói công việc, bàn giao và nghiệm thu
docs/contracts/   giao diện module và định dạng dữ liệu
third_party/      giấy phép và manifest kế thừa
.github/          CI và mẫu pull request
```
