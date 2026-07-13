# Cải tiến Kỹ năng Phân tích & Lọc Cổ phiếu (Pre-Screening Rules)

## 1. Mục tiêu
Văn bản này bổ sung các quy tắc "tiền kiểm tra" (Pre-screening) và "lọc rác" nhằm cải thiện chất lượng đầu ra của các subagent `stock_screener` (CANSLIM, VCP, Buffett). Do thị trường chứng khoán Việt Nam có nhiều đặc thù về thanh khoản và dữ liệu thô thường bị nhiễu, các quy tắc này là **bắt buộc** phải áp dụng trước khi đưa ra khuyến nghị cuối cùng cho người dùng.

## 2. Các Quy Tắc Lọc Rác & Kiểm Tra Tính Hợp Lý

Khi phân tích kết quả trả về từ các file báo cáo (`.json` hoặc `.md`) của các bộ lọc, AI cần tự động thực hiện các bước sau:

- **Thanh khoản:** Bỏ qua hoặc cảnh báo rủi ro cực cao nếu cổ phiếu có thanh khoản bình quân (Volume) quá thấp (ví dụ: < 100,000 cổ phiếu/phiên). 
- **Dữ liệu nhiễu (P/E & P/B):** Nếu hệ số P/E hiển thị > 100, P/E < 0, hoặc giá trị `999.0`, AI phải tự động nhận diện đây là dữ liệu có thể bị nhiễu (thường do lợi nhuận quá mỏng, chia cho 0 hoặc công ty đang lỗ nặng). Đừng coi mức P/E này là định giá đắt/rẻ một cách máy móc, hãy ghi chú: *"Dữ liệu P/E bất thường/nhiễu, cần đánh giá lại EPS cốt lõi."*
- **Biến động không tự nhiên:** Đối với VCP screener, biên độ dao động tại HOSE bị giới hạn 7%, HNX 10% và UPCOM 15%. Nếu mẫu hình nêm siết chặt biên độ dưới 3%, hãy lưu ý rằng điều này có thể bị bóp méo bởi trần/sàn thay vì cung cầu tự nhiên.
- **Tính chu kỳ (Cyclicality):** Đối với các ngành thâm dụng vốn (Điện, Thép) hay chu kỳ mạnh (Bất động sản), ROIC thấp hoặc FCF âm trong ngắn hạn có thể là do giai đoạn đầu tư dự án (Capex lớn). Đừng tự động đánh trượt công ty (điểm 0) theo tiêu chuẩn Buffett mà không có lời giải thích bối cảnh.

## 3. Cách Thức Hoạt Động (Agent Guidelines)

Sau khi đọc file báo cáo đầu ra (ví dụ `buffett_report.md` hoặc `vcp_screener.md`), nếu bạn nhận thấy cổ phiếu vi phạm các "Cờ Đỏ" (Red flags) ở trên, bạn **phải**:
1. Trình bày rõ điểm số gốc mà hệ thống chấm.
2. Thêm một mục **"Pre-Screening Warning"** hoặc **"Fact-Check"** để chỉ ra điểm vô lý của dữ liệu thô.
3. Điều chỉnh hoặc đưa ra kết luận trung lập, khách quan hơn thay vì chỉ dựa vào điểm số tự động của công cụ.
