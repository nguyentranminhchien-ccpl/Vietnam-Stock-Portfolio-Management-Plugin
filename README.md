# Vietnam Stock Portfolio Management Plugin

Hệ thống quản lý danh mục và phân tích cổ phiếu Việt Nam (HOSE/HNX/UPCoM) đa tác nhân (multi-agent), hỗ trợ tích hợp dữ liệu từ `mozyfin-cli` và cơ chế dự phòng tự động bằng thư viện `vnstock` v4.

Dự án hiện đã tích hợp thành công hai bộ lọc nổi tiếng **VCP Screener (Mark Minervini)** và **CANSLIM Screener (William O'Neil)** tối ưu hóa riêng cho thị trường chứng khoán Việt Nam.

---

## 1. Kiến trúc Hệ thống & Tính năng

Dự án này đóng gói toàn bộ quy trình phân tích và quản lý danh mục thành một **Antigravity Plugin** có thể tái sử dụng dễ dàng.

*   **Portfolio Tracker (`portfolio_tracker.py`)**: Tự động cập nhật thị giá cổ phiếu và hiển thị bảng báo cáo P&L động chia theo chiến lược Ngắn hạn (Short-term) / Dài hạn (Long-term).
*   **Short-Term Swing Trader (`st_trader_scan.py`)**: Quét các đường trung bình động (SMA 20/50), RSI (14) và MACD để đưa ra cảnh báo kỹ thuật (HOLD / BUY / SELL / STOP LOSS) cho các cổ phiếu lướt sóng.
*   **Long-Term Analyst (`lt_investor_report.py`)**: Sử dụng skill `vietnam-equity-analyst` để tự động tạo báo cáo phân tích định lượng và cơ bản chuyên sâu dạng Markdown (Tiếng Việt) cho các cổ phiếu tích sản.
*   **Transaction Manager (`update_portfolio.py`)**: Công cụ command-line để mua/bán cổ phiếu, tự động tính lại giá vốn bình quân gia quyền, quản lý tiền mặt và lưu nhật ký giao dịch (`transactions.json`).
*   **VCP Screener (`vcp_screener.py`)**: Lọc cổ phiếu theo mẫu hình biên độ thu hẹp VCP và mẫu xu hướng tăng Stage 2 của Mark Minervini. Hỗ trợ tính Relative Strength (RS) so với VN-Index và kiểm tra Volume kiệt quệ (VUD).
*   **CANSLIM Screener (`canslim_screener.py`)**: Lọc và chấm điểm (thang điểm 100) theo 7 tiêu chí tăng trưởng CANSLIM của William O'Neil. Hỗ trợ tổng hợp dữ liệu doanh thu/lợi nhuận quý/năm và cơ cấu cổ đông tổ chức.
*   **Dual-Data Fallback Engine (`vnstock_fallback.py`)**: Khi tài khoản Mozyfin hết lượt truy vấn (Insufficient credits), hệ thống sẽ tự động chuyển sang gọi thư viện `vnstock` v4 để lấy báo cáo tài chính và dữ liệu giá hoàn toàn miễn phí.
*   **Token-Saving Skip Logic**: Tự động bỏ qua việc tải lại báo cáo tài chính dài hạn nếu file báo cáo của cổ phiếu đó được tạo/cập nhật dưới 7 ngày, giúp tối ưu chi phí API.

---

## 2. Cài đặt & Chuẩn bị

### Bước 1: Cài đặt Dependencies
Cài đặt các gói thư viện Python cần thiết:
```bash
pip install pandas requests tabulate seaborn tenacity pytz importlib-metadata vnai numpy
```

*Lưu ý cho môi trường Python 3.14 (hoặc môi trường thiếu trình biên dịch C++):*
Để cài đặt `vnstock` mà không gặp lỗi biên dịch Meson khi cài đặt `numpy`, hãy chạy lệnh sau:
```bash
pip install vnstock --no-deps
pip install vnstock_ezchart --no-deps
```

### Bước 2: Tích hợp Mozyfin CLI (Khuyến khích)
Để có báo cáo định tính nâng cao bằng AI, hãy cài đặt `mozyfin-cli` và đăng nhập tài khoản của bạn:
```bash
npm install -g mozyfin-cli
mozyfin login --api-key <your-api-key>
```

---

## 3. Cách Sử Dụng qua Command Line

1.  **Chạy toàn bộ luồng quy trình (Cập nhật giá + Quét tín hiệu + Tạo báo cáo)**:
    ```powershell
    python pm_orchestrator.py
    ```
2.  **Xem bảng P&L danh mục**:
    ```powershell
    python portfolio_tracker.py
    ```
3.  **Ghi nhận giao dịch mua/bán**:
    ```powershell
    # MUA thêm 300 cổ phiếu DPM.VN ở mức giá 24,250 VND (Chiến lược dài hạn)
    python update_portfolio.py buy DPM.VN 300 24250 long-term

    # BÁN 500 cổ phiếu SHS.VN ở mức giá 18,300 VND (Chiến lược ngắn hạn)
    python update_portfolio.py sell SHS.VN 500 18300 short-term
    ```
4.  **Chạy bộ lọc mẫu hình VCP (Mark Minervini)**:
    ```powershell
    # Chạy lọc mặc định
    python vcp_screener.py

    # Chạy chế độ nghiêm ngặt và chỉ hiển thị Top 5 mã tốt nhất
    python vcp_screener.py --strict --top 5
    ```
5.  **Chạy bộ lọc cổ phiếu tăng trưởng CANSLIM (William O'Neil)**:
    ```powershell
    # Lọc cổ phiếu trong danh mục và watchlist mặc định
    python canslim_screener.py

    # Lọc các mã cụ thể được chọn lọc
    python canslim_screener.py --universe FPT.VN HPG.VN GMD.VN --top 3
    ```

---

## 4. Tương tác Không Cần Code qua Cửa Sổ Chat Antigravity

Bạn có thể chia sẻ thư mục plugin này cho bất kỳ ai sử dụng **Antigravity**. Khi họ tải plugin, họ chỉ cần chat trực tiếp với AI để ra lệnh:

*   *"Xem danh mục của tôi"* -> AI sẽ tự động chạy `portfolio_tracker.py` và in ra bảng P&L trực tiếp trong khung chat.
*   *"Tôi vừa mua thêm 500 cổ phiếu GMD.VN giá 75000 dài hạn"* -> AI sẽ tự động chạy tập lệnh cập nhật vị thế và báo lại kết quả.
*   *"Quét tín hiệu kỹ thuật ngắn hạn"* -> AI sẽ quét SMA, RSI, MACD của các vị thế ngắn hạn và đưa ra khuyến nghị mua/bán/nắm giữ.
*   *"Mở báo cáo nghiên cứu DPM"* -> AI sẽ hiển thị báo cáo định giá bằng Tiếng Việt được lưu trữ trong thư mục `reports/`.
*   *"Lọc cổ phiếu VCP"* -> AI sẽ chạy kịch bản lọc VCP và tóm tắt danh sách các mã đang tích lũy biến độ thu hẹp nổi bật trên thị trường.
*   *"Quét điểm CANSLIM"* -> AI sẽ tự động chấm điểm cổ phiếu theo các trụ cột tăng trưởng doanh thu, lợi nhuận ròng, sức mạnh giá và sở hữu tổ chức.
