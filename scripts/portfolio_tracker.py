#!/usr/bin/env python3
"""
portfolio_tracker.py — Cập nhật giá và hiển thị Dashboard danh mục.

Đọc dữ liệu từ: data/portfolio.json (nguồn duy nhất)
Ghi kết quả về: data/portfolio.json (cập nhật giá hiện tại, PnL)

Env vars:
  FORCE_VNSTOCK=1   Bỏ qua Mozyfin, dùng vnstock trực tiếp
  USE_WATCHLIST=1   Hiển thị thêm cột watchlist sau bảng holdings
"""
import sys
import os
import json
import csv
import subprocess
import tempfile
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Thêm thư mục scripts vào path để import preflight và vn_data_provider
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from preflight import (
    run_preflight, PORTFOLIO_FILE, WATCHLIST_FILE,
    PLUGIN_DIR, DATA_DIR, REPORTS_DIR, load_portfolio, load_watchlist
)

console = Console(highlight=False)

FORCE_VNSTOCK = os.environ.get('FORCE_VNSTOCK', '0') == '1'
USE_WATCHLIST  = os.environ.get('USE_WATCHLIST', '0') == '1'


def get_latest_price(ticker: str) -> float | None:
    """
    Lấy giá đóng cửa mới nhất.
    Ưu tiên: Mozyfin → vnstock fallback.
    Nếu FORCE_VNSTOCK=1, bỏ qua Mozyfin.
    """
    if not FORCE_VNSTOCK:
        # Thử Mozyfin trước
        fd, temp_path = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        try:
            cmd = ["mozyfin", "ohlcv", ticker, "--limit", "1", "--csv", temp_path]
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace', timeout=15
            )
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                with open(temp_path, mode='r', encoding='utf-8') as f:
                    rows = list(csv.DictReader(f))
                    if rows and 'close' in rows[0]:
                        return float(rows[0]['close'])
        except Exception:
            pass
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # Fallback: vnstock
    try:
        from vn_data_provider import get_latest_price_vnstock
        price = get_latest_price_vnstock(ticker)
        if price is not None:
            return price
    except Exception as e:
        console.print(f"[dim red][-] vnstock fallback thất bại cho {ticker}: {e}[/]")

    return None


