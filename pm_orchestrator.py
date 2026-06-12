import os
import subprocess
import sys

def run_script(script_name):
    """Run a python script and forward its output to stdout."""
    print(f"\n>>> Running {script_name}...")
    try:
        # We run the script in the same python environment
        result = subprocess.run([sys.executable, script_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
        
        # Print stdout and stderr
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"Error output:\n{result.stderr}", file=sys.stderr)
            
        return result.returncode == 0
    except Exception as e:
        print(f"Failed to execute {script_name}: {e}", file=sys.stderr)
        return False

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    print("="*85)
    print("                    VIETNAM STOCK MULTI-AGENT PORTFOLIO SYSTEM")
    print("="*85)
    
    # 1. Update Portfolio Valuation & Quotes
    tracker_success = run_script("portfolio_tracker.py")
    if not tracker_success:
        print("[-] Portfolio tracker failed. Exiting workflow.")
        return
        
    # 2. Run Short-Term Swing Trader Alerts
    run_script("st_trader_scan.py")
    
    # 3. Run Long-Term Value Investor Reports
    run_script("lt_investor_report.py")
    
    print("="*85)
    print("                            WORKFLOW RUN COMPLETED")
    print("="*85)

if __name__ == '__main__':
    main()
