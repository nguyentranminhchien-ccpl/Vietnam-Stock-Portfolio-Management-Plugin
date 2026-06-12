import os
import pandas as pd
import numpy as np

def get_clean_ticker(ticker):
    """Strip exchange suffix like .VN, .HN, .UPCOM"""
    return ticker.split('.')[0]

def get_latest_price_vnstock(ticker):
    """
    Fetch the latest close price using vnstock v4.
    Returns price in VND.
    """
    try:
        from vnstock import Market
        clean_ticker = get_clean_ticker(ticker)
        m = Market()
        df = m.equity(clean_ticker).ohlcv(length=1, interval='1D')
        if not df.empty:
            # vnstock price is divided by 1000, convert back to VND
            close_price = float(df.iloc[-1]['close']) * 1000.0
            return close_price
    except Exception as e:
        print(f"[-] vnstock failed to fetch price for {ticker}: {e}")
    return None

def get_ta_data_vnstock(ticker):
    """
    Calculate SMA20, SMA50, RSI14, and MACD indicators using vnstock market data.
    Returns (latest_day_dict, yesterday_dict).
    """
    try:
        from vnstock import Market
        clean_ticker = get_clean_ticker(ticker)
        m = Market()
        df = m.equity(clean_ticker).ohlcv(length=120, interval='1D')
        
        if df.empty or len(df) < 50:
            return None
            
        # Ensure correct column types
        df['close'] = df['close'].astype(float)
        
        # Calculate SMAs
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_50'] = df['close'].rolling(50).mean()
        
        # Calculate RSI 14
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        
        rs = avg_gain / avg_loss
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        # Calculate MACD (12, 26, 9)
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['histogram'] = df['macd'] - df['signal']
        
        # Multiply prices by 1000 to convert to VND
        price_cols = ['open', 'high', 'low', 'close', 'sma_20', 'sma_50']
        for col in price_cols:
            if col in df.columns:
                df[col] = df[col] * 1000.0
                
        # Fill NaNs with None so they are JSON friendly
        df = df.replace({np.nan: None})
        
        # Get latest two days
        latest = df.iloc[-1].to_dict()
        yesterday = df.iloc[-2].to_dict()
        
        return latest, yesterday
    except Exception as e:
        print(f"[-] vnstock failed to run TA scan for {ticker}: {e}")
    return None

