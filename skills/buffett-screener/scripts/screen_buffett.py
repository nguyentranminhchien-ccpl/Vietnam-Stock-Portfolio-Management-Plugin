import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except:
    pass

import os
import argparse
import json
from datetime import datetime

# Add vietnam-stock-manager to sys.path to import vn_data_provider
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
plugin_dir = os.path.dirname(os.path.dirname(base_dir))
sys.path.append(os.path.join(plugin_dir, "scripts"))

try:
    from vn_data_provider import VNDataProvider
except ImportError:
    print("Error: Could not import VNDataProvider from vietnam-stock-manager.")
    sys.exit(1)
    
from scorer import BuffettScorer
import report_generator

def main():
    parser = argparse.ArgumentParser(description="Buffett Margin of Safety Screener (2026 Edition)")
    parser.add_argument("--universe", type=str, default="", help="Comma-separated symbols to screen")
    parser.add_argument("--output", type=str, default="buffett_report", help="Output file prefix")
    args = parser.parse_args()

    symbols = []
    if args.universe:
        symbols = [s.strip().upper() for s in args.universe.split(",") if s.strip()]
    else:
        # Load portfolio.json
        portfolio_path = os.path.join(plugin_dir, "data", "portfolio.json")
        if os.path.exists(portfolio_path):
            try:
                with open(portfolio_path, "r", encoding="utf-8") as f:
                    portfolio = json.load(f)
                    symbols = [pos["symbol"] for pos in portfolio.get("positions", [])]
            except Exception:
                pass
        
        # Fallback to a default list if portfolio is empty or missing
        if not symbols:
            symbols = ["FPT", "HPG", "VNM", "VCB", "MBB", "MWG", "SSI", "ACB"]

    print(f"Starting Buffett Screener on {len(symbols)} symbols: {', '.join(symbols)}")
    
    client = VNDataProvider()
        
    scorer = BuffettScorer(client)
    results = []
    
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] Analyzing {symbol}...")
        res = scorer.score_symbol(symbol)
        results.append(res)
        
    # Sort results by total_score descending
    results.sort(key=lambda x: x.get('total_score', 0), reverse=True)
    
    metadata = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "candidates_analyzed": len(symbols),
        "schema_version": "1.0",
        "methodology": "Margin of Safety 2026 (Buffett Update)"
    }
    
    reports_dir = os.path.join(plugin_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    
    json_path = os.path.join(reports_dir, f"{args.output}.json")
    md_path = os.path.join(reports_dir, f"{args.output}.md")
    
    report_generator.generate_json_report(results, metadata, json_path)
    report_generator.generate_markdown_report(results, metadata, md_path)
    print("Screening complete.")

if __name__ == "__main__":
    main()
