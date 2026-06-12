import os
import json
import subprocess

def run_mozyfin_command(cmd_args):
    """Run a mozyfin command and return stdout as string."""
    try:
        cmd = ["mozyfin"] + cmd_args
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return f"Error running mozyfin: {result.stderr.strip()}"
    except Exception as e:
        return f"Exception: {e}"

def generate_analyst_report(ticker):
    """
    Generate a deep fundamental research report for the ticker
    using mozyfin ask and doc, structured according to the vietnam-equity-analyst skill.
    """
    print(f"\nGenerating fundamental analyst report for {ticker} using Mozyfin AI agent...")
    
    # Construct a detailed prompt based on the user's Prompt.docx template
    # Determine peers based on ticker
    peers_str = ""
    if "DPM" in ticker:
        peers_str = "DCM.VN, BFC.VN"
    elif "VEA" in ticker:
        peers_str = "TMT.VN, HTL.VN, HAX.VN" # Auto peers
    else:
        peers_str = "its direct industry competitors"
        
    prompt = f"""Hãy đóng vai trò là một nhà phân tích nghiên cứu cổ phiếu cấp cao. Hãy viết một báo cáo phân tích chi tiết, khách quan và dựa trên dữ liệu cho cổ phiếu {ticker} bằng TIẾNG VIỆT, sử dụng dữ liệu tài chính trong 5 năm tài chính gần nhất và 12 tháng gần nhất (TTM).
Cấu trúc báo cáo bắt buộc bao gồm các phần sau:

1. Tóm tắt dự án (Executive Summary):
   - Tổng quan ngắn gọn về hoạt động kinh doanh của công ty.
   - Luận điểm đầu tư trong 2-3 câu: Nên Mua, Nắm giữ hay Bán ở mức định giá hiện tại?
   - Các động lực tăng trưởng tích cực và rủi ro lớn nhất.

2. Hiệu quả Tài chính & Sức khỏe Doanh nghiệp (Financial Performance & Health):
   - Báo cáo kết quả kinh doanh: Phân tích tăng trưởng doanh thu, biên lợi nhuận gộp, biên lợi nhuận hoạt động và xu hướng biên lợi nhuận sau thuế trong 5 năm qua + TTM.
   - Bảng cân đối kế toán: Đánh giá mức độ nợ, tỷ lệ nợ/vốn chủ sở hữu, tỷ số thanh toán hiện hành và lượng tiền mặt. Bảng cân đối kế toán mạnh hay yếu?
   - Lưu chuyển tiền tệ: Phân tích dòng tiền từ hoạt động kinh doanh, chi phí vốn (CapEx) và dòng tiền tự do (FCF). Công ty có tạo ra FCF dương đều đặn không?

3. Định giá (Valuation):
   - Phân tích bội số: So sánh các tỷ số P/E, P/S, P/B và EV/EBITDA hiện tại so với:
     + Mức trung bình lịch sử 5 năm của chính nó.
     + Mức trung bình của ngành.
     + Top 3 đối thủ cạnh tranh trực tiếp ({peers_str}).
   - Kết luận: Đưa ra nhận định cổ phiếu đang bị định giá cao, định giá thấp hay định giá hợp lý.

4. Mô hình Kinh doanh & Lợi thế Cạnh tranh (Business Model & Economic Moat):
   - Các mảng kinh doanh cốt lõi đóng góp chính vào doanh thu.
   - Lợi thế cạnh tranh (Moat): Xác định các nguồn lợi thế (thương hiệu, chi phí thấp, v.v.) và độ bền vững của lợi thế này.

5. Chiến lược Tăng trưởng & Triển vọng Tương lai (Growth Strategy & Future Outlook):
   - Động lực tăng trưởng: Xác định các xúc tác chính (mở rộng công suất, sản phẩm mới).
   - Cơ hội thị trường: Quy mô thị trường (TAM) và khả năng giành thị phần.

6. Ban Điều hành & Quản trị Doanh nghiệp (Management & Governance):
   - Sơ lược về CEO và ban lãnh đạo.
   - Phân bổ nguồn vốn: Đánh giá chính sách cổ tức, mua lại cổ phiếu và M&A.
   - Tỷ lệ sở hữu của ban lãnh đạo (insider ownership).

7. Phân tích Rủi ro (Risk Analysis):
   - Top 3 rủi ro đặc thù của doanh nghiệp.
   - Top 3 rủi ro hệ thống (vĩ mô, chính sách, đối thủ).

8. Khuyến nghị Cuối cùng (Final Recommendation):
   - Xếp hạng MUA/NẮM GIỮ/BÁN kèm theo tóm tắt lập luận ngắn gọn dựa trên sự cân biến giữa cơ hội và rủi ro ở mức giá hiện tại.
"""

    # Call mozyfin ask to generate the report
    report_content = run_mozyfin_command(["ask", prompt, "--timeout", "400"])
    
    # Check if the output indicates failure
    is_error = "Error running mozyfin" in report_content or "Insufficient credits" in report_content or "Exception" in report_content
    
    if is_error:
        print(f"[!] Mozyfin report generation failed for {ticker}. Falling back to vnstock...")
        try:
            from vnstock_fallback import generate_fundamental_report_vnstock
            fallback_path = generate_fundamental_report_vnstock(ticker)
            if fallback_path and os.path.exists(fallback_path):
                return fallback_path
        except Exception as e:
            print(f"[-] Fallback to vnstock report failed: {e}")
    
    # Save the report
    reports_dir = 'reports'
    if not os.path.exists(reports_dir):
        os.makedirs(reports_dir)
        
    report_path = os.path.join(reports_dir, f"{ticker}_report.md")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
        
    print(f"[+] Saved analyst report to {report_path}")
    return report_path

def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    portfolio_file = 'portfolio.json'
    if not os.path.exists(portfolio_file):
        print(f"Error: {portfolio_file} not found.")
        return
        
    with open(portfolio_file, 'r', encoding='utf-8') as f:
        portfolio = json.load(f)
        
    holdings = portfolio.get('holdings', [])
    lt_holdings = [h for h in holdings if h['allocation'] == 'long-term']
    
    if not lt_holdings:
        print("No long-term holdings found in portfolio.json.")
        return
        
    print("\n" + "="*80)
    print("                      LONG-TERM VALUE INVESTING REPORT")
    print("="*80)
    
    for holding in lt_holdings:
        ticker = holding['ticker']
        basis_price = holding['basis_price']
        
        # Check if report already exists and is less than 7 days old
        reports_dir = 'reports'
        report_path = os.path.join(reports_dir, f"{ticker}_report.md")
        
        is_recent = False
        if os.path.exists(report_path):
            import time
            file_age_seconds = time.time() - os.path.getmtime(report_path)
            is_recent = file_age_seconds < (7 * 24 * 3600)  # 7 days in seconds
            
        if is_recent:
            print(f"[+] Báo cáo phân tích cho {ticker} đã tồn tại (dưới 1 tuần) tại {report_path}. Bỏ qua để tiết kiệm token.")
            if 'current_price' in holding:
                close = holding['current_price']
                pnl_pct = holding.get('pnl_pct', 0.0)
                print(f"    Giá hiện tại: {close:,.0f} VND (Giá vốn: {basis_price:,.0f} VND, PnL: {pnl_pct:+.2f}%)")
        else:
            if os.path.exists(report_path):
                print(f"[!] Báo cáo cho {ticker} đã cũ hơn 1 tuần. Đang cập nhật lại...")
            generate_analyst_report(ticker)
            
        print("-" * 50)
    print("="*80 + "\n")

if __name__ == '__main__':
    main()
