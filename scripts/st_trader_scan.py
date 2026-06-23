#!/usr/bin/env python3
"""
st_trader_scan.py — Quét tín hiệu kỹ thuật ngắn hạn cho toàn bộ danh mục.

Đọc từ:   data/portfolio.json (chỉ holdings có shares > 0)
Ghi vào:  reports/{TICKER}_st_scan_{YYYYMMDD}.md

Env vars:
  FORCE_VNSTOCK=1   Bỏ qua Mozyfin TA, tính chỉ báo từ vnstock
  USE_WATCHLIST=1   Quét cả danh sách watchlist
"""
import os
import sys
import json
import csv
import subprocess
import tempfile
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from preflight import (
    run_preflight, REPORTS_DIR,
    load_portfolio, load_watchlist
)

console = Console(highlight=False)

FORCE_VNSTOCK = os.environ.get('FORCE_VNSTOCK', '0') == '1'
USE_WATCHLIST  = os.environ.get('USE_WATCHLIST', '0') == '1'
TODAY_STR      = datetime.now().strftime('%Y%m%d')


def parse_risk_data(ticker: str) -> dict:
    """Lấy chỉ số rủi ro từ mozyfin risk (252 phiên)."""
    if FORCE_VNSTOCK:
        return {}
    try:
        cmd = ["mozyfin", "risk", ticker, "--limit", "252"]
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace', timeout=30
        )
        metrics = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("- ") and ":" in line:
                key, val = line[2:].split(":", 1)
                try:
                    metrics[key.strip()] = float(val.strip())
                except ValueError:
                    metrics[key.strip()] = val.strip()
        return metrics
    except Exception:
        return {}


def run_ta_scan(ticker: str):
    """
    Lấy dữ liệu TA (SMA20, SMA50, RSI14, MACD).
    Ưu tiên Mozyfin → vnstock fallback nếu FORCE_VNSTOCK=1 hoặc Mozyfin thất bại.
    Trả về (latest_dict, yesterday_dict) hoặc None.
    """
    if not FORCE_VNSTOCK:
        fd, temp_path = tempfile.mkstemp(suffix='.csv')
        os.close(fd)
        try:
            cmd = [
                "mozyfin", "ta", ticker,
                "--sma", "20,50", "--rsi", "14", "--macd",
                "--limit", "120", "--csv", temp_path
            ]
            subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace', timeout=30
            )
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                with open(temp_path, mode='r', encoding='utf-8') as f:
                    rows = list(csv.DictReader(f))
                # Kiểm tra các cột bắt buộc
                required_cols = {'close', 'sma_20', 'sma_50', 'rsi_14', 'macd', 'signal'}
                if rows and required_cols.issubset(rows[0].keys()) and len(rows) >= 2:
                    return rows[0], rows[1]
        except Exception:
            pass
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # Fallback vnstock
    try:
        from vn_data_provider import get_ta_data_vnstock
        result = get_ta_data_vnstock(ticker)
        if result is not None:
            return result
    except Exception as e:
        console.print(f"[dim red][-] vnstock TA fallback thất bại cho {ticker}: {e}[/]")

    return None


