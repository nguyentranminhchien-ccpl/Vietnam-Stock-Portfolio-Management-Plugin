# -*- coding: utf-8 -*-
"""
cleanup_reports.py — Dọn dẹp báo cáo cũ trong thư mục reports/

Chính sách giữ lại:
- CANSLIM screener : Giữ 3 cặp .json/.md mới nhất
- VCP screener     : Giữ 3 cặp .json/.md mới nhất
- ST scan          : Giữ 1 file mới nhất mỗi ticker (xóa bản cũ hơn)
- *_report.md      : Giữ nếu < 7 ngày tuổi
- Buffett          : Đổi tên buffett_report.json → buffett_report_YYYYMMDD.json
                     nếu chưa có ngày trong tên
"""

import os
import sys
import re
import time
import json
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except:
    pass

# ── Paths ────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(SCRIPT_DIR)
REPORTS_DIR = os.path.join(PLUGIN_DIR, 'reports')

KEEP_SCREENER_PAIRS = 3   # Số cặp json+md giữ lại
REPORT_MAX_AGE_DAYS = 7   # Số ngày giữ *_report.md


def cleanup_screener(prefix: str):
    """Giữ N cặp mới nhất cho loại screener; xóa phần còn lại."""
    pairs = defaultdict(dict)
    for fname in os.listdir(REPORTS_DIR):
        if not fname.startswith(prefix):
            continue
        # Match both YYYYMMDD_HHMMSS and YYYY-MM-DD_HHMMSS formats
        m = re.search(r'_(\d{4}-\d{2}-\d{2}_\d{6}|\d{8}_\d{6})\.', fname)
        if not m:
            continue
        key = m.group(1)
        ext = 'json' if fname.endswith('.json') else 'md'
        pairs[key][ext] = fname

    sorted_keys = sorted(pairs.keys(), reverse=True)
    kept, deleted = 0, 0
    for i, key in enumerate(sorted_keys):
        for ext, fname in pairs[key].items():
            fpath = os.path.join(REPORTS_DIR, fname)
            if i < KEEP_SCREENER_PAIRS:
                kept += 1
            else:
                try:
                    os.remove(fpath)
                    deleted += 1
                    print(f"  Xóa: {fname}")
                except OSError as e:
                    print(f"  Lỗi khi xóa {fname}: {e}")
    print(f"  [{prefix}] Giữ {kept} files, xóa {deleted} files.")


def cleanup_st_scans():
    """Giữ 1 file ST scan mới nhất mỗi ticker; xóa các bản cũ hơn."""
    by_ticker = defaultdict(list)
    for fname in os.listdir(REPORTS_DIR):
        m = re.match(r'^(.+)_st_scan_(\d{8}(?:_\d{6})?)\.md$', fname)
        if m:
            ticker = m.group(1)
            by_ticker[ticker].append(fname)

    deleted = 0
    for ticker, files in by_ticker.items():
        files_sorted = sorted(files, reverse=True)
        for old_file in files_sorted[1:]:  # Giữ file mới nhất
            fpath = os.path.join(REPORTS_DIR, old_file)
            try:
                os.remove(fpath)
                deleted += 1
                print(f"  Xóa ST scan cũ: {old_file}")
            except OSError as e:
                print(f"  Lỗi khi xóa {old_file}: {e}")
    print(f"  [ST scan] Xóa {deleted} files cũ.")


def cleanup_auto_reports():
    """Xóa *_report.md tự động nếu quá REPORT_MAX_AGE_DAYS ngày tuổi."""
    now = time.time()
    deleted = 0
    for fname in os.listdir(REPORTS_DIR):
        if not (fname.endswith('_report.md') and '_st_scan_' not in fname
                and '_equity_research' not in fname):
            continue
        fpath = os.path.join(REPORTS_DIR, fname)
        age_days = (now - os.path.getmtime(fpath)) / 86400
        if age_days > REPORT_MAX_AGE_DAYS:
            try:
                os.remove(fpath)
                deleted += 1
                print(f"  Xóa report cũ ({age_days:.0f} ngày): {fname}")
            except OSError as e:
                print(f"  Lỗi khi xóa {fname}: {e}")
    print(f"  [*_report.md] Xóa {deleted} files cũ hơn {REPORT_MAX_AGE_DAYS} ngày.")


def fix_undated_buffett():
    """Đổi tên buffett_report.json (không có ngày) sang buffett_report_YYYYMMDD.json."""
    src = os.path.join(REPORTS_DIR, 'buffett_report.json')
    if not os.path.exists(src):
        return
    try:
        with open(src, encoding='utf-8') as f:
            data = json.load(f)
        # Try to extract date from 'generated_at' field
        gen_at = data.get('generated_at', '')
        m = re.match(r'(\d{4})-(\d{2})-(\d{2})', gen_at)
        if m:
            date_str = m.group(1) + m.group(2) + m.group(3)
        else:
            # Use file modification time
            mtime = os.path.getmtime(src)
            from datetime import datetime as _dt
            date_str = _dt.fromtimestamp(mtime).strftime('%Y%m%d')
        dst = os.path.join(REPORTS_DIR, f'buffett_report_{date_str}.json')
        if not os.path.exists(dst):
            os.rename(src, dst)
            print(f"  Đổi tên: buffett_report.json → buffett_report_{date_str}.json")
        else:
            print(f"  Đã có {os.path.basename(dst)}, xóa bản không có ngày.")
            os.remove(src)
    except Exception as e:
        print(f"  Lỗi khi xử lý buffett_report.json: {e}")


def print_summary():
    """In tóm tắt số file còn lại trong reports/."""
    all_files = os.listdir(REPORTS_DIR)
    print(f"\n  Tổng số file còn lại trong reports/: {len(all_files)}")


def main():
    print("=" * 60)
    print("Dọn dẹp báo cáo cũ — Vietnam Portfolio Plugin")
    print("=" * 60)
    print("\n[1] Dọn CANSLIM screener...")
    cleanup_screener('canslim_screener_')
    print("\n[2] Dọn VCP screener...")
    cleanup_screener('vcp_screener_')
    print("\n[3] Dọn ST scan (giữ 1 mỗi ticker)...")
    cleanup_st_scans()
    print("\n[4] Dọn *_report.md cũ...")
    cleanup_auto_reports()
    print("\n[5] Xử lý buffett_report.json không có ngày...")
    fix_undated_buffett()
    print_summary()
    print("\nHoàn tất dọn dẹp!")


if __name__ == '__main__':
    main()