def generate_fundamental_report_vnstock(ticker):
    """
    Generate a fundamental report using vnstock v4 Fundamental data.
    Saves to reports/{ticker}_report.md.
    """
    try:
        from vnstock import Fundamental
        clean_ticker = get_clean_ticker(ticker)
        f = Fundamental()
        
        print(f"Fetching financial ratios for {ticker} using vnstock...")
        df_ratios = f.equity(clean_ticker).ratio(period='year')
        
        # Transpose or select the key ratios
        # Ratios DataFrame structure has 'item_id' and years as columns (e.g. '2024', '2023', etc.)
        if df_ratios.empty:
            return None
            
        # Find available year columns (numeric strings)
        year_cols = [col for col in df_ratios.columns if col.isdigit()]
        year_cols = sorted(year_cols, reverse=True) # Newest first
        
        # Pivot ratios for easier lookup
        ratios_dict = {}
        for _, row in df_ratios.iterrows():
            item_id = row['item_id']
            item_name = row['item']
            ratios_dict[item_id] = {
                'name': item_name,
                'values': {yr: row.get(yr, None) for yr in year_cols}
            }
            
        # Helper to get ratio value safely
        def get_ratio_str(item_id, year):
            if item_id in ratios_dict and year in ratios_dict[item_id]['values']:
                val = ratios_dict[item_id]['values'][year]
                if val is None or pd.isna(val):
                    return "N/A"
                # If ratio is margin or roe/roa, vnstock already returns it in percent format
                if item_id in ['roe', 'roa', 'gross_margin', 'net_margin']:
                    return f"{val:.2f}%"
                if item_id in ['pe', 'pb', 'ps', 'ev_ebitda', 'short_term_ratio', 'quick_ratio', 'debt_to_equity']:
                    return f"{val:.2f}x" if 'ratio' in item_id or 'short_term' in item_id or 'quick' in item_id or 'debt' in item_id else f"{val:.2f}"
                return f"{val:,.2f}"
            return "N/A"
            
        # Build Report Markdown Content
        md = []
        md.append(f"# Báo cáo Phân tích Cơ bản: {ticker} (Vnstock Fallback)")
        md.append(f"\n*Báo cáo được tạo tự động bởi mô-đun vnstock do tài khoản Mozyfin hết lượt truy vấn.*")
        md.append(f"\n## 1. Định giá & Chỉ số Tài chính (Lịch sử {len(year_cols)} năm)\n")
        
        # Create table headers
        headers = ["Chỉ tiêu tài chính / Tỷ số"] + year_cols
        md.append("| " + " | ".join(headers) + " |")
        md.append("| " + " | ".join(["---"] * len(headers)) + " |")
        
        # Add key metrics to table
        metrics_to_show = [
            ('pe', 'Hệ số P/E'),
            ('pb', 'Hệ số P/B'),
            ('ps', 'Hệ số P/S'),
            ('ev_ebitda', 'Chỉ số EV/EBITDA'),
            ('roe', 'Hiệu suất sinh lời trên vốn chủ sở hữu (ROE)'),
            ('roa', 'Hiệu suất sinh lời trên tổng tài sản (ROA)'),
            ('gross_margin', 'Biên lợi nhuận gộp'),
            ('net_margin', 'Biên lợi nhuận ròng'),
            ('debt_to_equity', 'Tỷ lệ Nợ / Vốn chủ sở hữu (D/E)'),
            ('short_term_ratio', 'Tỷ số thanh toán hiện hành (Current Ratio)'),
            ('quick_ratio', 'Tỷ số thanh toán nhanh (Quick Ratio)')
        ]
        
        for item_id, label in metrics_to_show:
            row_vals = [label]
            for yr in year_cols:
                row_vals.append(get_ratio_str(item_id, yr))
            md.append("| " + " | ".join(row_vals) + " |")
            
        md.append("\n## 2. Nhận định Hiệu quả Tài chính\n")
        
        # Add basic logical insights based on ratio values of latest year
        latest_yr = year_cols[0] if year_cols else None
        if latest_yr:
            pe_val = ratios_dict.get('pe', {}).get('values', {}).get(latest_yr, None)
            roe_val = ratios_dict.get('roe', {}).get('values', {}).get(latest_yr, None)
            debt_val = ratios_dict.get('debt_to_equity', {}).get('values', {}).get(latest_yr, None)
            current_ratio = ratios_dict.get('short_term_ratio', {}).get('values', {}).get(latest_yr, None)
            net_margin = ratios_dict.get('net_margin', {}).get('values', {}).get(latest_yr, None)
            
            md.append(f"Dựa trên dữ liệu năm tài chính gần nhất **{latest_yr}**:")
            
            # Insights
            insights = []
            if roe_val is not None and not pd.isna(roe_val):
                if roe_val > 15.0:
                    insights.append(f"- **Khả năng sinh lời cao:** Chỉ số ROE đạt **{roe_val:.2f}%** cho thấy hiệu quả sử dụng vốn tuyệt vời, đạt tiêu chuẩn đầu tư giá trị (>15%).")
                else:
                    insights.append(f"- **Khả năng sinh lời trung bình/thấp:** Chỉ số ROE đạt **{roe_val:.2f}%**, thấp hơn mức tiêu chuẩn 15%.")
                    
            if debt_val is not None and not pd.isna(debt_val):
                if debt_val < 1.0:
                    insights.append(f"- **Cơ cấu nợ an toàn:** Tỷ lệ Nợ/Vốn chủ sở hữu đạt **{debt_val:.2f}x** ở mức thấp và an toàn (dưới 1.0x), thể hiện tình hình tài chính vững chắc.")
                else:
                    insights.append(f"- **Đòn bẩy tài chính cao:** Tỷ lệ Nợ/Vốn chủ sở hữu đạt **{debt_val:.2f}x**, tiềm ẩn rủi ro nợ vay.")
                    
            if current_ratio is not None and not pd.isna(current_ratio):
                if current_ratio > 1.5:
                    insights.append(f"- **Thanh khoản lành mạnh:** Tỷ số thanh toán hiện hành đạt **{current_ratio:.2f}x** cho thấy khả năng thanh toán ngắn hạn tốt.")
                else:
                    insights.append(f"- **Lưu ý thanh khoản:** Tỷ số thanh toán hiện hành đạt **{current_ratio:.2f}x** cho thấy vốn lưu động tương đối eo hẹp.")
                    
            if pe_val is not None and not pd.isna(pe_val):
                if pe_val < 12.0 and pe_val > 0:
                    insights.append(f"- **Định giá hấp dẫn:** Cổ phiếu giao dịch ở mức P/E **{pe_val:.1f}x**, tương đối rẻ đối với một doanh nghiệp tốt.")
                elif pe_val >= 12.0:
                    insights.append(f"- **Định giá cao:** Cổ phiếu giao dịch ở mức P/E **{pe_val:.1f}x**, kỳ vọng tăng trưởng cao hoặc đang định giá ở mức cao.")
            
            md.append("\n".join(insights))
            
        md.append("\n## 3. Kết luận & Khuyến nghị\n")
        md.append("Cổ phiếu này nên được đánh giá dựa trên các trụ cột giá trị cốt lõi:")
        md.append("1. **Bội số định giá**: So sánh mức P/E và P/B hiện tại với mức trung bình lịch sử.")
        md.append("2. **Sức khỏe tài chính**: Khả năng thanh toán tốt và tỷ lệ nợ/vốn chủ sở hữu thấp mang lại sự an toàn.")
        md.append("3. **Khả năng sinh lời**: Kiểm tra biên lợi nhuận ròng và chỉ số ROE duy trì qua nhiều năm.")
        md.append("\n*Lưu ý: Báo cáo dự phòng này chỉ cung cấp các chỉ số tài chính định lượng. Các phân tích định tính như lợi thế cạnh tranh (moat), cơ cấu mảng kinh doanh và triển vọng tăng trưởng nên được tham chiếu chéo với các công bố thông tin gần nhất của doanh nghiệp.*")
        
        # Save to file
        reports_dir = 'reports'
        if not os.path.exists(reports_dir):
            os.makedirs(reports_dir)
            
        report_path = os.path.join(reports_dir, f"{ticker}_report.md")
        with open(report_path, 'w', encoding='utf-8') as f_out:
            f_out.write("\n".join(md))
            
        print(f"[+] Successfully generated fallback fundamental report for {ticker} at {report_path}")
        return report_path
    except Exception as e:
        print(f"[-] Failed to generate fallback fundamental report for {ticker}: {e}")
    return None

if __name__ == '__main__':
    # Test fallback price
    print("Testing GMD.VN fallback price:")
    print(get_latest_price_vnstock("GMD.VN"))
    
    # Test fallback TA
    print("\nTesting SHS.VN fallback TA:")
    ta = get_ta_data_vnstock("SHS.VN")
    if ta:
        print("Latest Close:", ta[0]['close'], "SMA20:", ta[0]['sma_20'], "RSI:", ta[0]['rsi_14'])
        
    # Test fallback report
    print("\nTesting VEA.VN fallback report:")
    generate_fundamental_report_vnstock("VEA.VN")
