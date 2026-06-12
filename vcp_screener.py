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

def calculate_vcp_contractions(df):
    """
    Look for Volatility Contraction Pattern (VCP) characteristics.
    Measures a series of declining pullback depths (e.g. 20% -> 10% -> 5%).
    Returns (num_contractions, pullbacks_list, volume_dry_up_status).
    """
    close = df['close'].values
    volume = df['volume'].values
    
    # Locate recent local peaks and troughs over the last 120 days
    lookback = 120
    if len(close) < lookback:
        lookback = len(close)
    
    prices_recent = close[-lookback:]
    vols_recent = volume[-lookback:]
    
    peaks = []
    troughs = []
    
    for i in range(5, len(prices_recent) - 5):
        val = prices_recent[i]
        if val == max(prices_recent[i-5:i+6]):
            peaks.append((i, val))
        if val == min(prices_recent[i-5:i+6]):
            troughs.append((i, val))
            
    pullbacks = []
    for peak_idx, peak_val in peaks:
        next_troughs = [t for t in troughs if t[0] > peak_idx]
        if next_troughs:
            trough_idx, trough_val = next_troughs[0]
            depth = (peak_val - trough_val) / peak_val * 100
            if depth > 2.0:
                pullbacks.append({
                    "peak_idx": peak_idx,
                    "trough_idx": trough_idx,
                    "peak": peak_val,
                    "trough": trough_val,
                    "depth": depth
                })
                
    pullbacks.sort(key=lambda x: x['peak_idx'])
    
    distinct_pullbacks = []
    last_end = -1
    for p in pullbacks:
        if p['peak_idx'] > last_end:
            distinct_pullbacks.append(p)
            last_end = p['trough_idx']
            
    contractions = []
    for dp in distinct_pullbacks:
        contractions.append(dp['depth'])
        
    is_declining = True
    for i in range(len(contractions) - 1):
        if contractions[i] < contractions[i+1]:
            is_declining = False
            break
            
    recent_vol_avg = np.mean(vols_recent[-5:]) if len(vols_recent) >= 5 else 0.0
    long_vol_avg = np.mean(vols_recent[-20:]) if len(vols_recent) >= 20 else 1.0
    vol_dry_up = recent_vol_avg < (long_vol_avg * 0.85)
    
    vol_status = "ĐẠT (Volume kiệt quệ)" if vol_dry_up else "KHÔNG ĐẠT (Volume cao)"
    
    return len(contractions), contractions, vol_status, is_declining

def run_vcp_screener(ticker, df_index):
    """Check if a ticker matches Mark Minervini's VCP Trend Template."""
    try:
        df = fetch_stock_history(ticker, length=260)
        if df is None or df.empty or len(df) < 200:
            return None
            
        df['sma_50'] = df['close'].rolling(50).mean()
        df['sma_150'] = df['close'].rolling(150).mean()
        df['sma_200'] = df['close'].rolling(200).mean()
        
        close = df.iloc[-1]['close']
        sma_50 = df.iloc[-1]['sma_50']
        sma_150 = df.iloc[-1]['sma_150']
        sma_200 = df.iloc[-1]['sma_200']
        
        high_52w = df['high'].max()
        low_52w = df['low'].min()
        
        sma_200_trend_up = df.iloc[-1]['sma_200'] > df.iloc[-20]['sma_200']
        
        rs_score = 50.0
        if df_index is not None and not df_index.empty:
            stock_return_12m = (close - df.iloc[-250]['close']) / df.iloc[-250]['close'] * 100 if len(df) >= 250 else 0.0
            idx_close_now = df_index.iloc[-1]['close']
            idx_close_12m = df_index.iloc[-250]['close'] if len(df_index) >= 250 else df_index.iloc[0]['close']
            index_return_12m = (idx_close_now - idx_close_12m) / idx_close_12m * 100
            rs_score = stock_return_12m - index_return_12m
            
        criteria = {
            "1. Close > SMA150 & Close > SMA200": close > sma_150 and close > sma_200,
            "2. SMA150 > SMA200": sma_150 > sma_200,
            "3. SMA200 đang hướng lên": sma_200_trend_up,
            "4. SMA50 > SMA150 & SMA50 > SMA200": sma_50 > sma_150 and sma_50 > sma_200,
            "5. Close > SMA50": close > sma_50,
            "6. Close >= 30% so với đáy 52 tuần": close >= (low_52w * 1.30),
            "7. Close cách đỉnh 52 tuần <= 25%": close >= (high_52w * 0.75)
        }
        
        score = sum(criteria.values())
        is_trend_template_met = score >= 5
        
        num_contractions, contractions, vol_status, is_declining = calculate_vcp_contractions(df)
        
        return {
            "ticker": ticker,
            "close": close,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "score": score,
            "trend_template_met": "ĐẠT" if is_trend_template_met else "KHÔNG ĐẠT",
            "criteria": criteria,
            "contractions": contractions,
            "contraction_count": num_contractions,
            "is_declining": is_declining,
            "vol_status": vol_status,
            "rs_score": rs_score
        }
    except Exception as e:
        print(f"[-] Lỗi quét VCP cho {ticker}: {e}")
    return None

