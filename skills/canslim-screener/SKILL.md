---
name: canslim-screener
description: Quét các cổ phiếu Việt Nam theo hệ thống đầu tư tăng trưởng CANSLIM của William O'Neil. Sử dụng khi người dùng yêu cầu lọc cổ phiếu có tăng trưởng doanh thu/lợi nhuận mạnh mẽ, sức mạnh giá (Relative Strength) vượt trội và có sự đồng hành của tổ chức lớn.
---

# CANSLIM Stock Screener (Hệ thống Đầu tư Tăng trưởng - William O'Neil)

Skill này thực hiện phân tích và lọc các cổ phiếu tiềm năng trên thị trường chứng khoán Việt Nam theo hệ sinh thái CANSLIM (7 tiêu chí cốt lõi):

## Tóm tắt 7 tiêu chí CANSLIM tại Việt Nam:
1. **C (Current Earnings)**: Tăng trưởng doanh thu và lợi nhuận ròng quý gần nhất YoY >= 20%.
2. **A (Annual Growth)**: Tăng trưởng lợi nhuận hàng năm (3 năm liên tục) >= 20% và tỷ suất sinh lời ROE >= 17%.
3. **N (Newness)**: Cổ phiếu nằm gần hoặc chuẩn bị đột phá vượt đỉnh 52 tuần (khoảng cách cách đỉnh <= 15%).
4. **S (Supply/Demand)**: Kiểm tra thanh khoản bình quân 50 phiên (> 100k cổ phiếu) và tỷ lệ tích lũy khối lượng (Up/Down Volume Ratio > 1.0).
5. **L (Leadership)**: Sức mạnh giá tương đối (Relative Strength - RS) đa khung thời gian có trọng số vượt trội hơn chỉ số VN-Index (VNINDEX).
6. **I (Institutional)**: Sự ủng hộ của tổ chức lớn thông qua tổng tỷ lệ sở hữu của cổ đông tổ chức, khối ngoại hoặc SCIC >= 30%.
7. **M (Market)**: Đánh giá xu hướng thị trường chung của VN-Index (Uptrend / Downtrend) để kích hoạt chế độ phòng vệ trong thị trường gấu.

---

## Hướng dẫn thực thi (Usage)

Chạy bộ lọc thông qua tập lệnh Python:

```powershell
# Chạy bộ lọc mặc định (Quét danh sách theo dõi và danh mục hiện tại)
python canslim_screener.py

# Quét danh sách cổ phiếu tùy chỉnh
python canslim_screener.py --universe FPT.VN HPG.VN GMD.VN VEA.VN

# Chỉ lấy Top 5 cổ phiếu hàng đầu và xuất báo cáo ra thư mục riêng
python canslim_screener.py --top 5 --output-dir reports/
```

## Kết quả xuất ra (Outputs)
* Báo cáo dạng Markdown hiển thị bảng điểm và xếp hạng trực quan: `reports/canslim_screener_YYYY-MM-DD_HHMMSS.md`
* Báo cáo dạng cấu trúc JSON phục vụ tích hợp tự động: `reports/canslim_screener_YYYY-MM-DD_HHMMSS.json`
