#!/usr/bin/env python3
"""
pm_orchestrator.py — Điều phối toàn bộ workflow Vietnam Stock Portfolio.

Chạy theo thứ tự:
  1. Preflight checks (mozyfin, portfolio, fonts...)
  2. portfolio_tracker.py  — cập nhật giá và Dashboard
  3. st_trader_scan.py     — quét tín hiệu kỹ thuật ngắn hạn
  4. lt_investor_report.py — báo cáo cơ bản dài hạn
  5. generate_pdf_report.py — xuất PDF tổng hợp
  6. Ghi run_summary.json

Tùy chọn:
  --non-interactive   Bỏ qua tất cả Y/n prompt, luôn chọn Yes
  --skip-lt           Bỏ qua bước phân tích dài hạn (tiết kiệm thời gian)
  --pdf-only          Chỉ xuất PDF từ dữ liệu hiện có
  --with-screeners    Tự động chạy CANSLIM và VCP screener cho danh mục & watchlist
"""
import os
import sys
import subprocess
import json
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

console = Console(highlight=False)

# Thêm thư mục scripts vào sys.path để import preflight
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from preflight import run_preflight, load_portfolio, load_watchlist, PLUGIN_DIR, REPORTS_DIR


def run_script(script_name: str, env: dict = None) -> tuple:
    """
    Chạy một Python script và chuyển tiếp output ra stdout.
    Trả về (success: bool, stdout: str, stderr: str).
    """
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    console.print(f"\n[bold blue]>>> Đang chạy: {script_name}...[/]")

    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=run_env
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            console.print(f"[dim red]--- stderr ---\n{result.stderr}[/]")
        success = result.returncode == 0
        return success, result.stdout, result.stderr
    except Exception as e:
        console.print(f"[bold red]Không thể chạy {script_name}: {e}[/]")
        return False, "", str(e)


def print_banner():
    console.print(Panel(
        "[bold green]VIETNAM STOCK MULTI-AGENT PORTFOLIO SYSTEM[/]\n"
        "[dim]Chạy toàn bộ workflow: Dashboard → Kỹ thuật → Cơ bản → PDF[/]",
        border_style="green"
    ))


def save_run_summary(results: dict, cfg: dict):
    """Ghi tóm tắt lần chạy vào run_summary.json."""
    summary = {
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_source": "vnstock (fallback)" if cfg.get('use_vnstock_fallback') else "mozyfin",
        "steps": results,
        "plugin_dir": cfg.get('plugin_dir'),
        "reports_dir": cfg.get('reports_dir'),
    }
    summary_path = os.path.join(REPORTS_DIR, 'run_summary.json')
    try:
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        console.print(f"[dim]Đã lưu tóm tắt chạy tại: {summary_path}[/]")
    except Exception as e:
        console.print(f"[yellow][!] Không thể ghi run_summary.json: {e}[/]")


def print_summary_table(results: dict):
    """In bảng kết quả các bước."""
    table = Table(title="Kết Quả Workflow", show_header=True, header_style="bold cyan")
    table.add_column("Bước", style="cyan", min_width=30)
    table.add_column("Kết quả", justify="center", min_width=10)
    for step, ok in results.items():
        status = "[bold green]✓ OK[/]" if ok else "[bold red]✗ LỖI[/]"
        table.add_row(step, status)
    console.print(table)


