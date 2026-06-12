import os
import json
from datetime import datetime
import sys

def load_json(file_path, default):
    if not os.path.exists(file_path):
        return default
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def record_transaction(ticker, action, shares, price, allocation):
    tx_file = 'transactions.json'
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

def update_holdings(ticker, action, shares, price, allocation):
    portfolio_file = 'portfolio.json'
    portfolio = load_json(portfolio_file, {"cash_balance_vnd": 0, "holdings": []})
    
    total_val = shares * price
    
    # 1. Update Cash Balance
    if action.lower() == 'buy':
        if portfolio['cash_balance_vnd'] < total_val:
            print(f"[-] LỖI: Không đủ tiền mặt! Cần {total_val:,.0f} VND, hiện có {portfolio['cash_balance_vnd']:,.0f} VND.")
            return False
        portfolio['cash_balance_vnd'] -= total_val
    elif action.lower() == 'sell':
        portfolio['cash_balance_vnd'] += total_val
        
    # 2. Update Holdings list
    holdings = portfolio.get('holdings', [])
    found = False
    
    for idx, holding in enumerate(holdings):
        # Match ticker and strategy bucket
        if holding['ticker'] == ticker and holding['allocation'] == allocation:
            found = True
            if action.lower() == 'buy':
                # Recalculate average cost basis
                curr_shares = holding['shares']
                curr_basis = holding['basis_price']
                
                new_shares = curr_shares + shares
                new_basis = ((curr_shares * curr_basis) + total_val) / new_shares
                
                holding['shares'] = new_shares
                holding['basis_price'] = round(new_basis, 2)
                print(f"[+] Cập nhật vị thế: {ticker} đạt {new_shares:,} CP, giá vốn mới: {new_basis:,.0f} VND.")
            elif action.lower() == 'sell':
                curr_shares = holding['shares']
                if curr_shares < shares:
                    print(f"[-] LỖI: Vị thế không đủ cổ phiếu để bán! Có {curr_shares:,} CP, yêu cầu bán {shares:,} CP.")
                    return False
                
                new_shares = curr_shares - shares
                if new_shares == 0:
                    holdings.pop(idx)
                    print(f"[+] Đã bán hết toàn bộ vị thế {ticker} ({allocation}).")
                else:
                    holding['shares'] = new_shares
                    print(f"[+] Giảm vị thế: {ticker} còn {new_shares:,} CP.")
            break
            
    if not found:
        if action.lower() == 'buy':
            # Create new holding record
            new_holding = {
                "ticker": ticker,
                "shares": shares,
                "basis_price": price,
                "allocation": allocation
            }
            holdings.append(new_holding)
            print(f"[+] Mở vị thế mới: {shares:,} CP {ticker} ({allocation}) giá {price:,.0f} VND.")
        elif action.lower() == 'sell':
            print(f"[-] LỖI: Không tìm thấy vị thế {ticker} ({allocation}) để bán.")
            return False
            
    portfolio['holdings'] = holdings
    save_json(portfolio_file, portfolio)
    return True

def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    # Parse CLI Arguments: python update_portfolio.py [buy/sell] [ticker] [shares] [price] [allocation]
    if len(sys.argv) < 6:
        print("Cú pháp: python update_portfolio.py [buy/sell] [ticker] [shares] [price] [short-term/long-term]")
        sys.exit(1)
        
    action = sys.argv[1]
    ticker = sys.argv[2].upper()
    shares = int(sys.argv[3])
    price = float(sys.argv[4])
    allocation = sys.argv[5].lower()
    
    if action.lower() not in ['buy', 'sell']:
        print("Lỗi: Hành động phải là 'buy' hoặc 'sell'")
        sys.exit(1)
        
    if allocation not in ['short-term', 'long-term']:
        print("Lỗi: Chiến lược phải là 'short-term' hoặc 'long-term'")
        sys.exit(1)
        
    success = update_holdings(ticker, action, shares, price, allocation)
    if success:
        record_transaction(ticker, action, shares, price, allocation)

if __name__ == '__main__':
    main()
