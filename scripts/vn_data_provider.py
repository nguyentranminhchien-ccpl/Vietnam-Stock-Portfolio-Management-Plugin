#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import subprocess
import json
import time
import pandas as pd
import numpy as np

def get_clean_ticker(ticker):
    return ticker.split('.')[0].upper()

def normalize_vn_ticker(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if len(symbol) == 3 and symbol.isalpha():
        return f"{symbol}.VN"
    return symbol

class VNDataProvider:
    """
    Unified Data Provider for Vietnam Stocks.
    Uses mozyfin CLI as the primary data source via CSV export.
    Falls back to vnstock v4 for profiles if needed.
    """
    def __init__(self):
        self.cache = {}
        # Ensure a tmp dir exists for CSVs
        self.tmp_dir = os.path.join(os.path.dirname(__file__), ".tmp")
        os.makedirs(self.tmp_dir, exist_ok=True)

        # Theo dõi số lần mozyfin thất bại liên tiếp — khi đủ ngưỡng sẽ hỏi user
        self.mozyfin_fail_count: int = 0
        self.mozyfin_fail_threshold: int = 3  # hỏi sau 3 lần thất bại liên tiếp

        # Check if mozyfin CLI is installed and available
        self.mozyfin_available = True
        if os.environ.get('FORCE_VNSTOCK') == '1':
            self.mozyfin_available = False
        else:
            try:
                result = subprocess.run(["mozyfin", "--version"], capture_output=True)
                if result.returncode != 0:
                    self.mozyfin_available = False
            except Exception:
                self.mozyfin_available = False

    def _prompt_switch_to_vnstock(self):
        """
        Hiển thị cảnh báo và hỏi user có muốn tắt mozyfin cho phần còn lại
        của phiên không. Nếu stdin không phải terminal (non-interactive)
        thì tự động chọn Yes.
        """
        import sys
        print()
        print("=" * 65)
        print("  ⚠️  MOZYFIN THẤT BẠI {} LẦN LIÊN TIẾP".format(self.mozyfin_fail_count))
        print("=" * 65)
        print("  Mozyfin không trả về dữ liệu cho {} mã vừa rồi.".format(self.mozyfin_fail_count))
        print("  Tiếp tục dùng mozyfin sẽ lãng phí thời gian retry cho từng mã.")
        print()
        print("  Bạn có muốn chuyển sang dùng VNSTOCK cho toàn bộ phiên này không?")
        print("  (vnstock sẽ được dùng thay thế cho mọi yêu cầu dữ liệu tiếp theo)")
        print()

        # Nếu không có terminal (script chạy tự động), tự chọn Yes
        if not sys.stdin.isatty():
            print("  [Auto] Không có terminal → Tự động chuyển sang vnstock.")
            print("=" * 65)
            self.mozyfin_available = False
            return

        try:
            ans = input("  Chọn [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = ''
        print("=" * 65)

        if ans in ('', 'y', 'yes', 'có', 'co'):
            print("  ✅ Đã chuyển sang vnstock cho phiên này.")
            self.mozyfin_available = False
        else:
            print("  ▶ Tiếp tục thử mozyfin. Bộ đếm thất bại được reset.")
            self.mozyfin_fail_count = 0  # reset nếu user chọn tiếp tục
        print()

    def _run_mozyfin_csv(self, cmd_args, output_filename):
        if not self.mozyfin_available:
            return None

        # Do not call mozyfin for index symbols like VNINDEX, HNXINDEX, ^GSPC, ^VIX, SPY
        # to save the 5 requests/min rate limit.
        symbol_arg = cmd_args[1] if len(cmd_args) > 1 else ""
        if "INDEX" in symbol_arg.upper() or symbol_arg.startswith("^") or symbol_arg.upper() == "SPY":
            return None

        csv_path = os.path.join(self.tmp_dir, output_filename)

        # Disk cache with 24-hour TTL:
        if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
            file_age = time.time() - os.path.getmtime(csv_path)
            if file_age < 86400:  # 24 hours in seconds
                self.mozyfin_fail_count = 0  # cache hit → coi như thành công, reset bộ đếm
                return csv_path
            else:
                try:
                    os.remove(csv_path)
                except Exception:
                    pass

        csv_path_cmd = csv_path.replace("\\", "/")
        cmd = ["mozyfin"] + cmd_args + ["--csv", csv_path_cmd]

        env = os.environ.copy()

        max_retries = 3
        success = False
        for attempt in range(max_retries):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)

                if result.returncode == 0 and os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
                    self.mozyfin_fail_count = 0  # thành công → reset bộ đếm
                    success = True
                    break

                # Check for rate limit or quota errors in stdout/stderr
                output = (result.stdout + " " + result.stderr).lower()
                if "quota" in output or "token" in output or "exhausted" in output:
                    print(f"⚠️ [API Quota Exceeded] mozyfin hết token/quota, bỏ qua {symbol_arg} để tránh infinite loop.")
                    break  # thoát vòng retry, sẽ đếm thất bại bên dưới

                if "rate limit" in output or "429" in output or result.returncode != 0:
                    if attempt < max_retries - 1:
                        sleep_time = 12 * (attempt + 1)
                        print(f"⏳ [API Rate Limit] Lỗi mozyfin, chờ {sleep_time}s để thử lại ({attempt+1}/{max_retries})...")
                        time.sleep(sleep_time)
                        continue

                break  # thất bại không phải rate-limit, thoát luôn
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    print(f"Error running mozyfin: {e}")
                    break

        if not success:
            self.mozyfin_fail_count += 1
            # Kiểm tra ngưỡng thất bại — hỏi user sau khi vượt ngưỡng
            if self.mozyfin_available and self.mozyfin_fail_count >= self.mozyfin_fail_threshold:
                self._prompt_switch_to_vnstock()
            return None

        return csv_path


    def get_quote(self, symbols: str):
        """Returns quote data for symbols."""
        cache_key = f"quote_{symbols}"
        if cache_key in self.cache: return self.cache[cache_key]
        
        results = []
        # Normalize and filter empty symbols
        normalized_symbols = [normalize_vn_ticker(s) for s in symbols.split(",") if s.strip()]
        
        for symbol in normalized_symbols:
            clean_ticker = get_clean_ticker(symbol)
            
            # Fetch historical data to compute yearHigh, yearLow, avgVolume
            hist_data = self.get_historical_prices(symbol, days=365)
            
            if hist_data and "historical" in hist_data and len(hist_data["historical"]) > 0:
                hist = hist_data["historical"]
                latest = hist[0]
                price = latest["close"]
                change = 0
                prev = None
                if len(hist) > 1:
                    prev = hist[1]["close"]
                    change = price - prev
                
                highs = [h["high"] for h in hist]
                lows = [h["low"] for h in hist]
                vols = [h["volume"] for h in hist]
                
                year_high = max(highs) if highs else price
                year_low = min(lows) if lows else price
                
                # 50-day average volume
                vol_50 = sum(vols[:50]) / min(50, len(vols)) if vols else 0
                
                results.append({
                    "symbol": symbol,
                    "price": price,
                    "change": change,
                    "changesPercentage": (change/prev*100) if prev else 0,
                    "volume": latest["volume"],
                    "avgVolume": vol_50,
                    "yearHigh": year_high,
                    "yearLow": year_low,
                    "marketCap": 0
                })
            else:
                results.append({
                    "symbol": symbol,
                    "price": 0, "change": 0, "changesPercentage": 0,
                    "volume": 0, "avgVolume": 0, "yearHigh": 0, "yearLow": 0, "marketCap": 0
                })
                
        self.cache[cache_key] = results
        return results

    def get_historical_prices(self, symbol: str, days: int = 365):
        symbol = normalize_vn_ticker(symbol)
        cache_key = f"hist_{symbol}_{days}"
        if cache_key in self.cache: return self.cache[cache_key]
        
        clean_ticker = get_clean_ticker(symbol)
        trading_days = min(int(days * 252 / 365) + 20, 1000)
        
        # Always fetch 1000 to maximize cache hit for multiple timeframes (90d vs 365d)
        csv_path = self._run_mozyfin_csv(["ohlcv", symbol, "--limit", "1000"], f"{symbol}_ohlcv_hist.csv")
        if csv_path:
            try:
                df = pd.read_csv(csv_path)
                if not df.empty:
                    df = df.head(trading_days)
                    df['date'] = pd.to_datetime(df['timestamp'], unit='s').dt.strftime('%Y-%m-%d')
                    historical = []
                    for _, row in df.iterrows():
                        historical.append({
                            "date": row['date'],
                            "open": float(row['open']),
                            "high": float(row['high']),
                            "low": float(row['low']),
                            "close": float(row['close']),
                            "volume": float(row['volume'])
                        })
                    res = {"symbol": symbol, "historical": historical}
                    self.cache[cache_key] = res
                    return res
            except Exception:
                pass
                
        # Fallback vnstock
        is_vn_index = clean_ticker in ["VNINDEX", "HNXINDEX", "UPCOMINDEX"]
        if not is_vn_index and (clean_ticker.startswith("^") or clean_ticker == "SPY" or "INDEX" in clean_ticker):
            return None
            
        max_retries = 3
        for attempt in range(max_retries):
            try:
                from vnstock import Market
                m = Market()
                if is_vn_index:
                    df = m.index(clean_ticker).ohlcv(length=trading_days, interval='1D')
                else:
                    df = m.equity(clean_ticker).ohlcv(length=trading_days, interval='1D')
                    
                if df is not None and not df.empty:
                    df = df.sort_values('time', ascending=False)
                    historical = []
                    for _, row in df.iterrows():
                        historical.append({
                            "date": row['time'].strftime('%Y-%m-%d') if hasattr(row['time'], 'strftime') else str(row['time']).split(' ')[0],
                            "open": float(row['open']) * (1.0 if is_vn_index else 1000.0),
                            "high": float(row['high']) * (1.0 if is_vn_index else 1000.0),
                            "low": float(row['low']) * (1.0 if is_vn_index else 1000.0),
                            "close": float(row['close']) * (1.0 if is_vn_index else 1000.0),
                            "volume": float(row['volume'])
                        })
                    res = {"symbol": symbol, "historical": historical}
                    self.cache[cache_key] = res
                    return res
                # if df is empty, maybe rate limited, sleep and retry
                time.sleep(5)
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    return None
        return None

    def get_key_metrics(self, symbol: str, period: str = "annual", limit: int = 5):
        symbol = normalize_vn_ticker(symbol)
        cache_key = f"metrics_{symbol}_{period}_{limit}"
        if cache_key in self.cache: return self.cache[cache_key]
        
        clean_ticker = get_clean_ticker(symbol)
        
        csv_path = self._run_mozyfin_csv(["stats", symbol], f"{symbol}_stats.csv")
        if csv_path:
            try:
                df = pd.read_csv(csv_path)
                if not df.empty:
                    if period == "annual":
                        df_filtered = df[df['quarter'].isna()].copy()
                    else:
                        df_filtered = df[df['quarter'].notna()].copy()
                    
                    df_filtered = df_filtered.head(limit)
                    
                    results = []
                    for _, row in df_filtered.iterrows():
                        yr = int(row['year']) if not pd.isna(row['year']) else 0
                        qtr = int(row['quarter']) if not pd.isna(row['quarter']) else None
                        
                        pe = float(row['pe']) if 'pe' in row and not pd.isna(row['pe']) else None
                        fcf_yield_proxy = (1.0 / pe) if pe and pe > 0 else 0
                        
                        if period == "annual":
                            date_str = f"{yr}-12-31"
                        else:
                            months = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
                            date_str = f"{yr}-{months.get(qtr, '12-31')}"
                            
                        res_dict = {
                            "date": date_str,
                            "peRatio": pe,
                            "pbRatio": float(row['pb']) if 'pb' in row and not pd.isna(row['pb']) else None,
                            "roe": float(row['roe']) if 'roe' in row and not pd.isna(row['roe']) else 0,
                            "roic": float(row['roic']) if 'roic' in row and not pd.isna(row['roic']) else 0,
                            "debtToEquity": float(row['debt_to_equity']) if 'debt_to_equity' in row and not pd.isna(row['debt_to_equity']) else 0,
                            "freeCashFlowYield": fcf_yield_proxy,
                            "netProfitMargin": float(row['after_tax_profit_margin']) if 'after_tax_profit_margin' in row and not pd.isna(row['after_tax_profit_margin']) else 0
                        }
                        results.append(res_dict)
                    
                    self.cache[cache_key] = results
                    return results
            except Exception as e:
                print(f"Error parsing mozyfin stats: {e}")
                
        # Fallback to vnstock
        try:
            from vnstock import Fundamental
            f = Fundamental()
            df = f.equity(clean_ticker).ratio(period='year' if period == 'annual' else 'quarter')
            if not df.empty:
                year_cols = sorted([col for col in df.columns if col.isdigit()], reverse=True)
                if year_cols:
                    results = []
                    for yr in year_cols[:limit]:
                        ratios = {row['item_id']: row.get(yr) for _, row in df.iterrows()}
                        pe = ratios.get('pe')
                        fcf_yield_proxy = (1.0 / pe) if pe and pe > 0 else 0
                        res_dict = {
                            "date": f"{yr}-12-31",
                            "peRatio": pe,
                            "pbRatio": ratios.get('pb'),
                            "roe": ratios.get('roe', 0) / 100.0 if ratios.get('roe') else 0,
                            # Approximated by ROE if ROIC is missing in vnstock
                            "roic": ratios.get('roic', ratios.get('roe', 0)) / 100.0 if (ratios.get('roic') or ratios.get('roe')) else 0,
                            # vnstock trả về D/E dạng % (vd: 65.0 = 65%), chia 100 ra tỷ số thập phân
                            "debtToEquity": ratios.get('debt_to_equity', 0) / 100.0 if ratios.get('debt_to_equity') is not None else None,
                            "freeCashFlowYield": fcf_yield_proxy,
                            "netProfitMargin": ratios.get('net_margin', 0) / 100.0 if ratios.get('net_margin') else 0
                        }
                        results.append(res_dict)
                    self.cache[cache_key] = results
                    return results
        except:
            pass
            
        return None

    def get_income_statement(self, symbol: str, period: str = "annual", limit: int = 5):
        symbol = normalize_vn_ticker(symbol)
        cache_key = f"income_{symbol}_{period}_{limit}"
        if cache_key in self.cache: return self.cache[cache_key]
        
        clean_ticker = get_clean_ticker(symbol)
        csv_path = self._run_mozyfin_csv(["financials", symbol], f"{symbol}_fin.csv")
        if csv_path:
            try:
                df = pd.read_csv(csv_path)
                if not df.empty:
                    df = df[df['type'] == 'INCOME_STATEMENT']
                    if period == "annual":
                        df_filtered = df[df['quarter'].isna()].copy()
                    else:
                        df_filtered = df[df['quarter'].notna()].copy()
                    
                    df_filtered = df_filtered.head(limit)
                    
                    results = []
                    for _, row in df_filtered.iterrows():
                        yr = int(row['year']) if not pd.isna(row['year']) else 0
                        qtr = int(row['quarter']) if not pd.isna(row['quarter']) else None
                        
                        if period == "annual":
                            date_str = f"{yr}-12-31"
                        else:
                            months = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
                            date_str = f"{yr}-{months.get(qtr, '12-31')}"
                            
                        pat = float(row['profit_after_tax']) if 'profit_after_tax' in row and not pd.isna(row['profit_after_tax']) else 0
                        rev = float(row['net_sales']) if 'net_sales' in row and not pd.isna(row['net_sales']) else 0
                        
                        results.append({
                            "date": date_str,
                            "netIncome": pat,
                            "epsdiluted": pat,
                            "revenue": rev,
                            "eps": pat
                        })
                    
                    self.cache[cache_key] = results
                    return results
            except Exception as e:
                print(f"Error parsing mozyfin financials: {e}")
                
        return None

    def get_profile(self, symbol: str):
        symbol = normalize_vn_ticker(symbol)
        clean_ticker = get_clean_ticker(symbol)
        try:
            from vnstock import Fundamental
            f = Fundamental()
            df = f.equity(clean_ticker).profile()
            if not df.empty:
                row = df.iloc[0]
                return [{
                    "symbol": symbol,
                    "companyName": row.get('company_name', symbol),
                    "sector": row.get('industry', 'N/A'),
                    "industry": row.get('industry', 'N/A'),
                    "mktCap": 0
                }]
        except:
            pass
        return [{"symbol": symbol, "sector": "N/A", "industry": "N/A"}]

    def get_institutional_holders(self, symbol: str):
        symbol = normalize_vn_ticker(symbol)
        return {
            "num_holders": 0,
            "ownership_pct": 0.0,
            "top_holders": [],
            "status": "Not implemented"
        }

# =============================================================================
# STANDALONE VNSTOCK FALLBACK FUNCTIONS
# =============================================================================

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR  = os.path.abspath(os.path.join(SCRIPTS_DIR, '..'))
REPORTS_DIR = os.path.join(PLUGIN_DIR, 'reports')

def get_latest_price_vnstock(ticker: str) -> float | None:
    """
    Lấy giá đóng cửa mới nhất từ vnstock v4.
    Giá trị trả về là VND (đã nhân 1000).
    """
    try:
        from vnstock import Market
        clean = get_clean_ticker(ticker)
        m  = Market()
        df = m.equity(clean).ohlcv(length=1, interval='1D')
        if not df.empty:
            return float(df.iloc[-1]['close']) * 1000.0
    except Exception as e:
        print(f"[-] vnstock giá thất bại ({ticker}): {e}")
    return None

def get_ta_data_vnstock(ticker: str):
    """
    Tính SMA20, SMA50, RSI14, MACD từ dữ liệu vnstock.
    Trả về (latest_dict, yesterday_dict) hoặc None.
    Dict trả về có cùng key với output Mozyfin CSV:
      close, sma_20, sma_50, rsi_14, macd, signal, histogram
    """
    try:
        from vnstock import Market
        clean = get_clean_ticker(ticker)
        m  = Market()
        df = m.equity(clean).ohlcv(length=120, interval='1D')

        if df.empty or len(df) < 50:
            return None

        # Chuyển sang VND
        for col in ['open', 'high', 'low', 'close']:
            if col in df.columns:
                df[col] = df[col].astype(float) * 1000.0

        # SMA
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_50'] = df['close'].rolling(50).mean()

        # RSI 14
        delta    = df['close'].diff()
        gain     = delta.clip(lower=0)
        loss     = -delta.clip(upper=0)
        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()
        rs       = avg_gain / avg_loss.replace(0, np.nan)
        df['rsi_14'] = 100 - (100 / (1 + rs))

        # MACD (12, 26, 9)
        ema12       = df['close'].ewm(span=12, adjust=False).mean()
        ema26       = df['close'].ewm(span=26, adjust=False).mean()
        df['macd']  = ema12 - ema26
        df['signal']    = df['macd'].ewm(span=9, adjust=False).mean()
        df['histogram'] = df['macd'] - df['signal']

        df = df.where(pd.notnull(df), None)

        latest    = df.iloc[-1].to_dict()
        yesterday = df.iloc[-2].to_dict()
        return latest, yesterday

    except Exception as e:
        print(f"[-] vnstock TA thất bại ({ticker}): {e}")
    return None

def generate_fundamental_report_vnstock(ticker: str, save_dir: str = None) -> str | None:
    """
    Tạo báo cáo phân tích cơ bản từ dữ liệu vnstock v4.
    Lưu vào save_dir/{ticker}_report.md. Trả về đường dẫn file.
    """
    if save_dir is None:
        save_dir = REPORTS_DIR
    os.makedirs(save_dir, exist_ok=True)

    try:
        from vnstock import Fundamental
        clean = get_clean_ticker(ticker)
        f  = Fundamental()
        print(f"[*] Lấy dữ liệu tài chính cho {ticker} từ vnstock...")
        df_ratios = f.equity(clean).ratio(period='year')

        if df_ratios.empty:
            print(f"[-] vnstock không có dữ liệu tỷ số tài chính cho {ticker}.")
            return None

        # Tìm các cột năm (numeric strings)
        year_cols = sorted([c for c in df_ratios.columns if c.isdigit()], reverse=True)
        if not year_cols:
            return None

        # Xây dựng từ điển tra cứu
        ratios: dict = {}
        for _, row in df_ratios.iterrows():
            item_id = row.get('item_id', '')
            ratios[item_id] = {yr: row.get(yr) for yr in year_cols}

        def val_str(item_id: str, year: str, is_pct: bool = False, is_ratio: bool = False) -> str:
            v = ratios.get(item_id, {}).get(year)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return 'N/A'
            if is_pct:
                return f"{v:.2f}%"
            if is_ratio:
                return f"{v:.2f}x"
            return f"{v:.2f}"

        # -- Xây dựng Markdown -------------------------------------------------
        md = []
        md.append(f"# Báo Cáo Phân Tích Cơ Bản: {ticker} (Vnstock Fallback)")
        md.append(f"\n*Báo cáo được tạo tự động từ vnstock vì Mozyfin không khả dụng.*\n")

        md.append(f"## 1. Chỉ Số Tài Chính (Lịch sử {len(year_cols)} năm)\n")

        # vnstock trả D/E dạng % (vd: 65.0 = 65% = 0.65x) → cần chia 100
        def val_str_de(item_id: str, year: str) -> str:
            """Formatter riêng cho D/E: chia 100 vì vnstock trả về dạng %."""
            v = ratios.get(item_id, {}).get(year)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return 'N/A'
            return f"{v / 100.0:.2f}x"

        metrics = [
            ('pe',              'Hệ số P/E',                           False, True,  False),
            ('pb',              'Hệ số P/B',                           False, True,  False),
            ('ps',              'Hệ số P/S',                           False, True,  False),
            ('ev_ebitda',       'Chỉ số EV/EBITDA',                    False, False, False),
            ('roe',             'ROE (Vốn chủ sở hữu)',                True,  False, False),
            ('roa',             'ROA (Tổng tài sản)',                   True,  False, False),
            ('gross_margin',    'Biên lợi nhuận gộp',                  True,  False, False),
            ('net_margin',      'Biên lợi nhuận ròng',                 True,  False, False),
            ('debt_to_equity',  'Tỷ lệ Nợ / Vốn chủ sở hữu (D/E)',   False, True,  True),  # is_de=True
            ('short_term_ratio','Tỷ số thanh toán hiện hành',          False, True,  False),
            ('quick_ratio',     'Tỷ số thanh toán nhanh',              False, True,  False),
        ]

        headers = ['Chỉ tiêu tài chính / Tỷ số'] + year_cols
        md.append('| ' + ' | '.join(headers) + ' |')
        md.append('| ' + ' | '.join(['---'] * len(headers)) + ' |')

        for item_id, label, is_pct, is_ratio, is_de in metrics:
            if is_de:
                row_vals = [label] + [val_str_de(item_id, yr) for yr in year_cols]
            else:
                row_vals = [label] + [val_str(item_id, yr, is_pct, is_ratio) for yr in year_cols]
            md.append('| ' + ' | '.join(row_vals) + ' |')

        # -- Nhận định tự động -------------------------------------------------
        md.append('\n## 2. Nhận Định Tự Động\n')
        latest_yr = year_cols[0] if year_cols else None
        if latest_yr:
            md.append(f"Dựa trên dữ liệu năm tài chính gần nhất **{latest_yr}**:\n")

            def get_num(item_id: str) -> float | None:
                v = ratios.get(item_id, {}).get(latest_yr)
                if v is None:
                    return None
                try:
                    f_val = float(v)
                    return None if np.isnan(f_val) else f_val
                except (TypeError, ValueError):
                    return None

            roe_v   = get_num('roe')
            debt_v  = get_num('debt_to_equity')
            cr_v    = get_num('short_term_ratio')
            pe_v    = get_num('pe')
            nm_v    = get_num('net_margin')

            insights = []
            if roe_v is not None:
                if roe_v > 15:
                    insights.append(f"- **Khả năng sinh lợi cao:** ROE đạt **{roe_v:.2f}%** (>15% là tiêu chuẩn đầu tư giá trị).")
                else:
                    insights.append(f"- **Khả năng sinh lợi trung bình/thấp:** ROE đạt **{roe_v:.2f}%** (dưới mức chuẩn 15%).")

            if debt_v is not None:
                # vnstock D/E đơn vị %: chia 100 trước khi hiển thị
                debt_ratio = debt_v / 100.0
                if debt_ratio < 1.0:
                    insights.append(f"- **Cơ cấu nợ an toàn:** D/E = **{debt_ratio:.2f}x** (dưới 1.0x là tài chính vững chắc).")
                else:
                    insights.append(f"- **Đòn bẩy tài chính cao:** D/E = **{debt_ratio:.2f}x** (tiềm ẩn rủi ro nợ vay — lưu ý: bình thường với ngân hàng/CTCK).")

            if cr_v is not None:
                if cr_v > 1.5:
                    insights.append(f"- **Thanh khoản lành mạnh:** Tỷ số hiện hành = **{cr_v:.2f}x** (khả năng thanh toán ngắn hạn tốt).")
                else:
                    insights.append(f"- **Lưu ý thanh khoản:** Tỷ số hiện hành = **{cr_v:.2f}x** (vốn lưu động tương đối eo hẹp).")

            if pe_v is not None:
                if 0 < pe_v < 12:
                    insights.append(f"- **Định giá hấp dẫn:** P/E = **{pe_v:.1f}x** (tương đối rẻ so với mặt bằng chung).")
                elif pe_v >= 12:
                    insights.append(f"- **Định giá cao:** P/E = **{pe_v:.1f}x** (kỳ vọng tăng trưởng cao được phản ánh vào giá).")

            if nm_v is not None:
                insights.append(f"- **Biên lợi nhuận ròng:** **{nm_v:.2f}%**.")

            md.append('\n'.join(insights) if insights else "- Không đủ dữ liệu để đưa ra nhận định chi tiết.")

        md.append('\n## 3. Kết Luận & Khuyến Nghị\n')
        md.append("Cổ phiếu này nên được đánh giá dựa trên các trụ cột cốt lõi:")
        md.append("1. **Bội số định giá**: So sánh P/E và P/B hiện tại với trung bình lịch sử.")
        md.append("2. **Sức khỏe tài chính**: Khả năng thanh toán và tỷ lệ nợ/vốn.")
        md.append("3. **Khả năng sinh lợi**: Biên lợi nhuận ròng và ROE qua nhiều năm.")
        md.append(
            "\n*Lưu ý: Báo cáo dự phòng này chỉ cung cấp chỉ số định lượng. "
            "Các phân tích định tính (lợi thế cạnh tranh, triển vọng ngành) "
            "nên được tham chiếu chéo với công bố thông tin mới nhất của doanh nghiệp.*"
        )

        # -- Lưu file ----------------------------------------------------------
        report_path = os.path.join(save_dir, f"{ticker}_report.md")
        with open(report_path, 'w', encoding='utf-8') as f_out:
            f_out.write('\n'.join(md))
        print(f"[+] Đã lưu báo cáo vnstock fallback: {report_path}")
        return report_path

    except Exception as e:
        print(f"[-] Không tạo được báo cáo vnstock cho {ticker}: {e}")
    return None
