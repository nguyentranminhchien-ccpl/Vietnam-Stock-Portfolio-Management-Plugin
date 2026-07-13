#!/usr/bin/env python3
"""
preflight.py — Kiểm tra tiền điều kiện cho Vietnam Stock Manager.

Cách dùng trong các script khác:
    from preflight import run_preflight, PLUGIN_DIR, DATA_DIR, REPORTS_DIR, PORTFOLIO_FILE

    cfg = run_preflight(need_mozyfin=True, need_portfolio=True)
    if not cfg['proceed']:
        sys.exit(0)

    USE_VNSTOCK = cfg['use_vnstock_fallback']
"""
import os
import sys
import subprocess
import json

# ── Đường dẫn chuẩn (tính từ vị trí của file này) ───────────────────────────
SCRIPTS_DIR    = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR     = os.path.abspath(os.path.join(SCRIPTS_DIR, '..'))
DATA_DIR       = os.path.join(PLUGIN_DIR, 'data')
REPORTS_DIR    = os.path.join(PLUGIN_DIR, 'reports')
PORTFOLIO_FILE = os.path.join(DATA_DIR, 'portfolio.json')
WATCHLIST_FILE = os.path.join(DATA_DIR, 'watchlist.json')
FONTS_DIR      = os.path.join(SCRIPTS_DIR, 'fonts')


# ── Tiện ích hỏi người dùng ──────────────────────────────────────────────────

def ask_user(question: str, default_yes: bool = True) -> bool:
    """
    Hiển thị câu hỏi Y/n và chờ người dùng trả lời.
    - Nếu stdin không phải terminal (non-interactive), trả về default_yes.
    - Chấp nhận: y, yes, có, co (True) | n, no, không (False)
    """
    if not sys.stdin.isatty():
        return default_yes
    suffix = " [Y/n]: " if default_yes else " [y/N]: "
    try:
        answer = input(question + suffix).strip().lower()
        if answer == '':
            return default_yes
        return answer in ('y', 'yes', 'có', 'co', 'c')
    except (EOFError, KeyboardInterrupt):
        print()
        return default_yes


# ── Các hàm kiểm tra ─────────────────────────────────────────────────────────

