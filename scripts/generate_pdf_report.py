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
import re
import sys
import json
import time
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
        from fpdf.enums import XPos, YPos

        class _PDF(FPDF):
            def header(self_):
                self_.set_font(self._font, 'B', 14)
                self_.cell(0, 10, 'BÁO CÁO PHÂN TÍCH DANH MỤC ĐẦU TƯ', 0,
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
                self_.set_font(self._font, '', 9)
                self_.cell(
                    0, 5,
                    f'Ngày tạo: {datetime.now().strftime("%Y-%m-%d %H:%M")} '
                    f'| Hệ thống Quản lý Danh mục Việt Nam',
                    0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C'
                )
                self_.line(10, 27, 200, 27)
                self_.ln(5)

            def footer(self_):
                self_.set_y(-15)
                self_.set_font(self._font, '', 8)
                self_.cell(0, 10, f'Trang {self_.page_no()}', 0,
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

        self._XPos = XPos
        self._YPos = YPos

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
    """Đảm bảo chuỗi an toàn khi in ra PDF (tránh cắt đứt giữa ký tự multi-byte)."""
    if text is None:
        return ''
    s = str(text)
    if max_len and len(s) > max_len:
        # Cắt tại ranh giới từ gần nhất để tránh đứt câu
        truncated = s[:max_len]
        last_space = truncated.rfind(' ')
        if last_space > max_len // 2:
            truncated = truncated[:last_space]
        s = truncated + '...'
    return s


def load_latest_json(prefix: str, exclude_suffix: str = None) -> dict | None:
    """Load file JSON mới nhất trong REPORTS_DIR khớp với prefix."""
    if not os.path.exists(REPORTS_DIR):
        return None
    files = sorted(
        [
            f for f in os.listdir(REPORTS_DIR)
            if f.startswith(prefix) and f.endswith('.json')
            and (exclude_suffix is None or not f.endswith(exclude_suffix))
            and re.search(r'_\d{8}', f)  # Only dated files
        ],
        reverse=True
    )
    if not files:
        return None
    try:
        with open(os.path.join(REPORTS_DIR, files[0]), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def load_latest_md(prefix):
    """Load the most recent .md file with the given prefix from REPORTS_DIR."""
    try:
        files = sorted([f for f in os.listdir(REPORTS_DIR)
                        if f.startswith(prefix) and f.endswith('.md')], reverse=True)
        if not files:
            return None
        fpath = os.path.join(REPORTS_DIR, files[0])
        with open(fpath, encoding='utf-8', errors='replace') as f:
            return {'fname': files[0], 'content': f.read()[:3000]}
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
    """Load LT investor reports — prefers AI full-analysis over auto-generated stubs."""
    reports = {}
    if not os.path.isdir(REPORTS_DIR):
        return []

    def extract_ticker_and_priority(fname):
        """Returns (normalized_ticker, priority) or (None, 0)."""
        # AI full equity research reports (highest priority)
        if re.search(r'_equity_research_report\.md$', fname):
            base = re.sub(r'_equity_research_report\.md$', '', fname)
            return base.upper().replace('.VN', '').replace('-', ''), 2
        if re.search(r'_equity_research_\d{8}\.md$', fname):
            base = re.sub(r'_equity_research_\d{8}\.md$', '', fname)
            return base.upper().replace('.VN', '').replace('-', ''), 2
        # AI dated analysis
        if re.search(r'_analysis_\d{8}\.md$', fname):
            base = re.sub(r'_analysis_\d{8}\.md$', '', fname)
            return base.upper().replace('.VN', '').replace('-', ''), 2
        # Auto-generated fundamental report
        if fname.endswith('_report.md') and '_st_scan_' not in fname and '_equity_research' not in fname:
            base = fname[:-len('_report.md')]
            return base.upper().replace('.VN', '').replace('-', ''), 1
        return None, 0

    for fname in os.listdir(REPORTS_DIR):
        normalized_ticker, priority = extract_ticker_and_priority(fname)
        if normalized_ticker is None or priority == 0:
            continue
        fpath = os.path.join(REPORTS_DIR, fname)
        try:
            with open(fpath, encoding='utf-8', errors='replace') as f:
                content = f.read()[:6000]  # Increased from 1500 — AI reports are ~9300 chars
        except Exception:
            continue
        # Keep highest priority, or most recent (by filename) for same priority
        existing = reports.get(normalized_ticker)
        if existing is None or priority > existing['priority'] or (
                priority == existing['priority'] and fname > existing['fname']):
            reports[normalized_ticker] = {
                'ticker': normalized_ticker,
                'fname': fname,
                'content': content,
                'priority': priority,
                'report_type': 'Full Analysis' if priority == 2 else 'Auto (Raw Data)',
            }

    return list(reports.values())


def create_pdf_report():
    # ── Tải dữ liệu ───────────────────────────────────────────────────────────
    ok, portfolio_data, active_holdings = load_portfolio()
    latest_canslim = load_latest_json('canslim_screener_')
    latest_vcp     = load_latest_json('vcp_screener_')
    # Loại trừ buffett_report_watchlist.json khi tải report chính
    latest_buffett = load_latest_json('buffett_report_', exclude_suffix='_watchlist.json')
    st_reports     = load_st_reports()
    lt_reports     = load_lt_reports()
    
    # Load AI Portfolio Analysis
    ai_analysis_content = ""
    ai_path = os.path.join(REPORTS_DIR, 'ai_portfolio_analysis.md')
    if os.path.exists(ai_path):
        try:
            with open(ai_path, 'r', encoding='utf-8') as f:
                ai_analysis_content = f.read()
        except Exception:
            pass
    # Check staleness
    if ai_path and os.path.exists(ai_path):
        age_days = (time.time() - os.path.getmtime(ai_path)) / 86400
        if age_days > 14:
            stale_warning = f"\u26a0\ufe0f CANH BAO: Phan tich AI da {age_days:.0f} ngay tuoi. Can cap nhat.\n\n"
            ai_analysis_content = stale_warning + ai_analysis_content

    if not ok and not portfolio_data:
        print(f"[!] Không tìm thấy dữ liệu portfolio. PDF sẽ tạo với dữ liệu trống.")
        portfolio_data = {}

    # ── Khởi tạo PDF ──────────────────────────────────────────────────────────
    wrapper = PortfolioPDF(use_fallback=USE_FALLBACK_FONT)
    pdf     = wrapper.pdf
    font    = wrapper._font
    XPos    = wrapper._XPos
    YPos    = wrapper._YPos
    pdf.add_page()

    # ── SECTION 1: Tổng quan danh mục ─────────────────────────────────────────
    pdf.set_font(font, 'B', 12)
    pdf.cell(0, 10, '1. TỔNG QUAN DANH MỤC & HIỆU QUẢ ĐẦU TƯ', 0,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
    pdf.ln(2)

    if portfolio_data:
        pdf.set_font(font, '', 10)
        pdf.cell(95, 6, safe_text(f'Tổng giá trị tài sản: {portfolio_data.get("total_portfolio_value_vnd", 0):,.0f} VND'), 0,
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.cell(95, 6, safe_text(f'Số dư tiền mặt: {portfolio_data.get("cash_balance_vnd", 0):,.0f} VND'), 0,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(95, 6, safe_text(f'Giá trị cổ phiếu: {portfolio_data.get("total_stock_value_vnd", 0):,.0f} VND'), 0,
                 new_x=XPos.RIGHT, new_y=YPos.TOP)
        pnl     = portfolio_data.get("total_pnl_vnd", 0)
        pnl_pct = portfolio_data.get("total_pnl_pct", 0)
        pdf.cell(95, 6, safe_text(f'Tổng P&L: {pnl:+,.0f} VND ({pnl_pct:+.2f}%)'), 0,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

        # Bảng holdings
        pdf.set_fill_color(230, 230, 230)
        pdf.set_font(font, 'B', 9)
        for i, (header, w) in enumerate([('Mã CP', 20), ('Chiến lược', 25), ('SL', 18),
                                          ('Giá vốn', 30), ('Giá HT', 28), ('Giá trị HT', 35), ('P&L (%)', 34)]):
            is_last = i == 6
            pdf.cell(w, 8, header, 1,
                     new_x=XPos.LMARGIN if is_last else XPos.RIGHT,
                     new_y=YPos.NEXT if is_last else YPos.TOP,
                     align='C', fill=True)

        pdf.set_font(font, '', 9)
        for h in active_holdings:
            alloc = 'Dài hạn' if h.get('allocation') == 'long-term' else 'Ngắn hạn'
            pdf.cell(20, 7, safe_text(h['ticker']), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
            pdf.cell(25, 7, safe_text(alloc), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
            pdf.cell(18, 7, safe_text(f"{h.get('shares', 0):,}"), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
            pdf.cell(30, 7, safe_text(f"{h.get('basis_price', 0):,.0f}"), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='R')
            pdf.cell(28, 7, safe_text(f"{h.get('current_price', h.get('basis_price', 0)):,.0f}"), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='R')
            pdf.cell(35, 7, safe_text(f"{h.get('current_value', 0):,.0f}"), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='R')
            pnl_val = h.get('pnl', 0)
            pnl_pct = h.get('pnl_pct', 0)
            pdf.cell(34, 7, safe_text(f"{pnl_val:+,.0f} ({pnl_pct:+.2f}%)"), 1,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    else:
        pdf.set_font(font, '', 10)
        pdf.cell(0, 10, 'Không có dữ liệu danh mục. Vui lòng chạy portfolio_tracker.py trước.', 0,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(6)

    # ── SECTION 2: Phân tích kỹ thuật ngắn hạn ────────────────────────────────
    pdf.set_font(font, 'B', 12)
    pdf.cell(0, 10, '2. PHÂN TÍCH KỸ THUẬT NGẮN HẠN (SWING TRADING)', 0,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
    pdf.ln(2)
    pdf.set_font(font, '', 10)

    if st_reports:
        for report in st_reports[:4]:
            pdf.set_font(font, 'B', 10)
            pdf.cell(0, 7, safe_text(f"--- {report['ticker']} ---"), 0,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
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
    pdf.cell(0, 10, '3. PHÂN TÍCH CƠ BẢN & ĐỊNH GIÁ DÀI HẠN', 0,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
    pdf.ln(2)

    if lt_reports:
        for report in lt_reports:
            pdf.set_font(font, 'B', 10)
            pdf.cell(0, 7, safe_text(f"{report['ticker']} [{report.get('report_type', 'Report')}]"), 0,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font(font, '', 9)
            pdf.set_x(12)
            # Chỉ lấy văn bản ASCII + Latin để tránh lỗi font fallback
            content = report['content']
            if USE_FALLBACK_FONT:
                content = content.encode('ascii', 'replace').decode('ascii')
            pdf.multi_cell(0, 5, safe_text(content, 4000))
            pdf.ln(3)
            if pdf.get_y() > 240:
                pdf.add_page()
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
    pdf.cell(0, 10, '4. KẾT QUẢ BỘ LỌC CỔ PHIẾU (BUFFETT / CANSLIM / VCP)', 0,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
    pdf.ln(2)

    # Buffett summary
    if latest_buffett:
        # Hỗ trợ cả hai schema: 'results' (mới) và 'candidates' (cũ)
        buffett_rows = latest_buffett.get('results', latest_buffett.get('candidates', []))
        if buffett_rows:
            pdf.set_font(font, 'B', 10)
            pdf.cell(0, 7, 'Buffett Margin of Safety:', 0,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font(font, '', 9)
            pdf.set_fill_color(240, 240, 240)
            for i, (header, w) in enumerate([('Mã CP', 22), ('Điểm', 20), ('FCF Yield', 28),
                                              ('ROIC', 22), ('P/E', 22), ('D/E', 22), ('Sinh lời', 24)]):
                is_last = i == 6
                pdf.cell(w, 8, header, 1,
                         new_x=XPos.LMARGIN if is_last else XPos.RIGHT,
                         new_y=YPos.NEXT if is_last else YPos.TOP,
                         align='C', fill=True)
            for r in buffett_rows:
                metrics = r.get('metrics', r)
                pe_raw   = metrics.get('pe', r.get('pe_ratio', 0)) or 0
                pe_disp  = 'N/A' if pe_raw >= 500 else f"{pe_raw:.1f}"
                fcf_raw  = metrics.get('fcf_yield', r.get('fcf_yield', 0)) or 0
                fcf_disp = 'N/A' if fcf_raw == 0 else f"{fcf_raw:.1f}%"
                roic_val = metrics.get('roic', r.get('roic', 0)) or 0
                de_raw   = metrics.get('debt_to_equity', r.get('debt_to_equity', 0)) or 0
                de_disp  = f"{de_raw / 100.0:.2f}x" if de_raw > 5 else f"{de_raw:.2f}x"
                profit_y = metrics.get('positive_years', r.get('profitable_years', 0)) or 0
                score    = r.get('total_score', r.get('score', 0)) or 0
                ticker_b = r.get('symbol', r.get('ticker', ''))
                pdf.cell(22, 7, safe_text(ticker_b), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
                pdf.cell(20, 7, safe_text(f"{score:.0f}/100"), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
                pdf.cell(28, 7, safe_text(fcf_disp), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
                pdf.cell(22, 7, safe_text(f"{roic_val * 100:.1f}%" if roic_val < 5 else f"{roic_val:.1f}%"), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
                pdf.cell(22, 7, safe_text(pe_disp), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
                pdf.cell(22, 7, safe_text(de_disp), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
                pdf.cell(24, 7, safe_text(f"{profit_y}/5"), 1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
            pdf.ln(4)

    # CANSLIM summary
    if latest_canslim:
        # Hỗ trợ cả hai schema: 'results' (mới) và 'candidates' (cũ)
        canslim_rows = latest_canslim.get('results', latest_canslim.get('candidates', []))
        market_cond  = latest_canslim.get('metadata', {}).get('market_condition', {})
        market_trend = market_cond.get('trend', latest_canslim.get('market_trend', 'N/A'))
        market_score = market_cond.get('M_score', latest_canslim.get('market_score', 0))

        # Lấy VCP rows tương ứng
        vcp_rows = []
        if latest_vcp:
            vcp_rows = latest_vcp.get('results', latest_vcp.get('candidates', []))

        if canslim_rows:
            pdf.set_font(font, 'B', 10)
            pdf.cell(0, 7, 'CANSLIM Screener:', 0,
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font(font, '', 9)
            pdf.cell(0, 5, safe_text(
                f"Thị trường VNINDEX: {market_trend} "
                f"(Điểm M: {market_score}/100)"
            ), 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2)
            pdf.set_fill_color(240, 240, 240)
            for i, (header, w) in enumerate([('Mã CP', 20), ('Điểm CANSLIM', 30), ('Phân loại', 30),
                                              ('Nhịp VCP', 28), ('Khuyến nghị', 82)]):
                is_last = i == 4
                pdf.cell(w, 8, header, 1,
                         new_x=XPos.LMARGIN if is_last else XPos.RIGHT,
                         new_y=YPos.NEXT if is_last else YPos.TOP,
                         align='C', fill=True)
            for r in canslim_rows:
                ticker_r = r.get('symbol', r.get('ticker', ''))
                vcp_c    = 'N/A'
                vcp_match = next(
                    (x for x in vcp_rows
                     if x.get('symbol', x.get('ticker', '')) == ticker_r), None
                )
                if vcp_match:
                    cnt = vcp_match.get('contraction_count', vcp_match.get('contractions', 'N/A'))
                    vcp_c = f"{cnt} lần" if cnt != 'N/A' else 'N/A'
                score_val = r.get('composite_score', r.get('score', 0)) or 0
                rating    = r.get('rating', 'N/A')
                guidance  = r.get('guidance', r.get('rating_description', ''))
                pdf.cell(20, 7, safe_text(ticker_r), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
                pdf.cell(30, 7, safe_text(f"{score_val:.1f}"), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
                pdf.cell(30, 7, safe_text(rating.split(' ')[0]), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
                pdf.cell(28, 7, safe_text(vcp_c), 1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
                pdf.cell(82, 7, safe_text(guidance, 55), 1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
            pdf.ln(4)

    if not latest_buffett and not latest_canslim:
        pdf.set_font(font, '', 10)
        pdf.set_x(10)
        pdf.multi_cell(
            0, 5,
            'Chua co du lieu bo loc.\n'
            'Vui long yeu cau subagent [stock_screener] chay bo loc CANSLIM/VCP/Buffett.'
        )
    elif latest_buffett and not latest_buffett.get('results', latest_buffett.get('candidates')):
        pdf.set_font(font, '', 10)
        pdf.set_x(10)
        pdf.multi_cell(0, 5, 'Bo loc Buffett: Khong co ung vien nao du tieu chi.')

    # ── SECTION 5: Phân Tích Tổng Hợp Từ AI ────────────────────────────────
    pdf.ln(6)
    pdf.set_font(font, 'B', 12)
    pdf.cell(0, 10, '5. NHẬN ĐỊNH VÀ CHIẾN LƯỢC TỪ AI (PORTFOLIO MANAGER)', 0,
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
    pdf.ln(2)
    
    if ai_analysis_content:
        pdf.set_font(font, '', 9)
        pdf.set_x(12)
        content_safe = ai_analysis_content
        if USE_FALLBACK_FONT:
            content_safe = content_safe.encode('ascii', 'replace').decode('ascii')
        pdf.multi_cell(0, 5, safe_text(content_safe, 4000))
    else:
        pdf.set_font(font, '', 10)
        pdf.set_x(10)
        pdf.multi_cell(0, 5, 'Chưa có báo cáo chiến lược từ AI.')

    # ─── Section 6: Portfolio Review & Macro ────────────────────────────────
    pdf.ln(6)
    pdf.set_font(font, 'B', 12)
    pdf.cell(0, 10, '6. DANH MUC & VI MO', 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')
    pdf.ln(2)

    for prefix in ['portfolio_review_', 'macro_report_']:
        section_data = load_latest_md(prefix)
        if section_data:
            pdf.set_font(font, 'B', 9)
            pdf.cell(0, 6, safe_text(section_data['fname']), 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font(font, '', 8)
            pdf.multi_cell(0, 5, safe_text(section_data['content'], 2000))
            pdf.ln(3)

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
