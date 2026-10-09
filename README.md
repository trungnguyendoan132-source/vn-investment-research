# VN Equity Lab — sản phẩm nhóm 4

**Nhóm 4** xây dựng hệ thống hỗ trợ phân tích tổng quan vĩ mô, ngành và cơ hội đầu tư cổ phiếu Việt Nam; xuất PDF/JSON theo lựa chọn người dùng, kèm nguồn và trạng thái chất lượng. Đây là công cụ nghiên cứu, không bảo đảm dữ liệu đúng tuyệt đối hay lợi nhuận đầu tư.

**Luồng tự động có kiểm tra chất lượng.** Ở chế độ `live`, ứng dụng tự lấy các nguồn đã tích hợp; LLM/Jev chỉ chạy khi được bật và cấu hình. Ở `snapshot` dùng dữ liệu lưu/CSV; `demo` kiểm tra xuất báo cáo offline. Nguồn lỗi hoặc thiếu bằng chứng được thể hiện trong báo cáo `partial`, không được xem là xác nhận số liệu đúng. Phạm vi nghiệm thu còn lại nằm trong [ma trận yêu cầu](docs/REQUIREMENTS.md).

**Bằng chứng kiểm chứng hiện có:** [nền tảng](docs/TV1_IMPLEMENTATION.md), [dữ liệu](docs/TV2_IMPLEMENTATION.md), [audit](docs/TV1_TV2_AUDIT_PLAN.md). Đã đối chiếu 51 quan sát trong 7 envelope cho FPT/SSI/VCB và các kỳ so sánh. Đây là phạm vi hữu hạn, không phải xác nhận mọi mã/thời kỳ đều đúng.

## Chạy lần đầu trên Windows

Yêu cầu Python **3.11 hoặc 3.12** và Internet cho lần cài thư viện đầu tiên. Demo không cần API key LLM/Jev.

```powershell
git clone https://github.com/trungnguyendoan132-source/vn-investment-research.git
cd vn-investment-research
```

Mở thư mục vừa tải, nhấp đúp **`start_windows.bat`**. Trình khởi chạy chọn Python 3.12 hoặc 3.11, tạo `.venv`, cài ứng dụng và thư viện ở lần đầu, rồi chạy web tại `http://127.0.0.1:8000`. Giữ cửa sổ terminal mở trong khi dùng; nhấn `Ctrl+C` để dừng. Launcher không tạo `.env`; backend sẽ dùng file đó nếu bạn tự cấu hình. Demo không cần khóa.

Nếu chưa có Python 3.11/3.12 hoặc PowerShell không tìm thấy launcher, cài Python rồi chạy lại. Có thể khởi động thủ công:

```powershell
$env:PYTHONUTF8 = '1'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m vnresearch.cli serve --host 127.0.0.1 --port 8000
```

Giao diện mặc định chọn **Demo**. Chọn Demo để xem luồng xuất báo cáo offline; giá, vĩ mô và tin được gắn nhãn giả lập, còn BCTC lấy từ snapshot có sẵn. API tự mô tả ở `http://127.0.0.1:8000/docs`. Health: `/api/health` và `/api/health/ready`.