def check_mozyfin() -> bool:
    """Kiểm tra mozyfin CLI có khả dụng không."""
    try:
        result = subprocess.run(
            ['mozyfin', '--version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def load_portfolio() -> tuple:
    """
    Đọc portfolio.json. Trả về (ok: bool, data: dict, active_holdings: list).
    'active_holdings' chỉ gồm những mã có shares > 0.
    """
    if not os.path.exists(PORTFOLIO_FILE):
        return False, {}, []
    try:
        with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        active = [h for h in data.get('holdings', []) if h.get('shares', 0) > 0]
        return len(active) > 0, data, active
    except Exception as e:
        print(f"    [!] Lỗi đọc portfolio.json: {e}")
        return False, {}, []


def load_watchlist() -> list:
    """Đọc watchlist.json và trả về danh sách watchlist items."""
    if not os.path.exists(WATCHLIST_FILE):
        return []
    try:
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('watchlist', [])
    except Exception:
        return []


def check_fonts() -> bool:
    """Kiểm tra font Roboto tồn tại."""
    reg  = os.path.join(FONTS_DIR, 'Roboto-Regular.ttf')
    bold = os.path.join(FONTS_DIR, 'Roboto-Bold.ttf')
    return os.path.exists(reg) and os.path.exists(bold)


def ensure_reports_dir():
    """Tự động tạo thư mục reports/ nếu chưa có (không hỏi)."""
    os.makedirs(REPORTS_DIR, exist_ok=True)


def check_st_reports() -> bool:
    """Kiểm tra có file báo cáo TA (*_st_scan_YYYYMMDD.md) trong reports/ không."""
    if not os.path.exists(REPORTS_DIR):
        return False
    return any('_st_scan_' in f and f.endswith('.md') for f in os.listdir(REPORTS_DIR))


# ── Hàm chính ─────────────────────────────────────────────────────────────────

def run_preflight(
    need_mozyfin:    bool = True,
    need_portfolio:  bool = True,
    need_fonts:      bool = False,
    need_st_reports: bool = False,
    non_interactive: bool = False,
) -> dict:
    """
    Chạy toàn bộ kiểm tra tiền điều kiện và hỏi người dùng khi cần.

    Tham số:
        need_mozyfin      – Có cần Mozyfin CLI không?
        need_portfolio    – Có cần portfolio.json với dữ liệu thực không?
        need_fonts        – Có cần font Roboto không? (chỉ generate_pdf cần)
        need_st_reports   – Có cần báo cáo ST scan không? (chỉ generate_pdf cần)
        non_interactive   – True = luôn chọn Yes (dùng khi chạy từ subagent)

    Trả về dict với các key:
        proceed               – False nếu người dùng chọn dừng lại
        mozyfin_available     – True nếu mozyfin CLI hoạt động
        use_vnstock_fallback  – True nếu dùng vnstock thay mozyfin
        portfolio_ok          – True nếu có holdings thực
        use_watchlist         – True nếu không có holdings, dùng watchlist
        fonts_ok              – True nếu font Roboto tồn tại
        use_fallback_font     – True nếu dùng Helvetica thay Roboto
        st_reports_ok         – True nếu có báo cáo ST scan
        plugin_dir, data_dir, reports_dir, portfolio_file, watchlist_file
    """
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

    cfg = {
        'proceed':              True,
        'mozyfin_available':    False,
        'use_vnstock_fallback': False,
        'portfolio_ok':         False,
        'use_watchlist':        False,
        'fonts_ok':             False,
        'use_fallback_font':    False,
        'st_reports_ok':        False,
        'plugin_dir':           PLUGIN_DIR,
        'data_dir':             DATA_DIR,
        'reports_dir':          REPORTS_DIR,
        'portfolio_file':       PORTFOLIO_FILE,
        'watchlist_file':       WATCHLIST_FILE,
    }

    # Luôn đảm bảo thư mục reports/ tồn tại
    ensure_reports_dir()

    # ── 1. Kiểm tra Mozyfin ──────────────────────────────────────────────────
    if need_mozyfin:
        moz_ok = check_mozyfin()
        cfg['mozyfin_available'] = moz_ok
        if not moz_ok:
            print("\n[!] Mozyfin CLI không tìm thấy hoặc không phản hồi.")
            print(f"    (Cài đặt tại: https://mozyfin.com)")
            use_vs = non_interactive or ask_user(
                "    Sử dụng vnstock làm nguồn dữ liệu thay thế?", default_yes=True
            )
            if use_vs:
                cfg['use_vnstock_fallback'] = True
                print("    → Sẽ dùng vnstock làm nguồn dữ liệu.\n")
            else:
                print("    → Dừng lại. Vui lòng cài Mozyfin và thử lại.")
                cfg['proceed'] = False
                return cfg
        else:
            print("[+] Mozyfin CLI: OK")

    # ── 2. Kiểm tra Portfolio ────────────────────────────────────────────────
    if need_portfolio:
        port_ok, _, _ = load_portfolio()
        cfg['portfolio_ok'] = port_ok
        if not port_ok:
            print(f"\n[!] portfolio.json không có vị thế nào đang nắm giữ (shares > 0).")
            print(f"    Kiểm tra tại: {PORTFOLIO_FILE}")
            use_wl = non_interactive or ask_user(
                "    Chạy với danh sách watchlist thay thế?", default_yes=True
            )
            if use_wl:
                cfg['use_watchlist'] = True
                print("    → Sẽ dùng watchlist.json làm danh sách cổ phiếu.\n")
            else:
                print("    → Dừng lại.")
                cfg['proceed'] = False
                return cfg
        else:
            print("[+] Portfolio: OK")

    # ── 3. Kiểm tra Font ─────────────────────────────────────────────────────
    if need_fonts:
        fonts_ok = check_fonts()
        cfg['fonts_ok'] = fonts_ok
        if not fonts_ok:
            print(f"\n[!] Font Roboto không tìm thấy tại: {FONTS_DIR}")
            use_fb = non_interactive or ask_user(
                "    Dùng font mặc định Helvetica (tiếng Việt hiển thị hạn chế)?",
                default_yes=True
            )
            if use_fb:
                cfg['use_fallback_font'] = True
                print("    → Sẽ dùng font Helvetica.\n")
            else:
                print(f"    → Dừng lại. Vui lòng đặt Roboto-Regular.ttf và Roboto-Bold.ttf vào:\n    {FONTS_DIR}")
                cfg['proceed'] = False
                return cfg
        else:
            print("[+] Font Roboto: OK")

    # ── 4. Kiểm tra báo cáo ST scan ─────────────────────────────────────────
    if need_st_reports:
        st_ok = check_st_reports()
        cfg['st_reports_ok'] = st_ok
        if not st_ok:
            print("\n[!] Chưa có báo cáo phân tích kỹ thuật nào trong thư mục reports/.")
            if not non_interactive and ask_user(
                "    Chạy st_trader_scan.py ngay bây giờ để tạo dữ liệu?", default_yes=True
            ):
                print("    → Đang chạy st_trader_scan.py...")
                st_script = os.path.join(SCRIPTS_DIR, 'st_trader_scan.py')
                subprocess.run([sys.executable, st_script], check=False)
                cfg['st_reports_ok'] = check_st_reports()
                if cfg['st_reports_ok']:
                    print("    → Tạo báo cáo ST scan thành công.\n")
            else:
                print("    → Bỏ qua — Section 'Kỹ Thuật' trong PDF sẽ trống.\n")

    return cfg
