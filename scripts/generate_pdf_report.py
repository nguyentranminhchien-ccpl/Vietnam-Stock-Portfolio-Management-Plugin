#!/usr/bin/env python3
"""
generate_pdf_report.py — Xuất báo cáo PDF tổng hợp danh mục đầu tư.

Đọc từ:
  - data/portfolio.json         (tổng quan danh mục)
  - reports/*_st_scan_*.md      (phân tích kỹ thuật ngắn hạn)
  - reports/buffett_report_*.json / canslim_screener_*.json (bộ lọc)
  - reports/*_report.md         (phân tích cơ bản dài hạn)

Ghi ra: reports/portfolio_recommendations.pdf

Env vars:
  USE_FALLBACK_FONT=1   Dùng font Helvetica thay Roboto (tiếng Việt hạn chế)
"""
import os
import sys
import json
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from preflight import (
    run_preflight, PLUGIN_DIR, DATA_DIR, REPORTS_DIR,
    PORTFOLIO_FILE, FONTS_DIR, load_portfolio
)

USE_FALLBACK_FONT = os.environ.get('USE_FALLBACK_FONT', '0') == '1'

OUTPUT_PDF = os.path.join(REPORTS_DIR, 'portfolio_recommendations.pdf')


class PortfolioPDF:
    """Wrapper quanh FPDF với font đã được cấu hình."""

    def __init__(self, use_fallback: bool = False):
        from fpdf import FPDF

        class _PDF(FPDF):
            def header(self_):
                self_.set_font(self._font, 'B', 14)
                self_.cell(0, 10, 'BÁO CÁO KHUYẾN NGHỊ DANH MỤC ĐẦU TƯ', 0, 1, 'C')
                self_.set_font(self._font, '', 9)
                self_.cell(
                    0, 5,
                    f'Ngày tạo: {datetime.now().strftime("%Y-%m-%d %H:%M")} '
                    f'| Hệ thống Quản lý Danh mục Việt Nam',
                    0, 1, 'C'
                )
                self_.line(10, 27, 200, 27)
                self_.ln(5)

            def footer(self_):
                self_.set_y(-15)
                self_.set_font(self._font, '', 8)
                self_.cell(0, 10, f'Trang {self_.page_no()}', 0, 0, 'C')

        self._use_fallback = use_fallback
        self._font = 'Helvetica' if use_fallback else 'Roboto'
        self.pdf = _PDF()
        self.pdf._font = self._font  # truyền font name vào inner class

        if not use_fallback:
            font_reg  = os.path.join(FONTS_DIR, 'Roboto-Regular.ttf')
            font_bold = os.path.join(FONTS_DIR, 'Roboto-Bold.ttf')
            try:
                self.pdf.add_font('Roboto', '',  font_reg)
                self.pdf.add_font('Roboto', 'B', font_bold)
            except Exception as e:
                print(f"[!] Không load được Roboto: {e}. Dùng Helvetica.")
                self._font = 'Helvetica'
                self.pdf._font = 'Helvetica'


def safe_text(text: str, max_len: int = None) -> str:
    """Đảm bảo chuỗi an toàn khi in ra PDF."""
    if text is None:
        return ''
    s = str(text)
    if max_len:
        s = s[:max_len]
    return s


