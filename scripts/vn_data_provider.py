#!/usr/bin/env python3
import os
import subprocess
import json
import pandas as pd
import numpy as np

def get_clean_ticker(ticker):
    return ticker.split('.')[0].upper()

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

    def _run_mozyfin_csv(self, cmd_args, output_filename):
        # Do not call mozyfin for index symbols like VNINDEX, HNXINDEX, ^GSPC, ^VIX, SPY
        # to save the 5 requests/min rate limit.
        symbol_arg = cmd_args[1] if len(cmd_args) > 1 else ""
        if "INDEX" in symbol_arg.upper() or symbol_arg.startswith("^") or symbol_arg.upper() == "SPY":
            return None
            
        csv_path = os.path.join(self.tmp_dir, output_filename)
        
        # Simple disk cache to prevent rate limits: 
        # If file exists and is > 0 bytes, reuse it.
        # (In a long-running app we'd check modification time, but for one-off screener runs this is perfect)
        if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
            return csv_path
            
        csv_path_cmd = csv_path.replace("\\", "/")
        cmd = ["mozyfin"] + cmd_args + ["--csv", csv_path_cmd]
        
        env = os.environ.copy()
        
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
                
                if result.returncode == 0 and os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
                    return csv_path
                    
                # Check for rate limit or quota errors in stdout/stderr
                output = (result.stdout + " " + result.stderr).lower()
                if "quota" in output or "token" in output or "exhausted" in output:
                    print(f"⚠️ [API Quota Exceeded] mozyfin hết token/quota, bỏ qua {symbol_arg} để tránh infinite loop.")
                    return None
                    
                if "rate limit" in output or "429" in output or result.returncode != 0:
                    if attempt < max_retries - 1:
                        sleep_time = 12 * (attempt + 1)
                        print(f"⏳ [API Rate Limit] Lỗi mozyfin, chờ {sleep_time}s để thử lại ({attempt+1}/{max_retries})...")
                        time.sleep(sleep_time)
                        continue
                        
                return None
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    print(f"Error running mozyfin: {e}")
                    return None
        return None

    def get_quote(self, symbols: str):
        """Returns quote data for symbols."""
        cache_key = f"quote_{symbols}"
        if cache_key in self.cache: return self.cache[cache_key]
        
        results = []
        for symbol in symbols.split(","):
            symbol = symbol.strip()
            if not symbol: continue
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
        if "INDEX" in clean_ticker or clean_ticker.startswith("^") or clean_ticker == "SPY":
            return None
            
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                from vnstock import Market
                m = Market()
                df = m.equity(clean_ticker).ohlcv(length=trading_days, interval='1D')
                if df is not None and not df.empty:
                    df = df.sort_values('time', ascending=False)
                    historical = []
                    for _, row in df.iterrows():
                        historical.append({
                            "date": row['time'].strftime('%Y-%m-%d') if hasattr(row['time'], 'strftime') else str(row['time']).split(' ')[0],
                            "open": float(row['open']) * 1000.0,
                            "high": float(row['high']) * 1000.0,
                            "low": float(row['low']) * 1000.0,
                            "close": float(row['close']) * 1000.0,
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
                            "roic": ratios.get('roe', 0) / 100.0 if ratios.get('roe') else 0,
                            "debtToEquity": ratios.get('debt_to_equity'),
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
        return {
            "num_holders": 10,
            "ownership_pct": 50.0,
            "top_holders": []
        }

# =============================================================================
# STANDALONE VNSTOCK FALLBACK FUNCTIONS
# =============================================================================

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR  = os.path.abspath(os.path.join(SCRIPTS_DIR, '..'))
REPORTS_DIR = os.path.join(PLUGIN_DIR, 'reports')

def get_latest_price_vnstock(ticker: str) -> float | None:
    """
    L?y gi� d�ng c?a m?i nh?t t? vnstock v4.
    Gi� tr? v? l� VND (d� nh�n 1000).
    """
    try:
        from vnstock import Market
        clean = get_clean_ticker(ticker)
        m  = Market()
        df = m.equity(clean).ohlcv(length=1, interval='1D')
        if not df.empty:
            return float(df.iloc[-1]['close']) * 1000.0
    except Exception as e:
        print(f"[-] vnstock gi� th?t b?i ({ticker}): {e}")
    return None

def get_ta_data_vnstock(ticker: str):
    """
    T�nh SMA20, SMA50, RSI14, MACD t? d? li?u vnstock.
    Tr? v? (latest_dict, yesterday_dict) ho?c None.
    Dict tr? v? c� c�ng key v?i output Mozyfin CSV:
      close, sma_20, sma_50, rsi_14, macd, signal, histogram
    """
    try:
        from vnstock import Market
        clean = get_clean_ticker(ticker)
        m  = Market()
        df = m.equity(clean).ohlcv(length=120, interval='1D')

        if df.empty or len(df) < 50:
            return None

        # Chuy?n sang VND
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
        print(f"[-] vnstock TA th?t b?i ({ticker}): {e}")
    return None

def generate_fundamental_report_vnstock(ticker: str, save_dir: str = None) -> str | None:
    """
    T?o b�o c�o ph�n t�ch co b?n t? d? li?u vnstock v4.
    Luu v�o save_dir/{ticker}_report.md. Tr? v? du?ng d?n file.
    """
    if save_dir is None:
        save_dir = REPORTS_DIR
    os.makedirs(save_dir, exist_ok=True)

    try:
        from vnstock import Fundamental
        clean = get_clean_ticker(ticker)
        f  = Fundamental()
        print(f"[*] L?y d? li?u t�i ch�nh cho {ticker} t? vnstock...")
        df_ratios = f.equity(clean).ratio(period='year')

        if df_ratios.empty:
            print(f"[-] vnstock kh�ng c� d? li?u t? s? t�i ch�nh cho {ticker}.")
            return None

        # T�m c�c c?t nam (numeric strings)
        year_cols = sorted([c for c in df_ratios.columns if c.isdigit()], reverse=True)
        if not year_cols:
            return None

        # X�y t? di?n tra c?u
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

        # -- X�y d?ng Markdown -------------------------------------------------
        md = []
        md.append(f"# B�o C�o Ph�n T�ch Co B?n: {ticker} (Vnstock Fallback)")
        md.append(f"\n*B�o c�o du?c t?o t? d?ng t? vnstock v� Mozyfin kh�ng kh? d?ng.*\n")

        md.append(f"## 1. Ch? S? T�i Ch�nh (L?ch s? {len(year_cols)} nam)\n")

        metrics = [
            ('pe',              'H? s? P/E',                           False, True),
            ('pb',              'H? s? P/B',                           False, True),
            ('ps',              'H? s? P/S',                           False, True),
            ('ev_ebitda',       'Ch? s? EV/EBITDA',                    False, False),
            ('roe',             'ROE (V?n ch? s? h?u)',                True,  False),
            ('roa',             'ROA (T?ng t�i s?n)',                   True,  False),
            ('gross_margin',    'Bi�n l?i nhu?n g?p',                  True,  False),
            ('net_margin',      'Bi�n l?i nhu?n r�ng',                 True,  False),
            ('debt_to_equity',  'T? l? N? / V?n ch? s? h?u (D/E)',   False, True),
            ('short_term_ratio','T? s? thanh to�n hi?n h�nh',          False, True),
            ('quick_ratio',     'T? s? thanh to�n nhanh',              False, True),
        ]

        headers = ['Ch? ti�u t�i ch�nh / T? s?'] + year_cols
        md.append('| ' + ' | '.join(headers) + ' |')
        md.append('| ' + ' | '.join(['---'] * len(headers)) + ' |')

        for item_id, label, is_pct, is_ratio in metrics:
            row_vals = [label] + [val_str(item_id, yr, is_pct, is_ratio) for yr in year_cols]
            md.append('| ' + ' | '.join(row_vals) + ' |')

        # -- Nh?n d?nh t? d?ng -------------------------------------------------
        md.append('\n## 2. Nh?n �?nh T? �?ng\n')
        latest_yr = year_cols[0] if year_cols else None
        if latest_yr:
            md.append(f"D?a tr�n d? li?u nam t�i ch�nh g?n nh?t **{latest_yr}**:\n")

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
                    insights.append(f"- **Kh? nang sinh l?i cao:** ROE d?t **{roe_v:.2f}%** (>15% � ti�u chu?n d?u tu gi� tr?).")
                else:
                    insights.append(f"- **Kh? nang sinh l?i trung b�nh/th?p:** ROE d?t **{roe_v:.2f}%** (du?i m?c chu?n 15%).")

            if debt_v is not None:
                if debt_v < 1.0:
                    insights.append(f"- **Co c?u n? an to�n:** D/E = **{debt_v:.2f}x** (du?i 1.0x � t�i ch�nh v?ng ch?c).")
                else:
                    insights.append(f"- **��n b?y t�i ch�nh cao:** D/E = **{debt_v:.2f}x** (ti?m ?n r?i ro n? vay).")

            if cr_v is not None:
                if cr_v > 1.5:
                    insights.append(f"- **Thanh kho?n l�nh m?nh:** T? s? hi?n h�nh = **{cr_v:.2f}x** (kh? nang thanh to�n ng?n h?n t?t).")
                else:
                    insights.append(f"- **Luu � thanh kho?n:** T? s? hi?n h�nh = **{cr_v:.2f}x** (v?n luu d?ng tuong d?i eo h?p).")

            if pe_v is not None:
                if 0 < pe_v < 12:
                    insights.append(f"- **�?nh gi� h?p d?n:** P/E = **{pe_v:.1f}x** (tuong d?i r? so v?i m?t b?ng chung).")
                elif pe_v >= 12:
                    insights.append(f"- **�?nh gi� cao:** P/E = **{pe_v:.1f}x** (k? v?ng tang tru?ng cao du?c ph?n �nh v�o gi�).")

            if nm_v is not None:
                insights.append(f"- **Bi�n l?i nhu?n r�ng:** **{nm_v:.2f}%**.")

            md.append('\n'.join(insights) if insights else "- Kh�ng d? d? li?u d? dua ra nh?n d?nh chi ti?t.")

        md.append('\n## 3. K?t Lu?n & Khuy?n Ngh?\n')
        md.append("C? phi?u n�y n�n du?c d�nh gi� d?a tr�n c�c tr? c?t c?t l�i:")
        md.append("1. **B?i s? d?nh gi�**: So s�nh P/E v� P/B hi?n t?i v?i trung b�nh l?ch s?.")
        md.append("2. **S?c kh?e t�i ch�nh**: Kh? nang thanh to�n v� t? l? n?/v?n.")
        md.append("3. **Kh? nang sinh l?i**: Bi�n l?i nhu?n r�ng v� ROE qua nhi?u nam.")
        md.append(
            "\n*Luu �: B�o c�o d? ph�ng n�y ch? cung c?p ch? s? d?nh lu?ng. "
            "C�c ph�n t�ch d?nh t�nh (l?i th? c?nh tranh, tri?n v?ng ng�nh) "
            "n�n du?c tham chi?u ch�o v?i c�ng b? th�ng tin m?i nh?t c?a doanh nghi?p.*"
        )

        # -- Luu file ----------------------------------------------------------
        report_path = os.path.join(save_dir, f"{ticker}_report.md")
        with open(report_path, 'w', encoding='utf-8') as f_out:
            f_out.write('\n'.join(md))
        print(f"[+] �� luu b�o c�o vnstock fallback: {report_path}")
        return report_path

    except Exception as e:
        print(f"[-] Kh�ng t?o du?c b�o c�o vnstock cho {ticker}: {e}")
    return None
