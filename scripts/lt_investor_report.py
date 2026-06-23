#!/usr/bin/env python3
"""
lt_investor_report.py — Tải báo cáo phân tích cơ bản thô (Raw Data).

Chỉ chạy trên holdings có shares > 0.
Bỏ qua mã đã có báo cáo dưới 7 ngày tuổi.
"""
import os
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from preflight import (
    run_preflight, REPORTS_DIR,
    load_portfolio, load_watchlist
)
from vn_data_provider import generate_fundamental_report_vnstock

def generate_raw_data_report(ticker: str) -> str | None:
    """
    Tải số liệu tài chính thô lưu ra file markdown.
    """
    print(f"\n[*] Đang tải dữ liệu cơ bản thô cho {ticker}...")
    try:
        path = generate_fundamental_report_vnstock(ticker, save_dir=REPORTS_DIR)
        if path and os.path.exists(path):
            print(f"[+] Đã lưu dữ liệu thô: {path}")
            return path
    except Exception as e:
        print(f"[-] Thất bại khi tải dữ liệu cho {ticker}: {e}")
    
    return None


def main():
    # Preflight khi chạy độc lập
    if not os.environ.get('FORCE_VNSTOCK') and not os.environ.get('USE_WATCHLIST'):
        cfg = run_preflight(need_mozyfin=False, need_portfolio=True)
        if not cfg['proceed']:
            return

    # Đọc danh sách cổ phiếu — CHỈ shares > 0
    ok, portfolio, active_holdings = load_portfolio()
    tickers = [(h['ticker'], h.get('basis_price', 0)) for h in active_holdings]

    use_watchlist = os.environ.get('USE_WATCHLIST', '0') == '1'
    if use_watchlist or not tickers:
        watchlist = load_watchlist()
        for item in watchlist:
            sym = item.get('symbol', '')
            if sym and sym not in [t[0] for t in tickers]:
                tickers.append((sym, item.get('target_buy_vnd', 0)))

    if not tickers:
        print("Không có mã nào để tải dữ liệu.")
        return

    print("\n" + "=" * 70)
    print("          TẢI DỮ LIỆU CƠ BẢN DÀI HẠN (RAW DATA PRE-FETCH)")
    print("=" * 70)

    for ticker, basis_price in tickers:
        # Kiểm tra báo cáo đã tồn tại và còn mới (< 7 ngày)
        report_path = os.path.join(REPORTS_DIR, f"{ticker}_report.md")
        if os.path.exists(report_path):
            age_days = (time.time() - os.path.getmtime(report_path)) / 86400
            if age_days < 7:
                print(f"\n[+] {ticker}: Dữ liệu còn mới ({age_days:.1f} ngày tuổi) — bỏ qua.")
                if basis_price > 0:
                    current = next(
                        (h.get('current_price') for h in active_holdings if h['ticker'] == ticker),
                        basis_price
                    )
                    pnl_pct = (current - basis_price) / basis_price * 100 if basis_price > 0 else 0
                    print(f"    Giá vốn: {basis_price:,.0f}  Hiện tại: {current:,.0f}  PnL: {pnl_pct:+.2f}%")
                print("-" * 50)
                continue
            else:
                print(f"\n[!] {ticker}: Dữ liệu đã cũ ({age_days:.1f} ngày) — cập nhật lại...")

        generate_raw_data_report(ticker)
        print("-" * 50)

    print("=" * 70 + "\n")


if __name__ == '__main__':
    main()