def main():
    non_interactive = '--non-interactive' in sys.argv
    skip_lt         = '--skip-lt' in sys.argv
    pdf_only        = '--pdf-only' in sys.argv
    with_screeners  = '--with-screeners' in sys.argv

    print_banner()

    # ── Preflight checks ──────────────────────────────────────────────────────
    console.print("\n[bold][ Kiểm tra tiền điều kiện ][/]")
    cfg = run_preflight(
        need_mozyfin=True,
        need_portfolio=True,
        need_fonts=True,
        need_st_reports=False,        # orchestrator sẽ chạy st_trader_scan.py
        non_interactive=non_interactive,
    )

    if not cfg['proceed']:
        console.print("\n[bold red]Workflow bị dừng theo yêu cầu.[/]")
        return

    # Truyền cài đặt nguồn dữ liệu cho tất cả sub-script qua env var
    env_overrides = {}
    if cfg['use_vnstock_fallback']:
        env_overrides['FORCE_VNSTOCK'] = '1'
    if cfg['use_watchlist']:
        env_overrides['USE_WATCHLIST'] = '1'
    if cfg['use_fallback_font']:
        env_overrides['USE_FALLBACK_FONT'] = '1'

    results = {}

    if not pdf_only:
        # ── Bước 1: Cập nhật giá và Dashboard ────────────────────────────────
        ok, _, _ = run_script("portfolio_tracker.py", env=env_overrides)
        results["1. Portfolio Tracker (Dashboard)"] = ok
        if not ok:
            console.print("[yellow][!] Portfolio tracker gặp lỗi. Tiếp tục với dữ liệu đã cache...[/]")

        # ── Bước 2: Quét kỹ thuật ngắn hạn ──────────────────────────────────
        ok, _, _ = run_script("st_trader_scan.py", env=env_overrides)
        results["2. ST Trader Scan (Kỹ thuật)"] = ok

        # ── Bước 3: Báo cáo cơ bản dài hạn ──────────────────────────────────
        if skip_lt:
            console.print("\n[dim]Bỏ qua bước phân tích dài hạn (--skip-lt)[/]")
            results["3. LT Investor Report (Cơ bản)"] = None
        else:
            ok, _, _ = run_script("lt_investor_report.py", env=env_overrides)
            results["3. LT Investor Report (Cơ bản)"] = ok

        # ── Bước 3.5: Chạy các bộ lọc (CANSLIM / VCP) ───────────────────────
        if with_screeners:
            console.print("\n[bold blue]>>> Đang chạy các bộ lọc (CANSLIM & VCP)...[/]")
            _, _, active = load_portfolio()
            watchlist = load_watchlist()
            
            symbols = set([item.get('symbol') for item in active if item.get('symbol')] + 
                          [item.get('symbol') for item in watchlist if item.get('symbol')])
            
            if symbols:
                universe_str = ",".join(symbols)
                
                # PYTHONPATH để các script import được module dùng chung
                scr_env = env_overrides.copy()
                scr_env['PYTHONPATH'] = SCRIPTS_DIR
                
                canslim_script = os.path.join(PLUGIN_DIR, "skills", "canslim-screener", "scripts", "screen_canslim.py")
                vcp_script = os.path.join(PLUGIN_DIR, "skills", "vcp-screener", "scripts", "screen_vcp.py")
                
                if os.path.exists(canslim_script):
                    console.print(f"[dim]Chạy CANSLIM cho {len(symbols)} mã...[/]")
                    subprocess.run([sys.executable, canslim_script, "--universe", universe_str], env=scr_env)
                
                if os.path.exists(vcp_script):
                    console.print(f"[dim]Chạy VCP cho {len(symbols)} mã...[/]")
                    subprocess.run([sys.executable, vcp_script, "--universe", universe_str], env=scr_env)
                
                results["3.5. Auto Screeners"] = True
            else:
                console.print("[dim]Không có mã nào trong danh mục hoặc watchlist để chạy bộ lọc.[/]")

    # ── Bước 4: Xuất PDF ──────────────────────────────────────────────────────
    ok, _, _ = run_script("generate_pdf_report.py", env=env_overrides)
    results["4. Generate PDF Report"] = ok

    # ── Tóm tắt ───────────────────────────────────────────────────────────────
    console.print("\n")
    print_summary_table(results)
    save_run_summary(results, cfg)

    pdf_path = os.path.join(REPORTS_DIR, 'portfolio_recommendations.pdf')
    if os.path.exists(pdf_path):
        console.print(f"\n[bold green]✓ PDF đã sẵn sàng:[/] {pdf_path}")

    console.print(Panel(
        "[bold green]WORKFLOW HOÀN TẤT[/]",
        border_style="green"
    ))


if __name__ == '__main__':
    main()
