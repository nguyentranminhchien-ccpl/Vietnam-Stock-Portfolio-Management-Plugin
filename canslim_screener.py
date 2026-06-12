import os
import sys
import json
import csv
import argparse
import tempfile
import subprocess
from datetime import datetime
import pandas as pd
import numpy as np

# Reconfigure output to UTF-8 to prevent encoding crashes in Windows console
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

def get_clean_ticker(ticker):
    return ticker.split('.')[0]

def make_json_serializable(data):
    """Recursively convert numpy/pandas data types to native python types."""
    if isinstance(data, dict):
        return {k: make_json_serializable(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [make_json_serializable(v) for v in data]
    elif isinstance(data, (np.integer, np.int64)):
        return int(data)
    elif isinstance(data, (np.floating, np.float64)):
        return float(data)
    elif isinstance(data, np.ndarray):
        return make_json_serializable(data.tolist())
    elif isinstance(data, pd.Timestamp):
        return data.isoformat()
    elif isinstance(data, (int, float, str, bool)) or data is None:
        return data
    else:
        try:
            json.dumps(data)
            return data
        except TypeError:
            return str(data)

def fetch_index_history(length=260):
    """Fetch VNINDEX ohlcv data using vnstock."""
    try:
        from vnstock import Market
        m = Market()
        df = m.index('VNINDEX').ohlcv(length=length)
        if not df.empty:
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            return df
    except Exception as e:
        print(f"[-] Không thể lấy dữ liệu VNINDEX: {e}")
    return None

def fetch_stock_history(ticker, length=260):
    """Fetch stock ohlcv data from mozyfin first, then fallback to vnstock."""
    clean_ticker = get_clean_ticker(ticker)
    
    # Try mozyfin first
    fd, temp_path = tempfile.mkstemp(suffix='.csv')
    os.close(fd)
    try:
        cmd = ["mozyfin", "ohlcv", f"{clean_ticker}.VN", "--limit", str(length), "--csv", temp_path]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            df = pd.read_csv(temp_path)
            if not df.empty:
                df = df.iloc[::-1].reset_index(drop=True)
                df['close'] = df['close'].astype(float)
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                df['open'] = df['open'].astype(float)
                df['volume'] = df['volume'].astype(float)
                return df
    except Exception as e:
        print(f"[-] Mozyfin failed to fetch history for {ticker}: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    # Fallback to vnstock
    try:
        from vnstock import Market
        m = Market()
        df = m.equity(clean_ticker).ohlcv(length=length, interval='1D')
        if not df.empty:
            df['close'] = df['close'].astype(float) * 1000.0
            df['open'] = df['open'].astype(float) * 1000.0
            df['high'] = df['high'].astype(float) * 1000.0
            df['low'] = df['low'].astype(float) * 1000.0
            df['volume'] = df['volume'].astype(float)
            return df
    except Exception as e:
        print(f"[-] vnstock failed to fetch history for {ticker}: {e}")
    return None

def fetch_financials_mozyfin(ticker):
    """Fetch financials using mozyfin."""
    clean_ticker = get_clean_ticker(ticker)
    fd, temp_path = tempfile.mkstemp(suffix='.csv')
    os.close(fd)
    try:
        cmd = ["mozyfin", "financials", f"{clean_ticker}.VN", "--csv", temp_path]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            df = pd.read_csv(temp_path)
            return df
    except Exception as e:
        print(f"[-] Mozyfin failed to fetch financials for {ticker}: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    return None

def fetch_financials_vnstock(ticker):
    """Fetch financials using vnstock as fallback."""
    clean_ticker = get_clean_ticker(ticker)
    try:
        from vnstock import Fundamental
        f = Fundamental()
        df_q = f.equity(clean_ticker).income_statement(period='quarter')
        df_a = f.equity(clean_ticker).income_statement(period='year')
        df_r = f.equity(clean_ticker).ratio(period='year')
        return {"quarterly": df_q, "annual": df_a, "ratios": df_r}
    except Exception as e:
        print(f"[-] vnstock failed to fetch financials for {ticker}: {e}")
    return None

def fetch_ownership_vnstock(ticker):
    """Fetch shareholder structure from vnstock."""
    clean_ticker = get_clean_ticker(ticker)
    try:
        from vnstock import Reference
        r = Reference()
        df = r.company(clean_ticker).ownership()
        return df
    except Exception as e:
        print(f"[-] vnstock failed to fetch ownership for {ticker}: {e}")
    return None

def calculate_c_component(mozy_df, vn_data):
    """
    Calculate Current Quarterly Earnings (C).
    Requires YoY Net Profit growth >= 20% and YoY Revenue growth >= 20%.
    """
    score = 30
    details = "Không đủ dữ liệu quý"
    q_growth_eps = 0.0
    q_growth_rev = 0.0
    
    if mozy_df is not None and not mozy_df.empty:
        df_is = mozy_df[mozy_df['type'] == 'INCOME_STATEMENT'].copy()
        df_is = df_is.sort_values(by=['year', 'quarter']).reset_index(drop=True)
        
        if len(df_is) >= 5:
            latest = df_is.iloc[-1]
            latest_yr = int(latest['year'])
            latest_q = int(latest['quarter'])
            
            prev_yoy = df_is[(df_is['year'] == (latest_yr - 1)) & (df_is['quarter'] == latest_q)]
            if not prev_yoy.empty:
                prev = prev_yoy.iloc[0]
                
                eps_latest = float(latest['profit_after_tax'])
                eps_prev = float(prev['profit_after_tax'])
                rev_latest = float(latest['net_sales'])
                rev_prev = float(prev['net_sales'])
                
                if eps_prev > 0:
                    q_growth_eps = (eps_latest - eps_prev) / eps_prev * 100
                if rev_prev > 0:
                    q_growth_rev = (rev_latest - rev_prev) / rev_prev * 100
                    
                details = f"Quý gần nhất {latest_yr}-Q{latest_q}: Lợi nhuận YoY {q_growth_eps:+.1f}%, Doanh thu YoY {q_growth_rev:+.1f}%"
                
                if q_growth_eps >= 25.0 and q_growth_rev >= 20.0:
                    score = 100
                elif q_growth_eps >= 20.0 and q_growth_rev >= 15.0:
                    score = 80
                elif q_growth_eps >= 10.0:
                    score = 60
                elif q_growth_eps < 0:
                    score = 10
                else:
                    score = 40
            else:
                details = "Không tìm thấy quý cùng kỳ năm trước từ mozyfin"
    elif vn_data is not None:
        df_q = vn_data.get("quarterly")
        if df_q is not None and not df_q.empty:
            cols = [col for col in df_q.columns if col not in ['item', 'item_id']]
            try:
                np_row = df_q[df_q['item_id'] == 'net_profit']
                rev_row = df_q[df_q['item_id'] == 'revenue']
                if np_row.empty:
                    np_row = df_q[df_q['item_id'].str.contains('profit_after_tax', na=False)]
                if rev_row.empty:
                    rev_row = df_q[df_q['item_id'].str.contains('sales', na=False)]
                
                if not np_row.empty and len(cols) >= 2:
                    np_vals = np_row.iloc[0]
                    rev_vals = rev_row.iloc[0] if not rev_row.empty else None
                    
                    sorted_periods = sorted(cols)
                    latest_p = sorted_periods[-1]
                    lyr, lq = latest_p.split('-')
                    lyr = int(lyr)
                    
                    yoy_p = f"{lyr-1}-{lq}"
                    if yoy_p in cols:
                        eps_latest = float(np_vals[latest_p])
                        eps_prev = float(np_vals[yoy_p])
                        rev_latest = float(rev_vals[latest_p]) if rev_vals is not None else 0.0
                        rev_prev = float(rev_vals[yoy_p]) if rev_vals is not None else 0.0
                        
                        if eps_prev > 0:
                            q_growth_eps = (eps_latest - eps_prev) / eps_prev * 100
                        if rev_prev > 0:
                            q_growth_rev = (rev_latest - rev_prev) / rev_prev * 100
                            
                        details = f"Quý gần nhất {latest_p}: Lợi nhuận YoY {q_growth_eps:+.1f}%, Doanh thu YoY {q_growth_rev:+.1f}%"
                        if q_growth_eps >= 25.0 and q_growth_rev >= 20.0:
                            score = 100
                        elif q_growth_eps >= 20.0:
                            score = 80
                        else:
                            score = 50
                    else:
                        prev_p = sorted_periods[-2]
                        eps_latest = float(np_vals[latest_p])
                        eps_prev = float(np_vals[prev_p])
                        if eps_prev > 0:
                            q_growth_eps = (eps_latest - eps_prev) / eps_prev * 100
                        details = f"Quý gần nhất {latest_p} so với quý trước {prev_p} (QoQ): {q_growth_eps:+.1f}% (Thiếu cùng kỳ do giới hạn vnstock)"
                        if q_growth_eps >= 15.0:
                            score = 70
                        elif q_growth_eps > 0:
                            score = 50
                        else:
                            score = 30
            except Exception as e:
                details = f"Lỗi tính toán dữ liệu quý vnstock: {e}"
                
    return score, q_growth_eps, q_growth_rev, details

def calculate_a_component(mozy_df, vn_data):
    """
    Calculate Annual Growth (A).
    Requires 3-year EPS growth > 20% and ROE >= 17%.
    """
    score = 50
    details = "Không đủ dữ liệu năm"
    annual_growth_rates = []
    avg_growth = 0.0
    latest_roe = 0.0
    
    if mozy_df is not None and not mozy_df.empty:
        df_is = mozy_df[(mozy_df['type'] == 'INCOME_STATEMENT') & (mozy_df['quarter'].isna() | (mozy_df['quarter'] == ''))].copy()
        df_bs = mozy_df[(mozy_df['type'] == 'BALANCE_SHEET') & (mozy_df['quarter'].isna() | (mozy_df['quarter'] == ''))].copy()
        
        df_is = df_is.sort_values(by='year').reset_index(drop=True)
        df_bs = df_bs.sort_values(by='year').reset_index(drop=True)
        
        if len(df_is) >= 3:
            for i in range(1, len(df_is)):
                prev_val = float(df_is.iloc[i-1]['profit_after_tax'])
                curr_val = float(df_is.iloc[i]['profit_after_tax'])
                if prev_val > 0:
                    annual_growth_rates.append((curr_val - prev_val) / prev_val * 100)
            
            if annual_growth_rates:
                avg_growth = np.mean(annual_growth_rates[-3:])
            
            if not df_is.empty and not df_bs.empty:
                latest_year = df_is.iloc[-1]['year']
                bs_match = df_bs[df_bs['year'] == latest_year]
                if not bs_match.empty:
                    eq_val = float(bs_match.iloc[0]['owner_equity'])
                    pat_val = float(df_is.iloc[-1]['profit_after_tax'])
                    if eq_val > 0:
                        latest_roe = (pat_val / eq_val) * 100
                        
            details = f"Tăng trưởng năm TB (3 năm): {avg_growth:.1f}%, ROE gần nhất: {latest_roe:.1f}%"
            
            if avg_growth >= 20.0 and latest_roe >= 17.0:
                score = 100
            elif avg_growth >= 15.0 or latest_roe >= 15.0:
                score = 80
            elif avg_growth >= 10.0 or latest_roe >= 10.0:
                score = 60
            else:
                score = 30
    elif vn_data is not None:
        df_a = vn_data.get("annual")
        df_r = vn_data.get("ratios")
        
        try:
            if df_a is not None and not df_a.empty:
                cols = [col for col in df_a.columns if col not in ['item', 'item_id']]
                sorted_years = sorted(cols)
                
                np_row = df_a[df_a['item_id'] == 'net_profit']
                if np_row.empty:
                    np_row = df_a[df_a['item_id'].str.contains('profit_after_tax', na=False)]
                
                if not np_row.empty and len(cols) >= 2:
                    np_vals = np_row.iloc[0]
                    for i in range(1, len(sorted_years)):
                        prev_val = float(np_vals[sorted_years[i-1]])
                        curr_val = float(np_vals[sorted_years[i]])
                        if prev_val > 0:
                            annual_growth_rates.append((curr_val - prev_val) / prev_val * 100)
                    if annual_growth_rates:
                        avg_growth = np.mean(annual_growth_rates[-3:])
            
            if df_r is not None and not df_r.empty:
                roe_row = df_r[df_r['item_id'] == 'roe']
                if not roe_row.empty:
                    cols_r = [col for col in df_r.columns if col not in ['item', 'item_id']]
                    sorted_r_years = sorted(cols_r)
                    latest_r_yr = sorted_r_years[-1]
                    latest_roe = float(roe_row.iloc[0][latest_r_yr])
            
            details = f"Tăng trưởng năm TB: {avg_growth:.1f}%, ROE gần nhất: {latest_roe:.1f}%"
            if avg_growth >= 20.0 and latest_roe >= 17.0:
                score = 100
            elif avg_growth >= 15.0 or latest_roe >= 15.0:
                score = 80
            else:
                score = 50
        except Exception as e:
            details = f"Lỗi tính toán dữ liệu năm vnstock: {e}"
            
    return score, avg_growth, latest_roe, details

def calculate_n_component(df_prices):
    """
    Calculate Newness (N).
    Check distance from 52-week high (260 trading days) and recent breakout.
    """
    if df_prices is None or df_prices.empty:
        return 0, 0.0, "Không có dữ liệu giá"
        
    close = df_prices.iloc[-1]['close']
    high_52w = df_prices['high'].max()
    
    dist_from_high_pct = (high_52w - close) / high_52w * 100
    is_breakout = dist_from_high_pct <= 3.0
    
    details = f"Cách đỉnh 52 tuần: {dist_from_high_pct:.1f}% (Giá: {close:,.0f} VND vs Đỉnh: {high_52w:,.0f} VND)"
    if is_breakout:
        score = 100
        details += " [Đột phá vượt đỉnh / Gần đỉnh]"
    elif dist_from_high_pct <= 10.0:
        score = 85
    elif dist_from_high_pct <= 15.0:
        score = 70
    elif dist_from_high_pct <= 25.0:
        score = 40
    else:
        score = 10
        
    return score, dist_from_high_pct, details

def calculate_s_component(df_prices):
    """
    Calculate Supply and Demand (S).
    Checks average volume and Up/Down Volume Ratio.
    """
    if df_prices is None or df_prices.empty:
        return 0, 0.0, 0.0, "Không có dữ liệu giao dịch"
        
    avg_vol_50d = df_prices['volume'].rolling(50).mean().iloc[-1]
    
    recent = df_prices.iloc[-50:]
    up_days = recent[recent['close'] > recent['close'].shift(1)]
    down_days = recent[recent['close'] < recent['close'].shift(1)]
    
    total_up_vol = up_days['volume'].sum()
    total_down_vol = down_days['volume'].sum()
    
    up_down_ratio = 1.0
    if total_down_vol > 0:
        up_down_ratio = total_up_vol / total_down_vol
        
    details = f"Volume TB 50 phiên: {avg_vol_50d:,.0f} CP, Tỷ lệ Up/Down Volume: {up_down_ratio:.2f}"
    
    if avg_vol_50d < 50000:
        score = 20
        details += " [Thanh khoản quá yếu]"
    else:
        if up_down_ratio >= 1.5:
            score = 100
        elif up_down_ratio >= 1.2:
            score = 90
        elif up_down_ratio >= 1.0:
            score = 75
        elif up_down_ratio >= 0.8:
            score = 50
        else:
            score = 30
            
    return score, avg_vol_50d, up_down_ratio, details

def calculate_l_component(df_stock, df_index):
    """
    Calculate Leadership / Relative Strength (L).
    Weighted RS vs VNINDEX over 3m (60d), 6m (120d), 12m (250d).
    """
    if df_stock is None or df_stock.empty or df_index is None or df_index.empty:
        return 50, 0.0, "Không đủ dữ liệu so sánh RS"
        
    def get_period_return(df, days):
        if len(df) < days:
            days = len(df)
        close_now = df.iloc[-1]['close']
        close_then = df.iloc[-days]['close']
        return (close_now - close_then) / close_then * 100
        
    stock_3m = get_period_return(df_stock, 60)
    stock_6m = get_period_return(df_stock, 120)
    stock_12m = get_period_return(df_stock, 250)
    
    idx_3m = get_period_return(df_index, 60)
    idx_6m = get_period_return(df_index, 120)
    idx_12m = get_period_return(df_index, 250)
    
    rel_3m = stock_3m - idx_3m
    rel_6m = stock_6m - idx_6m
    rel_12m = stock_12m - idx_12m
    
    weighted_relative_return = 0.40 * rel_3m + 0.30 * rel_6m + 0.30 * rel_12m
    
    details = f"Hiệu suất vượt trội VNINDEX 3m/6m/12m: {rel_3m:+.1f}%/{rel_6m:+.1f}%/{rel_12m:+.1f}%"
    
    if weighted_relative_return >= 20.0:
        score = 100
        details += " [Dẫn đầu thị trường (Leader)]"
    elif weighted_relative_return >= 10.0:
        score = 85
    elif weighted_relative_return >= 0.0:
        score = 70
    elif weighted_relative_return >= -10.0:
        score = 50
    else:
        score = 30
        details += " [Yếu hơn thị trường (Laggard)]"
        
    return score, weighted_relative_return, details

def calculate_i_component(ownership_df):
    """
    Calculate Institutional Sponsorship (I).
    Checks institutional ownership percentage.
    """
    score = 50
    total_inst_ownership = 0.0
    details = "Không có dữ liệu sở hữu tổ chức"
    
    if ownership_df is not None and not ownership_df.empty:
        try:
            inst_rows = ownership_df[
                ownership_df['owner_type'].str.contains('tổ chức|nước ngoài|SCIC|Nhà nước', case=False, na=False)
            ]
            total_inst_ownership = inst_rows['ownership_percentage'].sum()
            
            details = f"Tổng sở hữu của tổ chức/nước ngoài: {total_inst_ownership:.1f}%"
            if total_inst_ownership >= 35.0:
                score = 100
                details += " [Đồng hành dòng tiền lớn]"
            elif total_inst_ownership >= 20.0:
                score = 85
            elif total_inst_ownership >= 10.0:
                score = 70
            elif total_inst_ownership > 0.0:
                score = 50
            else:
                score = 30
        except Exception as e:
            details = f"Lỗi tính toán sở hữu: {e}"
            
    return score, total_inst_ownership, details

def calculate_m_component(df_index):
    """
    Calculate Market Direction (M).
    VNINDEX vs 50-day EMA and 200-day SMA.
    """
    if df_index is None or df_index.empty:
        return 50, "Đang đi ngang", "Không có dữ liệu VNINDEX"
        
    close = df_index.iloc[-1]['close']
    ema_50 = df_index['close'].ewm(span=50, adjust=False).mean().iloc[-1]
    sma_200 = df_index['close'].rolling(200).mean().iloc[-1]
    
    is_above_ema50 = close > ema_50
    is_above_sma200 = close > sma_200
    
    if is_above_ema50 and is_above_sma200:
        score = 100
        trend = "Uptrend mạnh"
        details = f"VN-Index ({close:,.1f}) nằm trên EMA 50 ({ema_50:,.1f}) và SMA 200 ({sma_200:,.1f}) [Xu hướng tăng xác nhận]"
    elif is_above_sma200:
        score = 80
        trend = "Uptrend yếu / Tích lũy"
        details = f"VN-Index ({close:,.1f}) nằm trên SMA 200 nhưng dưới EMA 50 [Thị trường tích lũy]"
    else:
        score = 0
        trend = "Downtrend (Thị trường Gấu)"
        details = f"VN-Index ({close:,.1f}) nằm dưới SMA 200 ({sma_200:,.1f}) [CẢNH BÁO: RỦI RO LỚN]"
        
    return score, trend, details

def run_canslim_screener(ticker, df_index):
    """Run CANSLIM analysis for a single stock."""
    try:
        df_stock = fetch_stock_history(ticker, length=260)
        if df_stock is None or df_stock.empty:
            print(f"[-] Bỏ qua {ticker} do không lấy được dữ liệu giá.")
            return None
            
        mozy_df = fetch_financials_mozyfin(ticker)
        vn_data = None
        if mozy_df is None or mozy_df.empty:
            print(f"  Fetching financials from vnstock for {ticker}...")
            vn_data = fetch_financials_vnstock(ticker)
            
        ownership_df = fetch_ownership_vnstock(ticker)
        
        c_score, q_growth, q_rev, c_details = calculate_c_component(mozy_df, vn_data)
        a_score, a_growth, roe, a_details = calculate_a_component(mozy_df, vn_data)
        n_score, dist_high, n_details = calculate_n_component(df_stock)
        s_score, avg_vol, up_down_ratio, s_details = calculate_s_component(df_stock)
        l_score, weighted_rs, l_details = calculate_l_component(df_stock, df_index)
        i_score, inst_own, i_details = calculate_i_component(ownership_df)
        m_score, market_trend, m_details = calculate_m_component(df_index)
        
        composite_score = (
            c_score * 0.15 +
            a_score * 0.20 +
            n_score * 0.15 +
            s_score * 0.15 +
            l_score * 0.20 +
            i_score * 0.10 +
            m_score * 0.05
        )
        
        if composite_score >= 90.0:
            rating = "Exceptional+ (Xuất sắc+)"
            rec = "MUA ĐỊNH VỊ THẾ / THÊM VÀO DANH MỤC LỚN"
        elif composite_score >= 80.0:
            rating = "Exceptional (Xuất sắc)"
            rec = "MUA MẠNH KHI ĐỘT PHÁ"
        elif composite_score >= 70.0:
            rating = "Strong (Khỏe)"
            rec = "THEO DÕI MUA Ở NHỊP PULLBACK"
        elif composite_score >= 60.0:
            rating = "Above Average (Khá)"
            rec = "QUAN SÁT THÊM"
        else:
            rating = "Average/Weak (Trung bình/Yếu)"
            rec = "BỎ QUA"
            
        if m_score == 0:
            rec = "CẢNH BÁO THỊ TRƯỜNG GẤU - KHÔNG MỞ MUA MỚI / NẮM GIỮ TIỀN MẶT"
            
        return {
            "ticker": ticker,
            "current_price": df_stock.iloc[-1]['close'],
            "composite_score": composite_score,
            "rating": rating,
            "recommendation": rec,
            "components": {
                "C": {"score": c_score, "details": c_details, "growth": q_growth, "rev_growth": q_rev},
                "A": {"score": a_score, "details": a_details, "growth": a_growth, "roe": roe},
                "N": {"score": n_score, "details": n_details, "distance_high": dist_high},
                "S": {"score": s_score, "details": s_details, "avg_volume": avg_vol, "up_down_ratio": up_down_ratio},
                "L": {"score": l_score, "details": l_details, "weighted_rs": weighted_rs},
                "I": {"score": i_score, "details": i_details, "ownership_pct": inst_own},
                "M": {"score": m_score, "details": m_details, "trend": market_trend}
            }
        }
    except Exception as e:
        print(f"[-] Lỗi phân tích CANSLIM cho {ticker}: {e}")
    return None

def main():
    parser = argparse.ArgumentParser(description="CANSLIM Stock Screener - Vietnam Equity")
    parser.add_argument("--universe", nargs="+", help="Custom stock list (e.g. FPT.VN HPG.VN)")
    parser.add_argument("--top", type=int, default=10, help="Top N stocks in final report")
    parser.add_argument("--output-dir", default="reports", help="Reports output directory")
    args = parser.parse_args()
    
    print("\n" + "="*85)
    print("                  BỘ LỌC CỔ PHIẾU TĂNG TRƯỞNG CANSLIM - VIỆT NAM")
    print("="*85)
    
    print("Đang lấy thông tin thị trường chung VNINDEX...")
    df_index = fetch_index_history(260)
    if df_index is None:
        print("[-] Lỗi: Không thể lấy dữ liệu VNINDEX. Dừng thực thi.")
        return
        
    m_score, m_trend, m_details = calculate_m_component(df_index)
    print(f"  Xu hướng VNINDEX: {m_trend} (Giá đóng cửa: {df_index.iloc[-1]['close']:,.2f})")
    print(f"  Chi tiết: {m_details}")
    if m_score == 0:
        print("⚠️ CẢNH BÁO: THỊ TRƯỜNG ĐANG TRONG DOWNTREND. CÁC TÍN HIỆU CANSLIM CÓ THỂ BỊ NHIỄU.")
        
    tickers = ["DPM.VN", "SHS.VN", "VEA.VN", "GMD.VN", "FPT.VN", "HPG.VN", "VNM.VN", "SSI.VN"]
    if args.universe:
        tickers = args.universe
        
    portfolio_file = 'portfolio.json'
    if not args.universe and os.path.exists(portfolio_file):
        try:
            with open(portfolio_file, 'r', encoding='utf-8') as f:
                portfolio = json.load(f)
                for h in portfolio.get('holdings', []):
                    if h['ticker'] not in tickers:
                        tickers.append(h['ticker'])
        except Exception:
            pass
            
    print(f"\nBắt đầu quét {len(tickers)} cổ phiếu trong danh sách...")
    
    results = []
    for ticker in tickers:
        print(f"  Quét CANSLIM cho {ticker}...")
        res = run_canslim_screener(ticker, df_index)
        if res:
            results.append(res)
            
    results.sort(key=lambda x: x['composite_score'], reverse=True)
    
    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    
    json_path = os.path.join(args.output_dir, f"canslim_screener_{timestamp}.json")
    md_path = os.path.join(args.output_dir, f"canslim_screener_{timestamp}.md")
    
    # Clean results for JSON serialization
    serialized_results = make_json_serializable(results)
    
    with open(json_path, 'w', encoding='utf-8') as f_json:
        json.dump({
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "market_index": "VNINDEX",
            "market_trend": m_trend,
            "market_score": m_score,
            "candidates": serialized_results
        }, f_json, indent=2, ensure_ascii=False)
        
    md = []
    md.append("# BÁO CÁO KẾT QUẢ QUÉT CỔ PHIẾU CANSLIM")
    md.append(f"*Thời gian quét: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    md.append(f"\n## 1. Tổng quan Thị trường Chung (M - Market)")
    md.append(f"- **Xu hướng**: {m_trend}")
    md.append(f"- **Điểm số M**: {m_score}/100")
    md.append(f"- **Chi tiết**: {m_details}")
    if m_score == 0:
        md.append(f"\n> ⚠️ **CẢNH BÁO**: Thị trường chung đang trong xu hướng giảm mạnh. Quy tắc CANSLIM ưu tiên giữ an toàn vốn và rút tiền mặt.")
        
    md.append(f"\n## 2. Bảng Xếp Hạng Kết Quả Lọc (Top {args.top})")
    md.append("\n| Hạng | Mã CP | Điểm CANSLIM | Xếp loại | Giá hiện tại | Khuyến nghị hành động |")
    md.append("| --- | --- | --- | --- | --- | --- |")
    
    for idx, r in enumerate(results[:args.top], 1):
        md.append(f"| {idx} | **{r['ticker']}** | {r['composite_score']:.1f} | {r['rating']} | {r['current_price']:,.0f} VND | {r['recommendation']} |")
        
    md.append(f"\n## 3. Phân tích chi tiết từng Cổ phiếu")
    for r in results[:args.top]:
        md.append(f"\n---")
        md.append(f"### {r['ticker']} - Điểm số: {r['composite_score']:.1f} ({r['rating']})")
        md.append(f"- **Giá hiện tại**: {r['current_price']:,.0f} VND")
        md.append(f"- **Khuyến nghị**: {r['recommendation']}")
        md.append(f"\n**Chi tiết 7 tiêu chí CANSLIM:**")
        md.append(f"1. **C (Current Earnings)** - Điểm {r['components']['C']['score']}/100: {r['components']['C']['details']}")
        md.append(f"2. **A (Annual Growth)** - Điểm {r['components']['A']['score']}/100: {r['components']['A']['details']}")
        md.append(f"3. **N (Newness / Highs)** - Điểm {r['components']['N']['score']}/100: {r['components']['N']['details']}")
        md.append(f"4. **S (Supply/Demand)** - Điểm {r['components']['S']['score']}/100: {r['components']['S']['details']}")
        md.append(f"5. **L (Relative Strength)** - Điểm {r['components']['L']['score']}/100: {r['components']['L']['details']}")
        md.append(f"6. **I (Institutional)** - Điểm {r['components']['I']['score']}/100: {r['components']['I']['details']}")
        md.append(f"7. **M (Market)** - Điểm {r['components']['M']['score']}/100: {r['components']['M']['details']}")
        
    with open(md_path, 'w', encoding='utf-8') as f_md:
        f_md.write("\n".join(md))
        
    print("\n" + "="*85)
    print("                             BÁO CÁO LỌC CANSLIM")
    print("="*85)
    for idx, r in enumerate(results[:args.top], 1):
        print(f"{idx}. {r['ticker']:7} Điểm: {r['composite_score']:.1f} | Xếp loại: {r['rating']}")
        print(f"   Khuyến nghị: {r['recommendation']}")
        print("-" * 55)
    print(f"\n[+] Đã tạo báo cáo JSON tại: {json_path}")
    print(f"[+] Đã tạo báo cáo Markdown tại: {md_path}")
    print("="*85 + "\n")

if __name__ == '__main__':
    main()
