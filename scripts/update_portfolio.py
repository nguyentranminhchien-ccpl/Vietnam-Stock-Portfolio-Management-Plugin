import os
import json
from datetime import datetime
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from preflight import PORTFOLIO_FILE, DATA_DIR

BASE_DIR = SCRIPTS_DIR  # backward compat

def load_json(file_path, default):
    if not os.path.exists(file_path):
        return default
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def record_transaction(ticker, action, shares, price, allocation):
    tx_file = os.path.join(DATA_DIR, 'transactions.json')
    transactions = load_json(tx_file, [])
    
    tx_record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker": ticker,
        "action": action.upper(),
        "shares": shares,
        "price": price,
        "total_value": shares * price,
        "allocation": allocation
    }
    transactions.append(tx_record)
    save_json(tx_file, transactions)
    print(f"[+] Ghi nhận giao dịch: {action.upper()} {shares:,} cổ phiếu {ticker} giá {price:,.0f} VND.")

def update_holdings(ticker, action, shares, price, allocation, dry_run=False):
    portfolio_file = PORTFOLIO_FILE  # data/portfolio.json — nguồn duy nhất
    portfolio = load_json(portfolio_file, {"cash_balance_vnd": 0, "holdings": []})
    
    total_val = shares * price
    
    if dry_run:
        print("\n" + "="*55)
        print("  [DRY-RUN] XEM TRƯỚC - KHÔNG GHI FILE")
        print("="*55)
    
    # 1. Update Cash Balance
    if action.lower() == 'buy':
        if portfolio['cash_balance_vnd'] < total_val:
            print(f"[-] LỖI: Không đủ tiền mặt! Cần {total_val:,.0f} VND, hiện có {portfolio['cash_balance_vnd']:,.0f} VND.")
            return False
        new_cash = portfolio['cash_balance_vnd'] - total_val
        if not dry_run:
            portfolio['cash_balance_vnd'] -= total_val
        else:
            print(f"  Tiền mặt: {portfolio['cash_balance_vnd']:,.0f} → {new_cash:,.0f} VND (giảm {total_val:,.0f} VND)")
    elif action.lower() == 'sell':
        new_cash = portfolio['cash_balance_vnd'] + total_val
        if not dry_run:
            portfolio['cash_balance_vnd'] += total_val
        else:
            print(f"  Tiền mặt: {portfolio['cash_balance_vnd']:,.0f} → {new_cash:,.0f} VND (tăng {total_val:,.0f} VND)")
        
    # 2. Update Holdings list
    holdings = portfolio.get('holdings', [])
    found = False
    
    for idx, holding in enumerate(holdings):
        # Match ticker and strategy bucket
        if holding['ticker'] == ticker and holding['allocation'] == allocation:
            found = True
            if action.lower() == 'buy':
                curr_shares = holding['shares']
                curr_basis  = holding['basis_price']
                new_shares  = curr_shares + shares
                new_basis   = ((curr_shares * curr_basis) + total_val) / new_shares
                if dry_run:
                    print(f"  {ticker}: {curr_shares:,} CP @ {curr_basis:,.0f} + {shares:,} CP @ {price:,.0f}")
                    print(f"         → {new_shares:,} CP, giá vốn mới: {new_basis:,.0f} VND")
                else:
                    holding['shares']      = new_shares
                    holding['basis_price'] = round(new_basis, 2)
                    print(f"[+] Cập nhật vị thế: {ticker} đạt {new_shares:,} CP, giá vốn mới: {new_basis:,.0f} VND.")
            elif action.lower() == 'sell':
                curr_shares = holding['shares']
                if curr_shares < shares:
                    print(f"[-] LỖI: Vị thế không đủ cổ phiếu để bán! Có {curr_shares:,} CP, yêu cầu bán {shares:,} CP.")
                    return False
                new_shares = curr_shares - shares
                if dry_run:
                    print(f"  {ticker}: {curr_shares:,} CP → {new_shares:,} CP (bán {shares:,} @ {price:,.0f})")
                    if new_shares == 0:
                        print(f"  → Vị thế sẽ bị đóng hoàn toàn")
                else:
                    if new_shares == 0:
                        holdings.pop(idx)
                        print(f"[+] Đã bán hết toàn bộ vị thế {ticker} ({allocation}).")
                    else:
                        holding['shares'] = new_shares
                        print(f"[+] Giảm vị thế: {ticker} còn {new_shares:,} CP.")
            break
            
    if not found:
        if action.lower() == 'buy':
            if dry_run:
                print(f"  → Mở vị thế mới: {shares:,} CP {ticker} ({allocation}) @ {price:,.0f} VND")
            else:
                new_holding = {
                    "ticker":      ticker,
                    "shares":      shares,
                    "basis_price": price,
                    "allocation":  allocation
                }
                holdings.append(new_holding)
                print(f"[+] Mở vị thế mới: {shares:,} CP {ticker} ({allocation}) giá {price:,.0f} VND.")
        elif action.lower() == 'sell':
            print(f"[-] LỖI: Không tìm thấy vị thế {ticker} ({allocation}) để bán.")
            return False
    
    if dry_run:
        print(f"  Tổng giao dịch: {action.upper()} {shares:,} CP {ticker} @ {price:,.0f} VND = {total_val:,.0f} VND")
        print("\n[DRY-RUN] Không có thay đổi nào được ghi vào file.")
        return True
            
    portfolio['holdings'] = holdings
    save_json(portfolio_file, portfolio)
    return True

def main():
    # Parse CLI Arguments
    # Usage: python update_portfolio.py [buy/sell] [ticker] [shares] [price] [short-term/long-term] [--dry-run]
    dry_run = '--dry-run' in sys.argv
    args = [a for a in sys.argv[1:] if a != '--dry-run']
    
    if len(args) < 5:
        print("Cú pháp: python update_portfolio.py [buy/sell] [ticker] [số_lượng] [giá] [short-term/long-term] [--dry-run]")
        print("Ví dụ: python update_portfolio.py buy SHS.VN 500 19000 short-term --dry-run")
        sys.exit(1)
        
    action     = args[0]
    ticker     = args[1].upper()
    shares     = int(args[2])
    price      = float(args[3])
    allocation = args[4].lower()
    
    # Input validation
    if shares <= 0:
        print("Lỗi: Số lượng cổ phiếu phải lớn hơn 0.")
        sys.exit(1)
    if price <= 0:
        print("Lỗi: Giá cổ phiếu phải lớn hơn 0.")
        sys.exit(1)
    if action.lower() not in ['buy', 'sell']:
        print("Lỗi: Hành động phải là 'buy' hoặc 'sell'")
        sys.exit(1)
    if allocation not in ['short-term', 'long-term']:
        print("Lỗi: Chiến lược phải là 'short-term' hoặc 'long-term'")
        sys.exit(1)
        
    success = update_holdings(ticker, action, shares, price, allocation, dry_run=dry_run)
    if success and not dry_run:
        record_transaction(ticker, action, shares, price, allocation)

if __name__ == '__main__':
    main()