def main():
    parser = argparse.ArgumentParser(description="VCP Volatility Contraction Pattern Screener - Vietnam Equity")
    parser.add_argument("--universe", nargs="+", help="Custom stock list (e.g. FPT.VN HPG.VN)")
    parser.add_argument("--strict", action="store_true", help="Only show candidates meeting 7/7 Trend Template and declining contractions")
    parser.add_argument("--min-contractions", type=int, default=2, help="Minimum contractions for VCP")
    parser.add_argument("--top", type=int, default=10, help="Top N stocks in final report")
    parser.add_argument("--output-dir", default="reports", help="Reports output directory")
    args = parser.parse_args()
    
    print("\n" + "="*85)
    print("                 QUÉT MẪU HÌNH BIÊN ĐỘ THU HẸP (VCP SCREENER) - VIETNAM")
    print("="*85)
    
    print("Đang lấy thông tin thị trường chung VNINDEX...")
    df_index = fetch_index_history(260)
    
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
            
    results = []
    for ticker in tickers:
        print(f"Đang quét VCP cho {ticker}...")
        res = run_vcp_screener(ticker, df_index)
        if res:
            if args.strict:
                if res['score'] < 7 or res['contraction_count'] < args.min_contractions or not res['is_declining']:
                    continue
            else:
                if res['contraction_count'] < args.min_contractions:
                    continue
            results.append(res)
            
    results.sort(key=lambda x: (x['score'], x['contraction_count'], x['rs_score']), reverse=True)
    
    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    
    json_path = os.path.join(args.output_dir, f"vcp_screener_{timestamp}.json")
    md_path = os.path.join(args.output_dir, f"vcp_screener_{timestamp}.md")
    
    # Clean results for JSON serialization
    serialized_results = make_json_serializable(results)
    
    with open(json_path, 'w', encoding='utf-8') as f_json:
        json.dump({
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "strict_mode": args.strict,
            "min_contractions": args.min_contractions,
            "candidates": serialized_results
        }, f_json, indent=2, ensure_ascii=False)
        
    md = []
    md.append("# BÁO CÁO KẾT QUẢ QUÉT MẪU HÌNH VCP")
    md.append(f"*Thời gian quét: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    md.append(f"- **Chế độ quét**: {'Strict (Nghiêm ngặt)' if args.strict else 'Thường'}")
    md.append(f"- **Số nhịp thu hẹp tối thiểu**: {args.min_contractions}")
    
    md.append(f"\n## Bảng Xếp Hạng Kết Quả Lọc (Top {args.top})")
    md.append("\n| Hạng | Mã CP | Xu hướng (Trend) | Số nhịp VCP | Nhịp pullback (%) | Vol Dry-up | RS vs VNINDEX | Khuyến nghị |")
    md.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    
    for idx, r in enumerate(results[:args.top], 1):
        depth_str = " -> ".join([f"{d:.1f}%" for d in r['contractions']]) if r['contraction_count'] > 0 else "N/A"
        rec = "BỎ QUA"
        if r['score'] == 7 and r['contraction_count'] >= 2 and r['is_declining']:
            rec = "MUA THEO DÕI PIVOT BREAKOUT"
        elif r['score'] >= 5:
            rec = "THEO DÕI THÊM"
            
        md.append(f"| {idx} | **{r['ticker']}** | {r['trend_template_met']} ({r['score']}/7) | {r['contraction_count']} | {depth_str} | {r['vol_status']} | {r['rs_score']:+.1f}% | {rec} |")
        
    md.append(f"\n## Chi tiết tiêu chí xu hướng tăng (Trend Template)")
    for r in results[:args.top]:
        md.append(f"\n### {r['ticker']} - Giá: {r['close']:,.0f} VND (Điểm xu hướng: {r['score']}/7)")
        for crit, met in r['criteria'].items():
            status = "✓" if met else "✗"
            md.append(f"- {status} {crit}")
            
    with open(md_path, 'w', encoding='utf-8') as f_md:
        f_md.write("\n".join(md))
        
    print("\n" + "="*85)
    print("                                 BÁO CÁO KẾT QUẢ VCP")
    print("="*85)
    
    for idx, r in enumerate(results[:args.top], 1):
        print(f"{idx}. Mã cổ phiếu: {r['ticker']}")
        print(f"   Giá hiện tại:    {r['close']:,.0f} VND")
        print(f"   Trend Template:  {r['trend_template_met']} ({r['score']}/7 tiêu chí)")
        print(f"   Độ thu hẹp (VCP): {r['contraction_count']} lần thu hẹp")
        if r['contraction_count'] > 0:
            depth_str = " -> ".join([f"{d:.1f}%" for d in r['contractions']])
            print(f"     Các nhịp pullback: {depth_str}")
        print(f"   Khối lượng (Vol): {r['vol_status']}")
        
        rec = "BỎ QUA"
        if r['score'] == 7 and r['contraction_count'] >= 2:
            rec = "MUA THEO DÕI ĐIỂM PIVOT BREAKOUT (ĐỦ TIÊU CHUẨN MINERVINI)"
        elif r['score'] >= 5:
            rec = "THEO DÕI THÊM (Chờ hoàn thành mẫu hình thu hẹp)"
        print(f"   KHUYẾN NGHỊ:     {rec}")
        print("-" * 65)
        
    print(f"\n[+] Đã tạo báo cáo JSON tại: {json_path}")
    print(f"[+] Đã tạo báo cáo Markdown tại: {md_path}")
    print("="*85 + "\n")

if __name__ == '__main__':
    main()