def main():
    # ── Nếu chạy độc lập, thực hiện preflight nhỏ gọn ─────────────────────────
    if not os.environ.get('FORCE_VNSTOCK') and not os.environ.get('USE_WATCHLIST'):
        cfg = run_preflight(need_mozyfin=True, need_portfolio=True, need_fonts=False)
        if not cfg['proceed']:
            return
        global FORCE_VNSTOCK, USE_WATCHLIST
        FORCE_VNSTOCK = cfg['use_vnstock_fallback']
        USE_WATCHLIST  = cfg['use_watchlist']

    # ── Đọc portfolio ──────────────────────────────────────────────────────────
    ok, portfolio, active_holdings = load_portfolio()
    if not ok:
        if USE_WATCHLIST:
            console.print("[yellow][!] Không có holdings thực. Hiển thị watchlist.[/]")
            active_holdings = []
        else:
            console.print(f"[bold red]Lỗi:[/] Không tìm thấy holdings trong {PORTFOLIO_FILE}")
            return

    cash = portfolio.get('cash_balance_vnd', 0.0)

    source_label = "vnstock" if FORCE_VNSTOCK else "Mozyfin"
    console.print(f"\n[bold yellow]Cập nhật giá từ {source_label}...[/]")

    # ── Fetch giá ─────────────────────────────────────────────────────────────
    price_cache = {}
    for h in active_holdings:
        ticker = h['ticker']
        price  = get_latest_price(ticker)
        if price is None:
            price = h.get('current_price', h['basis_price'])
            console.print(f"[dim yellow]  [{ticker}] Không lấy được giá mới — dùng giá cache ({price:,.0f})[/]")
        price_cache[ticker] = price

    total_cost  = sum(h['shares'] * h['basis_price'] for h in active_holdings)
    total_value = sum(h['shares'] * price_cache.get(h['ticker'], h['basis_price']) for h in active_holdings)
    total_portfolio_value = total_value + cash

    # ── Xây dựng bảng Dashboard ───────────────────────────────────────────────
    table = Table(
        title=f"[bold]VIETNAM STOCK PORTFOLIO DASHBOARD[/]  [dim]{datetime.now().strftime('%Y-%m-%d %H:%M')}[/]",
        show_header=True,
        header_style="bold magenta"
    )
    table.add_column("Ticker",     style="cyan",    justify="left",   min_width=9)
    table.add_column("Chiến lược",                  justify="center", min_width=10)
    table.add_column("SL",                          justify="right",  min_width=7)
    table.add_column("Giá vốn",                     justify="right",  min_width=10)
    table.add_column("Giá hiện tại",                justify="right",  min_width=12)
    table.add_column("Giá trị",                     justify="right",  min_width=13)
    table.add_column("P&L",                         justify="right",  min_width=15)
    table.add_column("P&L %",                       justify="right",  min_width=8)
    table.add_column("% DM",                        justify="right",  min_width=7)
    table.add_column("Stop Loss",  style="dim red", justify="right",  min_width=11)

    for h in active_holdings:
        ticker      = h['ticker']
        shares      = h['shares']
        basis_price = h['basis_price']
        allocation  = h['allocation']

        current_price = price_cache.get(ticker, basis_price)
        cost          = shares * basis_price
        value         = shares * current_price
        pnl           = value - cost
        pnl_pct       = (pnl / cost * 100) if cost > 0 else 0.0
        pct_port      = (value / total_portfolio_value * 100) if total_portfolio_value > 0 else 0.0
        stop_loss     = basis_price * 0.93  # 7% hard stop

        pnl_color = "green" if pnl >= 0 else "red"
        sl_color  = "yellow" if current_price < stop_loss * 1.05 else "dim"

        table.add_row(
            ticker,
            "DÀI HẠN" if allocation == 'long-term' else "NGẮN HẠN",
            f"{shares:,}",
            f"{basis_price:,.0f}",
            f"{current_price:,.0f}",
            f"{value:,.0f} VND",
            f"[{pnl_color}]{pnl:+,.0f}[/]",
            f"[{pnl_color}]{pnl_pct:+.2f}%[/]",
            f"{pct_port:.1f}%",
            f"[{sl_color}]{stop_loss:,.0f}[/]",
        )

        # Cập nhật lại vào dict để ghi file
        h['current_price'] = current_price
        h['current_value'] = value
        h['pnl']           = round(pnl, 0)
        h['pnl_pct']       = round(pnl_pct, 4)
        h['stop_loss_ref'] = round(stop_loss, 0)
        h['pct_portfolio'] = round(pct_port, 2)

    # ── Ghi lại portfolio.json (nguồn duy nhất) ────────────────────────────────
    portfolio['holdings']                  = active_holdings
    portfolio['total_stock_value_vnd']     = total_value
    portfolio['total_portfolio_value_vnd'] = total_value + cash
    portfolio['total_cost_vnd']            = total_cost
    portfolio['total_pnl_vnd']             = total_value - total_cost
    portfolio['total_pnl_pct']             = round(
        ((total_value - total_cost) / total_cost * 100) if total_cost > 0 else 0.0, 4
    )
    portfolio['last_updated']              = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as f:
        json.dump(portfolio, f, indent=2, ensure_ascii=False)

    # ── Hiển thị Dashboard ────────────────────────────────────────────────────
    console.print("\n")
    console.print(table)

    overall_pnl     = total_value - total_cost
    overall_pnl_pct = (overall_pnl / total_cost * 100) if total_cost > 0 else 0.0
    cash_pct        = (cash / total_portfolio_value * 100) if total_portfolio_value > 0 else 0.0
    equity_pct      = 100.0 - cash_pct
    pnl_color       = "green" if overall_pnl >= 0 else "red"

    summary_text = (
        f"[bold]Nguồn dữ liệu:[/bold]         {source_label}\n"
        f"[bold]Tổng giá vốn:[/bold]           {total_cost:>16,.0f} VND\n"
        f"[bold]Tổng giá trị CP:[/bold]        {total_value:>16,.0f} VND   "
        f"[dim](CP: {equity_pct:.1f}% | Cash: {cash_pct:.1f}%)[/dim]\n"
        f"[bold]Tiền mặt:[/bold]               {cash:>16,.0f} VND\n"
        f"[bold]Tổng tài sản:[/bold]           {total_portfolio_value:>16,.0f} VND\n\n"
        f"[bold]P&L danh mục:[/bold]           "
        f"[{pnl_color}]{overall_pnl:+,.0f} VND ({overall_pnl_pct:+.2f}%)[/]\n"
        f"[dim]Cập nhật lúc: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]"
    )
    console.print(Panel(summary_text, title="[bold cyan]📊 TÓM TẮT DANH MỤC[/]", border_style="blue"))

    # ── Hiển thị watchlist nếu có ─────────────────────────────────────────────
    watchlist = load_watchlist()
    if watchlist:
        wl_table = Table(title="📋 WATCHLIST — Đang Theo Dõi", header_style="bold yellow")
        wl_table.add_column("Ticker",     style="cyan", min_width=9)
        wl_table.add_column("Kế hoạch",               min_width=10)
        wl_table.add_column("Mua mục tiêu",            justify="right", min_width=14)
        wl_table.add_column("Lý do",                   min_width=40)
        for item in watchlist:
            wl_table.add_row(
                item.get('symbol', ''),
                item.get('allocation_plan', '').upper(),
                f"{item.get('target_buy_vnd', 0):,.0f} VND",
                item.get('reason', '')[:50],
            )
        console.print("\n")
        console.print(wl_table)

    console.print("\n")


if __name__ == '__main__':
    main()
