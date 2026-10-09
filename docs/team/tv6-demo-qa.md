# TV6 demo PDF và QA artifact

## Hiện vật đã bàn giao

Các file dưới `docs/evidence/tv6-demo/` là một bản xuất `demo` có nhãn minh họa, không phải kết quả đầu tư live.

| File | Bytes | SHA-256 |
|---|---:|---|
| `report.pdf` | 40,939 | `b689257ec6750705feacb9629f4e9a2a69ab3466072c5875ba46e0d67f083aed` |
| `report.json` | 231,491 | `ff6c3e7b8f69d0fc0bd3a2f884ec9a2b6d3a5c6e254e0e0594dbe3d259d04a84` |

`manifest.json` ghi cùng byte count/hash. Năm PNG render nằm trong `docs/evidence/tv6-demo/images/`. Bản mới được render lại từ fixture sau khi tích hợp; cả năm trang đã được xem trực quan, không tràn trang hoặc lỗi Unicode. Biểu đồ đặt số LNST âm dưới mốc 0 và dùng màu đỏ.

## Giới hạn mẫu

- `report.json` ở schema 1.1.0, ticker FPT, mode `demo`.
- Mẫu có 11 nguồn: 10 nguồn BCTC legacy chưa xác minh và một nguồn giá synthetic; các đầu vào giá/vĩ mô/tin ở demo là giả lập.
- Mẫu không chứng minh độ chính xác của nguồn live, chất lượng OCR hay kết quả phân tích đầu tư.
- Báo cáo mẫu giữ `status=complete` cho pipeline demo nhưng decision ghi `MINH HỌA - KHÔNG DÙNG ĐỂ QUYẾT ĐỊNH ĐẦU TƯ`; 11 quality issues và nguồn `unverified/synthetic` vẫn phải được đọc.
- Tài liệu bàn giao gốc có số byte JSON và tổng test không nhất quán; các số ở đây lấy từ artifact được tạo lại, không giữ tuyên bố pass chưa tái lập.

## Tái tạo

```powershell
$env:PYTHONUTF8 = "1"
python demo/create_demo_pdf.py
```

Script xuất `var/demo-FPT/`, render PDF thành PNG, kiểm tra Unicode và in hash. Bản kiểm tra hiện tại: 5 trang, PDF 40,939 bytes, JSON 231,491 bytes; hash trong manifest khớp file. Hash PDF đổi khi layout thay đổi.
