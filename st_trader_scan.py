import os
import json
import csv
import subprocess
import tempfile

def parse_risk_data(ticker):
    """
    Run mozyfin risk and parse the key-value outputs.
    """
    try:
        cmd = ["mozyfin", "risk", ticker, "--limit", "252"]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
        
        metrics = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("- "):
                line = line[2:]  # Remove the leading "- "
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip()
                    try:
                        metrics[key] = float(val)
                    except ValueError:
                        metrics[key] = val
        return metrics
    except Exception as e:
        print(f"Exception parsing risk for {ticker}: {e}")
        return {}

def run_ta_scan(ticker):
    """
    Run mozyfin ta and parse the latest and previous rows.
    """
    fd, temp_path = tempfile.mkstemp(suffix='.csv')
    os.close(fd)
    
    try:
        cmd = ["mozyfin", "ta", ticker, "--sma", "20,50", "--rsi", "14", "--macd", "--limit", "120", "--csv", temp_path]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
        
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            return None
            
        with open(temp_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if len(rows) >= 2:
                # rows[0] is the latest day, rows[1] is the day before
                return rows[0], rows[1]
    except Exception as e:
        print(f"Exception running TA for {ticker}: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    # Fallback to vnstock if mozyfin fails
    try:
        from vnstock_fallback import get_ta_data_vnstock
        fallback_ta = get_ta_data_vnstock(ticker)
        if fallback_ta is not None:
            return fallback_ta
    except Exception as e:
        print(f"[-] Fallback to vnstock TA failed: {e}")
        
    return None

def main():
    portfolio_file = 'portfolio.json'
    if not os.path.exists(portfolio_file):
        print(f"Error: {portfolio_file} not found.")
        return
        
    with open(portfolio_file, 'r', encoding='utf-8') as f:
        portfolio = json.load(f)
        
    holdings = portfolio.get('holdings', [])
    st_holdings = [h for h in holdings if h['allocation'] == 'short-term']
    
    if not st_holdings:
        print("No short-term holdings found in portfolio.json.")
        return
        
    print("\n" + "="*80)
    print("                      SHORT-TERM SWING TRADER ALERTS")
    print("="*80)
    
    for holding in st_holdings:
        ticker = holding['ticker']
        shares = holding['shares']
        basis_price = holding['basis_price']
        
        ta_data = run_ta_scan(ticker)
        risk_data = parse_risk_data(ticker)
        
        if not ta_data:
            print(f"[-] Could not retrieve TA data for {ticker}")
            continue
            
        today, yesterday = ta_data
        
        close_price = float(today['close'])
        sma_20 = float(today['sma_20']) if today['sma_20'] else None
        sma_50 = float(today['sma_50']) if today['sma_50'] else None
        rsi_14 = float(today['rsi_14']) if today['rsi_14'] else None
        macd_today = float(today['macd']) if today['macd'] else None
        sig_today = float(today['signal']) if today['signal'] else None
        macd_yesterday = float(yesterday['macd']) if yesterday['macd'] else None
        sig_yesterday = float(yesterday['signal']) if yesterday['signal'] else None
        
        # Calculate PnL
        pnl_pct = ((close_price - basis_price) / basis_price) * 100
        
        # Evaluate signals
        trend = "NEUTRAL"
        if sma_20 and sma_50:
            if close_price > sma_20 > sma_50:
                trend = "BULLISH (Close > SMA20 > SMA50)"
            elif close_price < sma_20 < sma_50:
                trend = "BEARISH (Close < SMA20 < SMA50)"
                
        rsi_status = "NEUTRAL"
        if rsi_14:
            if rsi_14 > 70:
                rsi_status = f"OVERBOUGHT ({rsi_14:.1f}) - SELL WARNING"
            elif rsi_14 < 30:
                rsi_status = f"OVERSOLD ({rsi_14:.1f}) - BUY WATCH"
            else:
                rsi_status = f"NEUTRAL ({rsi_14:.1f})"
                
        macd_cross = "NEUTRAL"
        if macd_today is not None and sig_today is not None and macd_yesterday is not None and sig_yesterday is not None:
            if macd_today > sig_today and macd_yesterday <= sig_yesterday:
                macd_cross = "BULLISH CROSSOVER (MACD crossed above Signal)"
            elif macd_today < sig_today and macd_yesterday >= sig_yesterday:
                macd_cross = "BEARISH CROSSOVER (MACD crossed below Signal)"
                
        # Risk stop loss
        risk_action = "HOLD"
        stop_loss_pct = -7.0  # -7% standard stop loss
        take_profit_pct = 15.0  # +15% target
        
        if pnl_pct <= stop_loss_pct:
            risk_action = f"SELL (STOP LOSS TRIGGERED: {pnl_pct:.2f}%)"
        elif pnl_pct >= take_profit_pct:
            risk_action = f"SELL (TAKE PROFIT TRIGGERED: {pnl_pct:.2f}%)"
            
        print(f"Ticker: {ticker} (Short-term Swing)")
        print(f"  Current Close:   {close_price:,.0f} VND (Cost Basis: {basis_price:,.0f} VND, PnL: {pnl_pct:+.2f}%)")
        print(f"  Trend (SMA):     {trend}")
        print(f"  RSI:             {rsi_status}")
        print(f"  MACD Crossover:  {macd_cross}")
        
        if risk_data:
            ann_ret = risk_data.get('annualReturn', 0) * 100
            vol = risk_data.get('volatility', 0) * 100
            sharpe = risk_data.get('sharpe', 0)
            max_dd = risk_data.get('maxDrawdown', 0) * 100
            print(f"  Volatility (1y): {vol:.1f}% | Sharpe: {sharpe:.2f} | Max Drawdown: {max_dd:.1f}%")
            
        print(f"  Recommended Action: {risk_action}")
        print("-" * 50)
    print("="*80 + "\n")

if __name__ == '__main__':
    main()