def safe_float(val, default=None) -> float | None:
    """Chuyển đổi giá trị sang float an toàn, trả về default nếu thất bại."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def analyze_ticker(ticker: str, basis_price: float, shares: int):
    """Phân tích và in kết quả kỹ thuật cho một mã cổ phiếu."""
    ta_data   = run_ta_scan(ticker)
    risk_data = parse_risk_data(ticker)

    if not ta_data:
        console.print(f"[yellow][-] Không lấy được dữ liệu TA cho {ticker}. Bỏ qua.[/]")
        return False

    today, yesterday = ta_data

    close_price    = safe_float(today.get('close'))
    sma_20         = safe_float(today.get('sma_20'))
    sma_50         = safe_float(today.get('sma_50'))
    rsi_14         = safe_float(today.get('rsi_14'))
    macd_today     = safe_float(today.get('macd'))
    sig_today      = safe_float(today.get('signal'))
    macd_yesterday = safe_float(yesterday.get('macd'))
    sig_yesterday  = safe_float(yesterday.get('signal'))

    if close_price is None:
        console.print(f"[yellow][-] Không có giá đóng cửa cho {ticker}. Bỏ qua.[/]")
        return False

    pnl_pct = ((close_price - basis_price) / basis_price * 100) if basis_price > 0 else 0.0

    # ── Đánh giá xu hướng ────────────────────────────────────────────────────
    trend = "TRUNG TÍNH"
    if sma_20 and sma_50:
        if close_price > sma_20 > sma_50:
            trend = "TĂNG (Close > SMA20 > SMA50)"
        elif close_price < sma_20 < sma_50:
            trend = "GIẢM (Close < SMA20 < SMA50)"

    # ── RSI ──────────────────────────────────────────────────────────────────
    rsi_status = "TRUNG TÍNH"
    if rsi_14 is not None:
        if rsi_14 > 70:
            rsi_status = f"QUÁ MUA ({rsi_14:.1f}) — Cảnh báo bán"
        elif rsi_14 < 30:
            rsi_status = f"QUÁ BÁN ({rsi_14:.1f}) — Theo dõi mua"
        else:
            rsi_status = f"TRUNG TÍNH ({rsi_14:.1f})"

    # ── MACD crossover ────────────────────────────────────────────────────────
    macd_cross = "TRUNG TÍNH"
    if all(v is not None for v in [macd_today, sig_today, macd_yesterday, sig_yesterday]):
        if macd_today > sig_today and macd_yesterday <= sig_yesterday:
            macd_cross = "VƯỢT LÊN (Bullish Crossover)"
        elif macd_today < sig_today and macd_yesterday >= sig_yesterday:
            macd_cross = "CẮT XUỐNG (Bearish Crossover)"

    # ── (Đã gỡ bỏ Khuyến nghị cơ học theo yêu cầu) ────────────────────────────

    # ── Hiển thị rich panel ───────────────────────────────────────────────────
    content = Text()
    pnl_style = "bold green" if pnl_pct >= 0 else "bold red"
    content.append(f"Giá hiện tại:    {close_price:,.0f} VND  (Giá vốn: {basis_price:,.0f})  PnL: ", style="none")
    content.append(f"{pnl_pct:+.2f}%", style=pnl_style)
    content.append("\n")

    trend_style = "bold green" if "TĂNG" in trend else "bold red" if "GIẢM" in trend else "bold yellow"
    content.append(f"Xu hướng (SMA):  {trend}\n", style=trend_style)

    rsi_style = "bold red" if "QUÁ MUA" in rsi_status else "bold green" if "QUÁ BÁN" in rsi_status else "none"
    content.append(f"RSI:             {rsi_status}\n", style=rsi_style)

    macd_style = "bold green" if "VƯỢT" in macd_cross else "bold red" if "CẮT" in macd_cross else "none"
    content.append(f"MACD:            {macd_cross}\n", style=macd_style)

    if risk_data:
        vol    = risk_data.get('volatility', 0) * 100
        sharpe = risk_data.get('sharpe', 0)
        max_dd = risk_data.get('maxDrawdown', 0) * 100
        content.append(f"Biến động 1 năm: {vol:.1f}%  |  Sharpe: {sharpe:.2f}  |  Max DD: {max_dd:.1f}%\n", style="cyan")

    # Không còn in Khuyến nghị cơ học

    console.print(Panel(content, title=f"[bold cyan]{ticker}[/] (Phân Tích Kỹ Thuật)", border_style="cyan"))

    # ── Lưu báo cáo Markdown (có timestamp) ──────────────────────────────────
    report_path = os.path.join(REPORTS_DIR, f"{ticker}_st_scan_{TODAY_STR}.md")
    md = [
        f"# Phân Tích Kỹ Thuật: {ticker}",
        f"**Ngày:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
        f"**Nguồn:** {'vnstock' if FORCE_VNSTOCK else 'Mozyfin'}\n",
        f"- Giá hiện tại: {close_price:,.0f} VND  (Giá vốn: {basis_price:,.0f}, PnL: {pnl_pct:+.2f}%)",
        f"- Xu hướng: {trend}",
        f"- RSI: {rsi_status}",
        f"- MACD: {macd_cross}",
    ]
    if risk_data:
        md.append(
            f"- Biến động 1 năm: {risk_data.get('volatility', 0)*100:.1f}%  "
            f"Sharpe: {risk_data.get('sharpe', 0):.2f}  "
            f"Max DD: {risk_data.get('maxDrawdown', 0)*100:.1f}%"
        )
    # Không ghi khuyến nghị cơ học vào báo cáo thô

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(md))
    console.print(f"[dim][+] Đã lưu: {report_path}[/]")
    return True


def main():
    global FORCE_VNSTOCK, USE_WATCHLIST

    # Preflight khi chạy độc lập
    if not os.environ.get('FORCE_VNSTOCK') and not os.environ.get('USE_WATCHLIST'):
        cfg = run_preflight(need_mozyfin=True, need_portfolio=True)
        if not cfg['proceed']:
            return
        FORCE_VNSTOCK = cfg['use_vnstock_fallback']
        USE_WATCHLIST  = cfg['use_watchlist']

    # Đọc danh sách cổ phiếu
    ok, portfolio, active_holdings = load_portfolio()
    tickers_to_scan = [(h['ticker'], h['basis_price'], h['shares']) for h in active_holdings]

    if USE_WATCHLIST or not tickers_to_scan:
        watchlist = load_watchlist()
        for item in watchlist:
            sym = item.get('symbol', '')
            if sym and sym not in [t[0] for t in tickers_to_scan]:
                tickers_to_scan.append((sym, item.get('target_buy_vnd', 0), 0))

    if not tickers_to_scan:
        console.print("[yellow]Không có mã cổ phiếu nào để quét.[/]")
        return

    console.print("\n[bold magenta]═══════════════════════════════════════════════[/]")
    console.print("[bold magenta]       QUÉT KỸ THUẬT NGẮN HẠN (ST SCAN)       [/]")
    console.print("[bold magenta]═══════════════════════════════════════════════[/]\n")

    success_count = 0
    for ticker, basis, shares in tickers_to_scan:
        ok = analyze_ticker(ticker, basis, shares)
        if ok:
            success_count += 1

    console.print(f"\n[bold green]Hoàn tất: {success_count}/{len(tickers_to_scan)} mã được phân tích.[/]")


if __name__ == '__main__':
    main()
