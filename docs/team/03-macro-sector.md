# TV3 - Vĩ mô và ngành

Nhánh: `member03-macro-sector`. Sở hữu `macro/`, `sector/`, `assets/macro/`. Nhận BCTC và universe từ TV2; cung cấp Section + Source cho TV5/TV6.

## Có sẵn

Adapter World Bank cho GDP thực, CPI và xuất khẩu/GDP theo năm; CSV có nguồn. Peer group theo ICB cấp 2, cùng năm, các tỷ số thống nhất, trung vị chỉ trên số có dữ liệu.

## Công việc cần hoàn thiện

1. Bổ sung dữ liệu tháng/quý phù hợp: tăng trưởng, lạm phát, lãi suất, tỷ giá, tín dụng và chính sách có ảnh hưởng ngành; lưu kỳ/đơn vị/ngày nguồn.
2. Phân tích cơ chế tác động tới ngành mục tiêu; phân biệt quan sát với giả thuyết, tránh biến tương quan thành khẳng định nhân quả.
3. Xây hồ sơ đặc thù ngành: động lực cầu/cung, chu kỳ, cạnh tranh và chỉ tiêu chuyên biệt; phối hợp TV5 cho ngân hàng, chứng khoán và sản xuất.
4. Chọn peer group có lý do, cùng loại BCTC và kỳ; nêu sample size và dữ liệu bị loại, không lấy trung vị từ số 0 lấp thiếu.
5. Đưa bảng/đồ thị/nhận định có nguồn vào contract, kiểm tra ảnh hưởng của dữ liệu cũ.

## Bàn giao / điều kiện đạt

Bản phân tích vĩ mô và ngành thật cho các mã demo nghiệm thu; mỗi nhận định có Source hoặc được ghi là giả thuyết cần xác nhận. Có test thiếu chỉ tiêu, lệch kỳ, nhóm ngành quá nhỏ và lỗi nguồn.

API nguồn tham khảo: https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures .
