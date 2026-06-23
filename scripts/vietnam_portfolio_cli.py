import argparse
import subprocess
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def run_script(script_name, *args):
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, script_name)] + list(args)
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running {script_name}: {e}")
        sys.exit(e.returncode)

def main():
    parser = argparse.ArgumentParser(description="Vietnam Portfolio CLI (MCP wrapper)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Tracker command
    parser_tracker = subparsers.add_parser("dashboard", help="Xem Dashboard danh mục")
    
    # Update command
    parser_update = subparsers.add_parser("update", help="Mua/Bán cổ phiếu")
    parser_update.add_argument("action", choices=["buy", "sell"])
    parser_update.add_argument("ticker")
    parser_update.add_argument("shares", type=int)
    parser_update.add_argument("price", type=float)
    parser_update.add_argument("allocation", choices=["short-term", "long-term"])
    parser_update.add_argument("--dry-run", action="store_true")

    # Orchestrator command
    parser_orchestrate = subparsers.add_parser("orchestrate", help="Chạy luồng cập nhật tổng thể")
    parser_orchestrate.add_argument("--skip-lt", action="store_true")
    parser_orchestrate.add_argument("--pdf-only", action="store_true")
    parser_orchestrate.add_argument("--non-interactive", action="store_true")
    parser_orchestrate.add_argument("--with-screeners", action="store_true", help="Chạy tự động các bộ lọc CANSLIM/VCP")

    # Preflight command
    parser_preflight = subparsers.add_parser("preflight", help="Kiểm tra tiền điều kiện")

    args = parser.parse_args()

    if args.command == "dashboard":
        run_script("portfolio_tracker.py")
    elif args.command == "update":
        cmd_args = [args.action, args.ticker, str(args.shares), str(args.price), args.allocation]
        if args.dry_run:
            cmd_args.append("--dry-run")
        run_script("update_portfolio.py", *cmd_args)
    elif args.command == "orchestrate":
        cmd_args = []
        if args.skip_lt: cmd_args.append("--skip-lt")
        if args.pdf_only: cmd_args.append("--pdf-only")
        if args.non_interactive: cmd_args.append("--non-interactive")
        if args.with_screeners: cmd_args.append("--with-screeners")
        run_script("pm_orchestrator.py", *cmd_args)
    elif args.command == "preflight":
        run_script("preflight.py")

if __name__ == "__main__":
    main()