def load_latest_json(prefix: str) -> dict | None:
    """Load file JSON mới nhất trong REPORTS_DIR khớp với prefix."""
    if not os.path.exists(REPORTS_DIR):
        return None
    files = sorted(
        [f for f in os.listdir(REPORTS_DIR) if f.startswith(prefix) and f.endswith('.json')],
        reverse=True
    )
    if not files:
        return None
    try:
        with open(os.path.join(REPORTS_DIR, files[0]), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def load_st_reports() -> list:
    """Tải danh sách báo cáo ST scan mới nhất."""
    if not os.path.exists(REPORTS_DIR):
        return []
    # Pattern đúng: {TICKER}_st_scan_{YYYYMMDD}.md
    files = sorted(
        [f for f in os.listdir(REPORTS_DIR) if '_st_scan_' in f and f.endswith('.md')],
        reverse=True
    )
    results = []
    seen_tickers = set()
    for fname in files:
        ticker = fname.split('_st_scan_')[0]
        if ticker not in seen_tickers:
            seen_tickers.add(ticker)
            fpath = os.path.join(REPORTS_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    results.append({'ticker': ticker, 'content': f.read()[:1000]})
            except Exception:
                pass
    return results


def load_lt_reports() -> list:
    """Tải danh sách báo cáo phân tích cơ bản."""
    if not os.path.exists(REPORTS_DIR):
        return []
    files = [f for f in os.listdir(REPORTS_DIR) if f.endswith('_report.md')]
    results = []
    for fname in sorted(files):
        ticker = fname.replace('_report.md', '')
        fpath  = os.path.join(REPORTS_DIR, fname)
        try:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()[:1200]
            results.append({'ticker': ticker, 'content': content})
        except Exception:
            pass
    return results


def create_pdf_report():
    # ── Tải dữ liệu ───────────────────────────────────────────────────────────
    ok, portfolio_data, active_holdings = load_portfolio()
    latest_canslim = load_latest_json('canslim_screener_')
    latest_vcp     = load_latest_json('vcp_screener_')
    latest_buffett = load_latest_json('buffett_report_')
    st_reports     = load_st_reports()
    lt_reports     = load_lt_reports()

    if not ok and not portfolio_data:
        print(f"[!] Không tìm thấy dữ liệu portfolio. PDF sẽ tạo với dữ liệu trống.")
        portfolio_data = {}

    # ── Khởi tạo PDF ──────────────────────────────────────────────────────────
    wrapper = PortfolioPDF(use_fallback=USE_FALLBACK_FONT)
    pdf     = wrapper.pdf
    font    = wrapper._font
    pdf.add_page()

    # ── SECTION 1: Tổng quan danh mục ─────────────────────────────────────────
    pdf.set_font(font, 'B', 12)
    pdf.cell(0, 10, '1. TỔNG QUAN DANH MỤC & HIỆU QUẢ ĐẦU TƯ', 0, 1, 'L')
    pdf.ln(2)

    if portfolio_data:
        pdf.set_font(font, '', 10)
        pdf.cell(95, 6, safe_text(f'Tổng giá trị tài sản: {portfolio_data.get("total_portfolio_value_vnd", 0):,.0f} VND'), 0, 0)
        pdf.cell(95, 6, safe_text(f'Số dư tiền mặt: {portfolio_data.get("cash_balance_vnd", 0):,.0f} VND'), 0, 1)
        pdf.cell(95, 6, safe_text(f'Giá trị cổ phiếu: {portfolio_data.get("total_stock_value_vnd", 0):,.0f} VND'), 0, 0)
        pnl     = portfolio_data.get("total_pnl_vnd", 0)
        pnl_pct = portfolio_data.get("total_pnl_pct", 0)
        pdf.cell(95, 6, safe_text(f'Tổng P&L: {pnl:+,.0f} VND ({pnl_pct:+.2f}%)'), 0, 1)
        pdf.ln(4)

        # Bảng holdings
        pdf.set_fill_color(230, 230, 230)
        pdf.set_font(font, 'B', 9)
        for header, w in [('Mã CP', 20), ('Chiến lược', 25), ('SL', 18),
                           ('Giá vốn', 30), ('Giá HT', 28), ('Giá trị HT', 35), ('P&L (%)', 34)]:
            pdf.cell(w, 8, header, 1, 0, 'C', True)
        pdf.ln()

        pdf.set_font(font, '', 9)
        for h in active_holdings:
            alloc = 'Dài hạn' if h.get('allocation') == 'long-term' else 'Ngắn hạn'
            pdf.cell(20, 7, safe_text(h['ticker']), 1, 0, 'C')
            pdf.cell(25, 7, safe_text(alloc), 1, 0, 'C')
            pdf.cell(18, 7, safe_text(f"{h.get('shares', 0):,}"), 1, 0, 'C')
            pdf.cell(30, 7, safe_text(f"{h.get('basis_price', 0):,.0f}"), 1, 0, 'R')
            pdf.cell(28, 7, safe_text(f"{h.get('current_price', h.get('basis_price', 0)):,.0f}"), 1, 0, 'R')
            pdf.cell(35, 7, safe_text(f"{h.get('current_value', 0):,.0f}"), 1, 0, 'R')
            pnl_val = h.get('pnl', 0)
            pnl_pct = h.get('pnl_pct', 0)
            pdf.cell(34, 7, safe_text(f"{pnl_val:+,.0f} ({pnl_pct:+.2f}%)"), 1, 1, 'C')
    else:
        pdf.set_font(font, '', 10)
        pdf.cell(0, 10, 'Không có dữ liệu danh mục. Vui lòng chạy portfolio_tracker.py trước.', 0, 1)
    pdf.ln(6)

    # ── SECTION 2: Phân tích kỹ thuật ngắn hạn ────────────────────────────────
    pdf.set_font(font, 'B', 12)
    pdf.cell(0, 10, '2. PHÂN TÍCH KỸ THUẬT NGẮN HẠN (SWING TRADING)', 0, 1, 'L')
    pdf.ln(2)
    pdf.set_font(font, '', 10)

    if st_reports:
        for report in st_reports[:4]:
            pdf.set_font(font, 'B', 10)
            pdf.cell(0, 7, safe_text(f"--- {report['ticker']} ---"), 0, 1)
            pdf.set_font(font, '', 9)
            pdf.set_x(12)
            pdf.multi_cell(0, 5, safe_text(report['content'], 800))
            pdf.ln(2)
    else:
        pdf.set_x(10)
        pdf.multi_cell(
            0, 5,
            'Chưa có dữ liệu phân tích kỹ thuật.\n'
            'Vui lòng chạy: python st_trader_scan.py'
        )
    pdf.ln(6)

    # ── SECTION 3: Phân tích cơ bản dài hạn ──────────────────────────────────
    pdf.set_font(font, 'B', 12)
    pdf.cell(0, 10, '3. PHÂN TÍCH CƠ BẢN & ĐỊNH GIÁ DÀI HẠN', 0, 1, 'L')
    pdf.ln(2)

    if lt_reports:
        for report in lt_reports:
            pdf.set_font(font, 'B', 10)
            pdf.cell(0, 7, safe_text(report['ticker']), 0, 1)
            pdf.set_font(font, '', 9)
            pdf.set_x(12)
            # Chỉ lấy văn bản ASCII + Latin để tránh lỗi font fallback
            content = report['content']
            if USE_FALLBACK_FONT:
                content = content.encode('ascii', 'replace').decode('ascii')
            pdf.multi_cell(0, 5, safe_text(content, 1000))
            pdf.ln(3)
    else:
        pdf.set_font(font, '', 10)
        pdf.set_x(10)
        pdf.multi_cell(
            0, 5,
            'Chưa có báo cáo phân tích cơ bản.\n'
            'Vui lòng chạy: python lt_investor_report.py'
        )
    pdf.ln(6)

    # ── SECTION 4: Kết quả bộ lọc (Buffett / CANSLIM / VCP) ──────────────────
    pdf.set_font(font, 'B', 12)
    pdf.cell(0, 10, '4. KẾT QUẢ BỘ LỌC CỔ PHIẾU (BUFFETT / CANSLIM / VCP)', 0, 1, 'L')
    pdf.ln(2)

    # Buffett summary
    if latest_buffett:
        pdf.set_font(font, 'B', 10)
        pdf.cell(0, 7, 'Buffett Margin of Safety:', 0, 1)
        pdf.set_font(font, '', 9)
        pdf.set_fill_color(240, 240, 240)
        for header, w in [('Mã CP', 22), ('Điểm', 20), ('FCF Yield', 28),
                           ('ROIC', 22), ('P/E', 22), ('D/E', 22), ('Sinh lời', 24)]:
            pdf.cell(w, 8, header, 1, 0, 'C', True)
        pdf.ln()
        for r in latest_buffett.get('candidates', []):
            pe_raw  = r.get('pe_ratio', 0)
            pe_disp = 'N/A' if pe_raw >= 500 else f"{pe_raw:.1f}"
            fcf_raw = r.get('fcf_yield', 0)
            fcf_disp = 'N/A (proxy)' if fcf_raw == 0 else f"{fcf_raw:.1f}%"
            pdf.cell(22, 7, safe_text(r.get('ticker', '')), 1, 0, 'C')
            pdf.cell(20, 7, safe_text(f"{r.get('total_score', 0):.0f}/100"), 1, 0, 'C')
            pdf.cell(28, 7, safe_text(fcf_disp), 1, 0, 'C')
            pdf.cell(22, 7, safe_text(f"{r.get('roic', 0):.1f}%"), 1, 0, 'C')
            pdf.cell(22, 7, safe_text(pe_disp), 1, 0, 'C')
            pdf.cell(22, 7, safe_text(f"{r.get('debt_to_equity', 0):.2f}"), 1, 0, 'C')
            pdf.cell(24, 7, safe_text(f"{r.get('profitable_years', 0)}/5"), 1, 1, 'C')
        pdf.ln(4)

    # CANSLIM summary
    if latest_canslim:
        pdf.set_font(font, 'B', 10)
        pdf.cell(0, 7, 'CANSLIM Screener:', 0, 1)
        pdf.set_font(font, '', 9)
        pdf.cell(0, 5, safe_text(
            f"Thị trường VNINDEX: {latest_canslim.get('market_trend','N/A')} "
            f"(Điểm: {latest_canslim.get('market_score',0)}/100)"
        ), 0, 1)
        pdf.ln(2)
        pdf.set_fill_color(240, 240, 240)
        for header, w in [('Mã CP', 20), ('Điểm CANSLIM', 30), ('Phân loại', 30),
                           ('Nhịp VCP', 28), ('Khuyến nghị', 82)]:
            pdf.cell(w, 8, header, 1, 0, 'C', True)
        pdf.ln()
        for r in latest_canslim.get('candidates', []):
            vcp_c   = 'N/A'
            if latest_vcp:
                vcp_m = next((x for x in latest_vcp.get('candidates', []) if x['ticker'] == r['ticker']), None)
                if vcp_m:
                    vcp_c = f"{vcp_m['contraction_count']} lần"
            pdf.cell(20, 7, safe_text(r['ticker']), 1, 0, 'C')
            pdf.cell(30, 7, safe_text(f"{r['composite_score']:.1f}"), 1, 0, 'C')
            pdf.cell(30, 7, safe_text(r['rating'].split(' ')[0]), 1, 0, 'C')
            pdf.cell(28, 7, safe_text(vcp_c), 1, 0, 'C')
            pdf.cell(82, 7, safe_text(r.get('recommendation', '')[:42]), 1, 1, 'L')
        pdf.ln(4)

    if not latest_buffett and not latest_canslim:
        pdf.set_font(font, '', 10)
        pdf.set_x(10)
        pdf.multi_cell(
            0, 5,
            'Chưa có dữ liệu bộ lọc.\n'
            'Vui lòng yêu cầu subagent [stock_screener] chạy bộ lọc CANSLIM/VCP/Buffett.'
        )

    # ── Xuất PDF ──────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(OUTPUT_PDF), exist_ok=True)
    try:
        pdf.output(OUTPUT_PDF)
        print(f"[+] PDF đã tạo thành công: {OUTPUT_PDF}")
    except Exception as e:
        print(f"[-] Lỗi khi xuất PDF: {e}")


def main():
    global USE_FALLBACK_FONT

    # Preflight khi chạy độc lập
    if not os.environ.get('USE_FALLBACK_FONT') and not os.environ.get('FORCE_VNSTOCK'):
        cfg = run_preflight(
            need_mozyfin=False,
            need_portfolio=True,
            need_fonts=True,
            need_st_reports=True,
        )
        if not cfg['proceed']:
            return
        USE_FALLBACK_FONT = cfg['use_fallback_font']

    create_pdf_report()


if __name__ == '__main__':
    main()
