import os
import json
import csv
import subprocess
import tempfile
from tabulate import tabulate  # Check if tabulate is installed, if not we will format it manually

def get_latest_price(ticker):
    """
    Fetch the latest close price for a ticker using mozyfin ohlcv CLI.
    """
    # Create a temporary file path
    fd, temp_path = tempfile.mkstemp(suffix='.csv')
    os.close(fd)
    
    try:
        # Run mozyfin ohlcv ticker --limit 1 --csv temp_path
        cmd = ["mozyfin", "ohlcv", ticker, "--limit", "1", "--csv", temp_path]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
        
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            print(f"Error fetching data for {ticker}: {result.stderr}")
            return None
            
        # Read the CSV
        with open(temp_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if rows:
                close_price = float(rows[0]['close'])
                return close_price
    except Exception as e:
        print(f"Exception fetching price for {ticker}: {e}")
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    # Fallback to vnstock if mozyfin fails
    try:
        from vnstock_fallback import get_latest_price_vnstock
        fallback_price = get_latest_price_vnstock(ticker)
        if fallback_price is not None:
            return fallback_price
    except Exception as e:
        print(f"[-] Fallback to vnstock price failed: {e}")
            
    return None

def main():
    portfolio_file = 'portfolio.json'
    if not os.path.exists(portfolio_file):
        print(f"Error: {portfolio_file} not found.")
        return
        
    with open(portfolio_file, 'r', encoding='utf-8') as f:
        portfolio = json.load(f)
        
    holdings = portfolio.get('holdings', [])
    cash = portfolio.get('cash_balance_vnd', 0.0)
    
    table_rows = []
    total_cost = 0.0
    total_value = 0.0
    
    print("\nUpdating stock quotes from Mozyfin...")
    for holding in holdings:
        ticker = holding['ticker']
        shares = holding['shares']
        basis_price = holding['basis_price']
        allocation = holding['allocation']
        
        current_price = get_latest_price(ticker)
        if current_price is None:
            # Fallback to basis_price if we can't fetch it
            current_price = basis_price
            
        cost = shares * basis_price
        value = shares * current_price
        pnl = value - cost
        pnl_pct = (pnl / cost) * 100 if cost > 0 else 0.0
        
        total_cost += cost
        total_value += value
        
        table_rows.append([
            ticker,
            allocation.upper(),
            f"{shares:,}",
            f"{basis_price:,.0f} VND",
            f"{current_price:,.0f} VND",
            f"{value:,.0f} VND",
            f"{pnl:+,.0f} VND",
            f"{pnl_pct:+.2f}%"
        ])
        
        # Update JSON holding data with latest info
        holding['current_price'] = current_price
        holding['current_value'] = value
        holding['pnl'] = pnl
        holding['pnl_pct'] = pnl_pct
        
    # Save the updated portfolio with latest price cache
    portfolio['total_stock_value_vnd'] = total_value
    portfolio['total_portfolio_value_vnd'] = total_value + cash
    portfolio['total_cost_vnd'] = total_cost
    portfolio['total_pnl_vnd'] = total_value - total_cost
    portfolio['total_pnl_pct'] = ((total_value - total_cost) / total_cost * 100) if total_cost > 0 else 0.0
    
    with open(portfolio_file, 'w', encoding='utf-8') as f:
        json.dump(portfolio, f, indent=2)
        
    # Print Dashboard
    headers = ["Ticker", "Strategy", "Shares", "Basis Price", "Current Price", "Current Value", "P&L", "P&L %"]
    print("\n" + "="*80)
    print("                      VIETNAM STOCK PORTFOLIO DASHBOARD")
    print("="*80)
    print(tabulate(table_rows, headers=headers, tablefmt="grid"))
    
    overall_pnl = total_value - total_cost
    overall_pnl_pct = (overall_pnl / total_cost) * 100 if total_cost > 0 else 0.0
    
    print("\nSUMMARY:")
    print(f"Total Stock Cost:      {total_cost:,.0f} VND")
    print(f"Total Stock Value:     {total_value:,.0f} VND")
    print(f"Cash Balance:          {cash:,.0f} VND")
    print(f"Total Portfolio Value: {total_value + cash:,.0f} VND")
    print(f"Overall Stock P&L:     {overall_pnl:+,.0f} VND ({overall_pnl_pct:+.2f}%)")
    print("="*80 + "\n")

if __name__ == '__main__':
    # Make sure tabulate is available, else define a simple printer
    try:
        from tabulate import tabulate
    except ImportError:
        def tabulate(rows, headers, tablefmt="grid"):
            col_widths = [len(h) for h in headers]
            for row in rows:
                for idx, cell in enumerate(row):
                    col_widths[idx] = max(col_widths[idx], len(str(cell)))
            
            # Draw line
            sep = "+" + "+".join(["-" * (w + 2) for w in col_widths]) + "+"
            
            # Header
            header_str = "|" + "|".join([f" {headers[i].ljust(col_widths[i])} " for i in range(len(headers))]) + "|"
            
            result = [sep, header_str, sep]
            for row in rows:
                row_str = "|" + "|".join([f" {str(row[i]).ljust(col_widths[i])} " for i in range(len(row))]) + "|"
                result.append(row_str)
            result.append(sep)
            return "\n".join(result)
            
    main()
