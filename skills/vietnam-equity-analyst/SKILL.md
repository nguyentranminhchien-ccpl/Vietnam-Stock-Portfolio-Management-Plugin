---
name: vietnam-equity-analyst
description: "Perform long-term fundamental equity research on Vietnam stocks using mozyfin-cli following a structured analyst framework."
---

# vietnam-equity-analyst

Use this skill when you need to conduct a deep-dive long-term investment research report on any company listed on the Vietnam Stock Market (HOSE/HNX/UPCoM) using the `mozyfin` CLI.

## Objective

Act as a senior equity research analyst. Your task is to perform thorough fundamental research on a target Vietnamese stock, gather objective data, and write a structured, data-driven report using financial data from the last 5 full fiscal years and the most recent trailing twelve months (TTM).

## Step-by-Step Research Workflow

1.  **Understand the Target Ticker**:
    *   Verify the ticker symbol (e.g., `DPM.VN`, `VSC.VN`, `GMD.VN`). If not known, search using:
        ```bash
        mozyfin search --query <CompanyName>
        ```
    *   Get the basic profile:
        ```bash
        mozyfin profile <TICKER>.VN
        ```

2.  **Gather Financial Statements and Statistics**:
    *   Export the financial statements to a CSV for analysis:
        ```bash
        mozyfin financials <TICKER>.VN --csv financials.csv
        ```
    *   Get key financial ratios (P/E, P/B, ROE, ROA, Debt/Equity) for historical comparison:
        ```bash
        mozyfin stats <TICKER>.VN --year 2024
        # Repeat for other years as needed or query via ask
        ```

3.  **Perform Competitor Comparison**:
    *   Identify the top 3 direct competitors in the same industry (e.g., for `DPM.VN`, compare with `DCM.VN` and `BFC.VN`).
    *   Fetch valuation and performance stats for competitors:
        ```bash
        mozyfin stats <COMPETITOR_TICKER>.VN --year 2024
        ```
    *   Use `mozyfin ask` to compare margins or growth trends if needed:
        ```bash
        mozyfin ask "Compare <TICKER> and <COMPETITOR> net profit margins and ROE over the last 3 years"
        ```

4.  **Analyze Qualitative Factors (Moat, Growth, Management)**:
    *   Query the analysis reports database using natural language:
        ```bash
        mozyfin doc "<TICKER> competitive moat"
        mozyfin doc "<TICKER> growth strategy and capacity expansion"
        mozyfin doc "<TICKER> board of directors and ownership"
        ```
    *   Fetch latest news to capture recent catalysts:
        ```bash
        mozyfin news --entities <TICKER>.VN --limit 10
        ```

5.  **Evaluate Risk Metrics**:
    *   Fetch risk and volatility metrics:
        ```bash
        mozyfin risk <TICKER>.VN --limit 252 --risk-free 0.03
        ```

---

## Report Structure (Tiếng Việt)

Cấu trúc báo cáo phân tích bắt buộc bao gồm các phần sau:

### 1. Tóm tắt dự án (Executive Summary)
*   Tổng quan ngắn gọn về hoạt động kinh doanh của công ty.
*   Luận điểm đầu tư trong 2-3 câu: Nên Mua, Nắm giữ hay Bán ở mức định giá hiện tại?
*   Các động lực tăng trưởng tích cực và rủi ro lớn nhất.

### 2. Hiệu quả Tài chính & Sức khỏe Doanh nghiệp (Financial Performance & Health)
*   **Báo cáo kết quả kinh doanh**: Phân tích tăng trưởng doanh thu, biên lợi nhuận gộp, biên lợi nhuận hoạt động và xu hướng biên lợi nhuận sau thuế trong 5 năm qua + TTM.
*   **Bảng cân đối kế toán**: Đánh giá mức độ nợ, tỷ lệ nợ/vốn chủ sở hữu, tỷ số thanh toán hiện hành và lượng tiền mặt. Bảng cân đối kế toán mạnh hay yếu?
*   **Lưu chuyển tiền tệ**: Phân tích dòng tiền từ hoạt động kinh doanh, chi phí vốn (CapEx) và dòng tiền tự do (FCF). Công ty có tạo ra FCF dương đều đặn không?

### 3. Định giá (Valuation)
*   **Phân tích bội số**: So sánh các tỷ số P/E, P/S, P/B và EV/EBITDA hiện tại so với:
    *   Mức trung bình lịch sử 5 năm của chính nó.
    *   Mức trung bình của ngành.
    *   Top 3 đối thủ cạnh tranh trực tiếp.
*   **Kết luận**: Đưa ra nhận định cổ phiếu đang bị định giá cao, định giá thấp hay định giá hợp lý.

### 4. Mô hình Kinh doanh & Lợi thế Cạnh tranh (Business Model & Economic Moat)
*   Các mảng kinh doanh cốt lõi đóng góp chính vào doanh thu.
*   Lợi thế cạnh tranh (Moat): Xác định các nguồn lợi thế (thương hiệu, chi phí thấp, v.v.) và độ bền vững của lợi thế này.

### 5. Chiến lược Tăng trưởng & Triển vọng Tương lai (Growth Strategy & Future Outlook)
*   Động lực tăng trưởng: Xác định các xúc tác chính (mở rộng công suất, sản phẩm mới).
*   Cơ hội thị trường: Quy mô thị trường (TAM) và khả năng giành thị phần.

### 6. Ban Điều hành & Quản trị Doanh nghiệp (Management & Governance)
*   Sơ lược về CEO và ban lãnh đạo.
*   Phân bổ nguồn vốn: Đánh giá chính sách cổ tức, mua lại cổ phiếu và M&A.
*   Tỷ lệ sở hữu của ban lãnh đạo (insider ownership).

### 7. Phân tích Rủi ro (Risk Analysis)
*   Top 3 rủi ro đặc thù của doanh nghiệp.
*   Top 3 rủi ro hệ thống (vĩ mô, chính sách, đối thủ).

### 8. Khuyến nghị Cuối cùng (Final Recommendation)
*   Xếp hạng MUA/NẮM GIỮ/BÁN kèm theo tóm tắt lập luận ngắn gọn dựa trên sự cân biến giữa cơ hội và rủi ro ở mức giá hiện tại.
