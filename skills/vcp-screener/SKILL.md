---
name: vcp-screener
description: Quét các cổ phiếu Việt Nam theo mẫu hình Volatility Contraction Pattern (VCP) của Mark Minervini. Sử dụng khi người dùng yêu cầu lọc cổ phiếu theo mẫu hình biên độ thu hẹp, tìm các cổ phiếu đang tích lũy siết nền (tight base) hoặc mẫu hình bứt phá xu hướng (breakout).
---

# VCP Stock Screener (Mẫu hình Biên độ Thu hẹp - Mark Minervini)

Skill này giúp lọc các cổ phiếu trên thị trường chứng khoán Việt Nam (HOSE/HNX/UPCoM) theo mẫu hình Biên độ Thu hẹp (VCP) và Mẫu xu hướng (Trend Template) của nhà vô địch đầu tư chứng khoán Mỹ - Mark Minervini.

## Các tiêu chí lọc của mẫu xu hướng (7-point Trend Template):
1. Thị giá hiện tại nằm trên cả 2 đường trung bình động SMA 150 và SMA 200.
2. Đường SMA 150 nằm trên đường SMA 200.
3. Đường SMA 200 đang có xu hướng hướng lên (tăng trưởng trong 20 phiên gần nhất).
4. Đường SMA 50 nằm trên cả SMA 150 và SMA 200.
5. Thị giá hiện tại nằm trên đường trung bình động SMA 50.
6. Thị giá hiện tại cao hơn đáy 52 tuần tối thiểu là 30%.
7. Thị giá hiện tại nằm trong phạm vi cách đỉnh 52 tuần tối đa là 25%.

## Mẫu hình VCP:
* Phát hiện chuỗi pullback thu hẹp biên độ biến động giảm dần (Ví dụ: 15% -> 8% -> 3%).
* Kiểm tra hiện tượng kiệt quệ khối lượng (Volume Dry-up - VUD) tại các nhịp siết nền cuối cùng.
* Tính toán Relative Strength (RS) so với chỉ số VN-Index (VNINDEX).

---

## Hướng dẫn thực thi (Usage)

Chạy bộ lọc thông qua tập lệnh Python:

```powershell
# Chạy bộ lọc mặc định (Quét danh sách theo dõi và danh mục hiện tại)
python vcp_screener.py

# Quét danh sách cổ phiếu tùy chỉnh
python vcp_screener.py --universe FPT.VN HPG.VN GMD.VN

# Chạy chế độ nghiêm ngặt (chỉ trả về cổ phiếu đạt đủ xu hướng tăng và mẫu hình)
python vcp_screener.py --strict --min-contractions 2

# Chỉ lấy Top 5 cổ phiếu hàng đầu và xuất báo cáo ra thư mục riêng
python vcp_screener.py --top 5 --output-dir reports/
```

## Kết quả xuất ra (Outputs)
* Báo cáo dạng Markdown hiển thị bảng xếp hạng trực quan: `reports/vcp_screener_YYYY-MM-DD_HHMMSS.md`
* Báo cáo dạng cấu trúc JSON phục vụ tích hợp tự động: `reports/vcp_screener_YYYY-MM-DD_HHMMSS.json`