Tạo báo cáo qua CLI:

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m vnresearch.cli report --ticker FPT --mode demo --start-year 2022 --end-year 2025 --target-pe 20 --no-ai --no-jev --output var/demo-FPT
.\.venv\Scripts\python.exe -m ruff check src tests
```

Nếu `.env` trong repo có key thật, chạy pytest từ thư mục tạm mới để test thiếu-key không nạp cấu hình nhóm:

```powershell
$env:PYTHONUTF8 = '1'
$repo = (Resolve-Path .).Path
$testCwd = Join-Path $env:TEMP ('vnresearch-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testCwd | Out-Null
Push-Location $testCwd
try {
  & (Join-Path $repo '.venv\Scripts\python.exe') -m pytest -c (Join-Path $repo 'pyproject.toml') (Join-Path $repo 'tests') -q -p no:cacheprovider
} finally { Pop-Location }
```

Linux/macOS dùng `.venv/bin/python`.

## Tính năng sản phẩm

- Web tiếng Việt: chọn mã, ngày chốt, giai đoạn, hồ sơ rủi ro, nội dung PDF, CSV bổ sung và bật API AI.
- BCTC sẵn có: **6 tệp Parquet / 1.921.197 dòng upstream**, kỳ lớn nhất 2025; danh mục doanh nghiệp và phân ngành ICB. Số dòng không chứng minh độ phủ hay độ chính xác từng doanh nghiệp.
- Bộ tính tài chính thống nhất cho Web và CLI: ROA/ROE bình quân, thanh toán hiện hành, tỷ lệ nợ, biên lợi nhuận, CFO, FCF và YoY đúng năm liền kề. Ngân hàng không nhận tỷ số thanh khoản của doanh nghiệp sản xuất.
- Giá và giao dịch: nhập CSV với đơn vị rõ, kiểm tra OHLCV, loại dữ liệu sau ngày chốt, SMA20, lợi suất, biến động và drawdown. Live dùng adapter KBS trực tiếp theo contract đã ghim từ mã nguồn vnstock; `vnstock` không phải dependency runtime. Cơ sở điều chỉnh giá vẫn unknown.
- Vĩ mô: Live dùng sáu chỉ tiêu World Bank theo năm; snapshot có thêm mẫu CPI/GDP/tín dụng/lãi suất tháng-quý 2024 và sự kiện chính sách. Các dòng nhập mẫu đều `unverified`, có thể làm báo cáo `partial`, không phải chuỗi live đã đối chiếu. Ngành dùng peer cùng phân ngành/kỳ và trung vị trên số có dữ liệu.
- Tin và tài liệu: kế thừa bộ thu thập tin, xác nhận doanh nghiệp, khai phá từ khóa và trích đoạn; chỉ nhận bài có ngày hợp lệ. CLI `inspect-pdf` trích bằng chứng theo trang và đánh dấu trang scan cần OCR.
- Định giá: P/E theo EPS năm, P/B khi có số cổ phiếu lưu hành kèm nguồn; giá kịch bản từ bội số người dùng nhập. Không tự suy số cổ phiếu từ vốn điều lệ.
- AI: LLM dùng Chat Completions; Jev / TypeSafe AI dùng API quyết định có kiểu SystemOne. Có thể nhập URL, model và key riêng cho từng dịch vụ ngay trong giao diện; key theo phiên local.
- PDF tiếng Việt, biểu đồ doanh thu, danh mục nguồn; JSON đầy đủ và manifest SHA-256.
- Tác vụ có UUID, token truy cập riêng, SQLite lưu tiến độ; khởi động lại đánh dấu tác vụ dở dang. Không nhận đường dẫn file máy chủ qua API.
- Mẫu CI Windows/Linux sẵn ở `docs/ci/github-actions.yml`, test hồi quy, contract dữ liệu và quy trình ghép nhánh. Workflow GitHub Actions chưa được bật/chạy.

## Kiến trúc sản phẩm

| Thành phần | Vai trò |
|---|---|
| `api/`, `platform/`, `domain/` | API, hàng đợi job, quyền tải file, cấu hình và contract chung |
| `data/`, `assets/` | BCTC, danh mục doanh nghiệp, filing và giá/giao dịch |
| `macro/`, `sector/` | Chỉ tiêu vĩ mô và đối chiếu ngành theo kỳ |
| `intelligence/`, `_vendor/` | Tin, PDF tài chính và bằng chứng theo nguồn/trang |
| `analysis/` | Công thức, kịch bản, LLM và Jev có guard |
| `reports/`, `static/` | Giao diện, PDF, JSON và manifest |

API contract: [docs/contracts](docs/contracts/README.md). Cấu hình LLM/Jev: [docs/AI_INTEGRATION.md].

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

## Giới hạn nghiệm thu còn mở

- Số tài chính đã đối chiếu có phạm vi hữu hạn; danh mục hiện tại chưa chứng minh độ phủ mọi mã, mã nhỏ hoặc doanh nghiệp sản xuất.
- World Bank trả chuỗi năm sửa đổi mới nhất; chưa có bằng chứng vintage lịch sử tại từng ngày chốt. Cơ sở điều chỉnh giá KBS chưa xác minh.
- Nguồn tin live và OCR cần đối chiếu trên mẫu tài liệu thật; heuristic ticker/prompt-like chỉ là bộ lọc, không phải xác thực tuyệt đối.
- Test provider/UI hiện không thay cho kiểm tra key/model thật, review claim → nguồn và duyệt kết quả Jev trên nhiều ngành.
- GitHub Actions có workflow mẫu nhưng chưa có lần chạy CI được ghi nhận. PDF demo offline không thay thế nghiệm thu live đa mã/ngành và luồng trình duyệt.

Ma trận yêu cầu và điều kiện đạt: [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md). CI mẫu: [docs/ci/github-actions.yml](docs/ci/github-actions.yml).

## Kết nối LLM và Jev trong giao diện

Trong mục **Kết nối LLM và Jev TypeSafe**, điền Base URL, model và API key của từng dịch vụ rồi bấm **Lưu kết nối vào phiên**. Chỉ cần cấu hình provider muốn dùng. Sau khi lưu, các ô key được xóa; khi chọn `snapshot` hoặc `live`, giao diện bật checkbox tương ứng. Demo khóa hai lựa chọn để không gửi nội dung sang provider.

Các trường mặc định khớp gateway local nhóm 4:

| Dịch vụ | Base URL | Model |
|---|---|---|
| LLM Chat Completions | `http://localhost:61392/v1` | `gpt-6-luna` |
| Jev TypeSafe SystemOne | `http://127.0.0.1:8795/v1/systemone` | `jev-1.13-free` |

Dán key riêng của bạn vào ô password tương ứng. **Không đưa key vào repo, ảnh chụp hoặc báo cáo.** GUI gửi key tới `POST /api/provider-sessions` cùng origin. Endpoint chỉ nhận client loopback; nếu request có Origin thì Origin phải khớp. Key ở ô nhập trong RAM trình duyệt tới lúc submit, sau đó server giữ key trong RAM; không ghi key GUI vào `.env`, SQLite, report hay manifest. Session id nằm trong RAM của tab. Session và job snapshot có TTL tối đa 8 giờ; reload trang làm mất session id phía trình duyệt, còn server giữ session đến khi hết hạn hoặc tiến trình dừng. Job snapshot bị xóa sau thành công, giữ tạm khi retry lỗi. Mỗi lần lưu tạo phiên mới; nhập lại mọi provider bạn muốn tiếp tục dùng. Nếu server yêu cầu `VNRESEARCH_API_KEY`, nhập application key ở mục “Khóa API máy chủ”; đây không phải key LLM/Jev.

**LLM** tổng hợp luận điểm từ bằng chứng có sẵn qua Chat Completions; không tính lại số. **Jev / TypeSafe AI** là endpoint quyết định có kiểu native `/v1/systemone`, không phải Chat Completions. Jev nhận `state` và hai câu hỏi: `research_action` kiểu Choice trong `insufficient_data`, `needs_review`, `watchlist`, `risk_caution`; `requires_review` kiểu Noul từ 0 đến 1. Ứng dụng kiểm tra schema và áp guard: demo, báo cáo partial/còn issue, confidence dưới `JEV_MIN_CONFIDENCE` (mặc định 0.85) hoặc Noul từ 0.5 đều buộc `needs_review`. Confidence không phải xác suất lợi nhuận; Jev không đặt lệnh giao dịch.

HTTP chỉ được dùng cho loopback; provider ngoài máy cần HTTPS. Không theo redirect khi gửi key. Dữ liệu nghiên cứu được gửi tới endpoint bạn cấu hình. Việc lưu session chỉ xác nhận cấu hình được nhận, không xác thực key/model hay chất lượng output. Adapter có timeout, không tự retry request tính phí. Mẫu sạch key: [examples/local-gateways.env](examples/local-gateways.env). Chi tiết: [AI và Jev](docs/AI_INTEGRATION.md), [Jev native](docs/JEV_INTEGRATION.md).

## Dữ liệu và chế độ chạy

| Chế độ | Dữ liệu / kết quả |
|---|---|
| `demo` | BCTC snapshot thật + giá/vĩ mô/tin **giả lập có nhãn**. Dùng kiểm tra đường ống, không dùng làm phân tích đầu tư thực. |
| `snapshot` | BCTC/filing có sẵn, CSV người dùng, snapshot World Bank nếu có; không tự lấy giá/tin live. Có thể kiểm tra/tải filing gốc khi cần nên không bảo đảm hoàn toàn offline. Thiếu mục thì báo `partial`. |
| `live` | KBS daily OHLCV, World Bank năm, tin từ adapter hiện có và filing tùy coverage/điều kiện nguồn. LLM/Jev chỉ chạy khi bật và cấu hình. Nguồn lỗi hoặc chưa xác minh có thể tạo báo cáo `partial`; cơ sở điều chỉnh giá KBS vẫn unknown. |

Định dạng CSV có mẫu trong `examples/` và contract. `report.json` giữ toàn bộ bảng ngành; PDF hiển thị bảng rút gọn và chỉ rõ nơi lấy đầy đủ. `manifest.json` lưu hash PDF/JSON và thông tin nguồn.

Không bật dịch vụ ra mạng khi chưa có key truy cập. Dùng `VNRESEARCH_USER_TOKENS_JSON` để cấp token riêng từng người dùng; shared key chỉ là một principal. Tác vụ/upload có owner, hash và hạn dùng; queue SQLite có giới hạn, idempotency và recovery. Worker dở dang không tự lặp lời gọi AI không rõ kết quả. Chỉ một process dùng mỗi data directory. `/api/health/ready` tách khỏi liveness. `var/`, upload và `.env` không được commit.

## Cây repo

```text
src/vnresearch/
  api/            API và tạo tác vụ
  platform/       cấu hình, SQLite, file kết quả
  domain/         schema chung và validation
  data/           BCTC, danh mục công ty, giá và giao dịch
  macro/          nguồn và phân tích vĩ mô
  sector/         so sánh doanh nghiệp trong ngành
  intelligence/   tin tức, tài liệu và trích bằng chứng
  _vendor/        mã kế thừa có ghi nhận nguồn
  analysis/       tài chính, định giá, AI và pipeline
  reports/        PDF, JSON, manifest
  static/         giao diện Web
  assets/         BCTC, danh mục, từ điển, font
tests/            hồi quy, contract, API, AI, PDF
docs/team/        ghi chú vận hành và kiểm tra từng mô-đun
docs/contracts/   giao diện module và định dạng dữ liệu
docs/ci/          mẫu GitHub Actions
third_party/      giấy phép và manifest kế thừa
.github/          mẫu pull request
```
