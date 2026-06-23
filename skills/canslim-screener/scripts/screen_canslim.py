#!/usr/bin/env python3
"""
CANSLIM Stock Screener - Phase 3 (Full CANSLIM)

Screens US stocks using William O'Neil's CANSLIM methodology.
Phase 3 implements all 7 components: C, A, N, S, L, I, M (100% coverage)

Usage:
    python3 screen_canslim.py --api-key YOUR_KEY --max-candidates 40
    python3 screen_canslim.py  # Uses FMP_API_KEY environment variable

Output:
    - JSON: canslim_screener_YYYY-MM-DD_HHMMSS.json
    - Markdown: canslim_screener_YYYY-MM-DD_HHMMSS.md
"""

import argparse
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except:
    pass

from datetime import datetime
from typing import Optional

# Add calculators directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "calculators"))

from calculators.earnings_calculator import calculate_quarterly_growth
from calculators.growth_calculator import calculate_annual_growth
from calculators.institutional_calculator import calculate_institutional_sponsorship
from calculators.leadership_calculator import calculate_leadership
from calculators.market_calculator import calculate_market_direction
from calculators.new_highs_calculator import calculate_newness
from calculators.supply_demand_calculator import calculate_supply_demand

# Add vietnam-stock-manager to sys.path to import vn_data_provider
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
plugin_dir = os.path.dirname(os.path.dirname(base_dir))
sys.path.append(os.path.join(plugin_dir, "scripts"))

try:
    from vn_data_provider import VNDataProvider
except ImportError as e:
    print(f"Error: Could not import VNDataProvider from vietnam-stock-manager. Details: {e}")
    sys.exit(1)

from report_generator import generate_json_report, generate_markdown_report
from scorer import (
    calculate_composite_score_phase3,
    check_minimum_thresholds_phase3,
)

# Benchmark index for VN market
DEFAULT_BENCHMARK = "VNINDEX"

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="CANSLIM Stock Screener - Phase 3 (Full CANSLIM: C, A, N, S, L, I, M)"
    )

    parser.add_argument(
        "--universe",
        type=str,
        help="Comma-separated list of symbols. Defaults to portfolio.json.",
    )

    parser.add_argument(
        "--max-candidates",
        type=int,
        default=40,
        help="Limit number of stocks to output in the final report",
    )

    parser.add_argument(
        "--benchmark",
        type=str,
        default=DEFAULT_BENCHMARK,
        help=f"Benchmark symbol for RS calculation (default: {DEFAULT_BENCHMARK})",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "../../reports"),
        help="Directory to save reports",
    )

    parser.add_argument(
        "--disable-rs",
        action="store_true",
        help=(
            "Skip L component calculation (saves the per-stock 365-day price fetch; "
            "also skips the custom RS benchmark fetch when applicable). "
            "L score is set to neutral 50."
        ),
    )

    return parser.parse_args()


def analyze_stock(
    symbol: str,
    client: VNDataProvider,
    market_data: dict,
    rs_benchmark_historical: Optional[dict] = None,
    rs_benchmark: str = "VNINDEX",
    disable_rs: bool = False,
) -> Optional[dict]:
    """
    Analyze a single stock using CANSLIM Phase 3 components (7 components: C, A, N, S, L, I, M)

    Args:
        symbol: Stock ticker
        client: FMP API client
        market_data: Pre-calculated market direction data
        rs_benchmark_historical: RS benchmark historical prices (FMP response shape) for the
                                 L component's relative-strength calculation. May be None when
                                 the benchmark fetch failed; the L calculator falls back to
                                 absolute performance with a 20% penalty in that case.
        rs_benchmark: Benchmark symbol surfaced into the L component output (e.g. "VNINDEX", "SPY").
        disable_rs: When True, skip the per-stock 365-day fetch and emit a neutral L=50 result.

    Returns:
        Dict with analysis results, or None if analysis failed
    """
    print(f"  Analyzing {symbol}...", end=" ", flush=True)

    try:
        # Get company profile
        profile = client.get_profile(symbol)
        if not profile:
            print("✗ Profile unavailable")
            return None

        company_name = profile[0].get("companyName", symbol)
        sector = profile[0].get("sector", "Unknown")
        market_cap = profile[0].get("mktCap", 0)

        # Get quote
        quote = client.get_quote(symbol)
        if not quote:
            print("✗ Quote unavailable")
            return None

        price = quote[0].get("price", 0)

        # C Component: Current Quarterly Earnings
        quarterly_income = client.get_income_statement(symbol, period="quarter", limit=8)
        c_result = (
            calculate_quarterly_growth(quarterly_income)
            if quarterly_income
            else {"score": 0, "error": "No quarterly data"}
        )

        # A Component: Annual Growth
        annual_income = client.get_income_statement(symbol, period="annual", limit=5)
        a_result = (
            calculate_annual_growth(annual_income)
            if annual_income
            else {"score": 50, "error": "No annual data"}
        )

        # N Component: Newness / New Highs
        n_result = calculate_newness(quote[0])

        # S Component: Supply/Demand (uses existing historical_prices data - no extra API call)
        historical_prices = client.get_historical_prices(symbol, days=90)
        s_result = (
            calculate_supply_demand(historical_prices)
            if historical_prices
            else {"score": 0, "error": "No price history data"}
        )

        # L Component: Leadership / Relative Strength
        # When --disable-rs is set, skip the 365-day fetch entirely and emit a neutral
        # placeholder so downstream composite scoring still has a value to multiply by.
        if disable_rs:
            # Mirror the full Phase 3.1 l_component schema so downstream consumers
            # (JSON parsers, report templates, postmortem tools) can read fields
            # uniformly without special-casing the disable-rs branch. Multi-period
            # numeric fields are None; available_periods is empty; missing_periods
            # lists every configured window.
            l_result = {
                "score": 50,
                "skipped": True,
                "reason": "Disabled by --disable-rs",
                # Legacy fields
                "stock_52w_performance": None,
                "sp500_52w_performance": None,
                "relative_performance": None,
                "rs_rank_estimate": None,
                "days_analyzed": 0,
                "interpretation": "L component skipped via --disable-rs (neutral 50)",
                "quality_warning": None,
                "error": None,
                # Phase 3.1 multi-period fields
                "rs_3m_return": None,
                "rs_6m_return": None,
                "rs_12m_return": None,
                "rs_12m_return": None,
                "benchmark_3m_return": None,
                "benchmark_6m_return": None,
                "benchmark_12m_return": None,
                "rel_3m": None,
                "rel_6m": None,
                "rel_12m": None,
                "weighted_stock_performance": None,
                "weighted_relative_performance": None,
                "available_periods": [],
                "missing_periods": ["3m", "6m", "12m"],
                "benchmark_52w_performance": None,
                "rs_benchmark": rs_benchmark,
            }
        else:
            historical_prices_365 = client.get_historical_prices(symbol, days=365)
            l_result = (
                calculate_leadership(historical_prices_365, rs_benchmark_historical, rs_benchmark)
                if historical_prices_365
                else {"score": 0, "error": "No 365-day price history data"}
            )

        # I Component: Institutional Sponsorship
        institutional_data = client.get_institutional_holders(symbol)
        i_result = (
            calculate_institutional_sponsorship(institutional_data)
            if institutional_data
            else {"score": 50, "error": "No institutional data"}
        )

        # M Component: Market Direction (use pre-calculated)
        m_result = market_data

        # Calculate composite score (Phase 3: 7 components - FULL CANSLIM)
        composite = calculate_composite_score_phase3(
            c_score=c_result.get("score", 0),
            a_score=a_result.get("score", 50),
            n_score=n_result.get("score", 0),
            s_score=s_result.get("score", 0),
            l_score=l_result.get("score", 0),
            i_score=i_result.get("score", 0),
            m_score=m_result.get("score", 50),
        )

        # Check minimum thresholds (Phase 3)
        threshold_check = check_minimum_thresholds_phase3(
            c_score=c_result.get("score", 0),
            a_score=a_result.get("score", 50),
            n_score=n_result.get("score", 0),
            s_score=s_result.get("score", 0),
            l_score=l_result.get("score", 0),
            i_score=i_result.get("score", 0),
            m_score=m_result.get("score", 50),
        )

        print(f"✓ Score: {composite['composite_score']:.1f} ({composite['rating']})")

        return {
            "symbol": symbol,
            "company_name": company_name,
            "sector": sector,
            "price": price,
            "market_cap": market_cap,
            "composite_score": composite["composite_score"],
            "rating": composite["rating"],
            "rating_description": composite["rating_description"],
            "guidance": composite["guidance"],
            "weakest_component": composite["weakest_component"],
            "weakest_score": composite["weakest_score"],
            "c_component": c_result,
            "a_component": a_result,
            "n_component": n_result,
            "s_component": s_result,
            "l_component": l_result,  # NEW: Phase 3
            "i_component": i_result,
            "m_component": m_result,
            "threshold_check": threshold_check,
        }

    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def main():
    """Main screening workflow"""
    args = parse_arguments()

    print("=" * 60)
    print("CANSLIM Stock Screener - Phase 3 (Full CANSLIM)")
    print(
        "Components: C (Earnings), A (Growth), N (Newness), S (Supply/Demand), L (Leadership), I (Institutional), M (Market)"
    )
    print("=" * 60)
    print()

    # Initialize VNDataProvider
    try:
        client = VNDataProvider()
        print("OK VNDataProvider initialized")
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine universe
    if args.universe:
        universe = [s.strip() for s in args.universe.split(",")]
        universe = universe[: args.max_candidates]
        print(f"✓ Custom universe: {len(universe)} stocks")
    else:
        universe = DEFAULT_UNIVERSE[: args.max_candidates]
        print(f"✓ Default universe (VN-Index top {len(universe)}): {len(universe)} stocks")

    print()

    # Step 1: Calculate market direction (M component) once for all stocks
    print("Step 1: Analyzing Market Direction (M Component)")
    print("-" * 60)

    sp500_quote = client.get_quote("VNINDEX")
    vix_quote = client.get_quote("^VIX")

    if not sp500_quote:
        print("ERROR: Unable to fetch VN-Index data", file=sys.stderr)
        sys.exit(1)

    # Fetch VNINDEX historical prices for the M component. VNINDEX must remain the
    # benchmark for the M component to keep scale consistent with the VNINDEX quote
    # (see test_canslim_fixes.py::TestBenchmarkScaleConsistency).
    print("Fetching VNINDEX 52-week data for M component (EMA)...")
    market_sp500_historical = client.get_historical_prices("VNINDEX", days=365)
    if market_sp500_historical and market_sp500_historical.get("historical"):
        market_days = len(market_sp500_historical.get("historical", []))
        print(f"✓ VNINDEX historical data: {market_days} days")
    else:
        print("⚠️  VNINDEX historical data unavailable - M component will use EMA fallback")

    # Resolve the L component's benchmark fetch. When the user kept the default
    # VNINDEX, reuse the already-fetched series (FMPClient cache also covers this,
    # but the explicit reuse here documents the intent). When --disable-rs is
    # set, skip the benchmark fetch entirely.
    rs_benchmark_historical = None
    if not args.disable_rs:
        if args.benchmark == "VNINDEX":
            rs_benchmark_historical = market_sp500_historical
        else:
            print(
                f"Fetching {args.benchmark} 52-week data for L component (Relative Strength)..."
            )
            rs_benchmark_historical = client.get_historical_prices(args.benchmark, days=365)
            if rs_benchmark_historical and rs_benchmark_historical.get("historical"):
                rs_days = len(rs_benchmark_historical.get("historical", []))
                print(f"✓ {args.benchmark} historical data: {rs_days} days")
            else:
                print(
                    f"⚠️  {args.benchmark} historical data unavailable - "
                    "L component will fall back to absolute performance with 20% penalty"
                )
    else:
        print("⚠️  --disable-rs set: L component will be fixed at neutral 50 (no RS fetch)")

    # Calculate M component using real VNINDEX historical prices for accurate EMA
    market_sp500_list = (
        market_sp500_historical.get("historical", []) if market_sp500_historical else []
    )
    market_data = calculate_market_direction(
        sp500_quote=sp500_quote[0],
        sp500_prices=market_sp500_list if market_sp500_list else None,
        vix_quote=vix_quote[0] if vix_quote else None,
    )

    print(f"VN-Index: ${market_data.get('sp500_price', 0.0):.2f}")
    print(f"Distance from 50-EMA: {market_data.get('distance_from_ema_pct', 0.0):+.2f}%")
    print(f"Trend: {market_data.get('trend', 'unknown')}")
    print(f"M Score: {market_data.get('score', 50)}/100")
    print(f"Interpretation: {market_data.get('interpretation', 'Unavailable')}")

    if market_data.get("warning"):
        print()
        print(f"⚠️  WARNING: {market_data['warning']}")
        print("    Consider raising cash allocation. CANSLIM doesn't work in bear markets.")

    print()

    # Step 2: Progressive filtering and analysis
    print(f"Step 2: Analyzing {len(universe)} Stocks")
    print("-" * 60)

    results = []
    for symbol in universe:
        analysis = analyze_stock(
            symbol,
            client,
            market_data,
            rs_benchmark_historical=rs_benchmark_historical,
            rs_benchmark=args.benchmark,
            disable_rs=args.disable_rs,
        )
        if analysis:
            results.append(analysis)

    print()
    print(f"✓ Successfully analyzed {len(results)} stocks")
    print()

    # Step 3: Rank by composite score
    print("Step 3: Ranking Results")
    print("-" * 60)

    results.sort(key=lambda x: x["composite_score"], reverse=True)

    # Display top 5
    print("Top 5 Stocks:")
    for i, stock in enumerate(results[:5], 1):
        print(f"  {i}. {stock['symbol']:6} - {stock['composite_score']:5.1f} ({stock['rating']})")

    print()

    # Step 4: Generate reports
    print("Step 4: Generating Reports")
    print("-" * 60)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_file = os.path.join(args.output_dir, f"canslim_screener_{timestamp}.json")
    md_file = os.path.join(args.output_dir, f"canslim_screener_{timestamp}.md")

    metadata = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "schema_version": "3.1",
        "phase": "3.1 (7 components - FULL CANSLIM with multi-period RS)",
        "components_included": ["C", "A", "N", "S", "L", "I", "M"],
        "candidates_analyzed": len(results),
        "universe_size": len(universe),
        "screening_options": {
            "rs_benchmark": args.benchmark,
            "rs_disabled": args.disable_rs,
        },
        "market_condition": {
            "trend": market_data["trend"],
            "M_score": market_data["score"],
            "warning": market_data.get("warning"),
        },
    }

    # Limit to top N for report
    top_results = results[: args.max_candidates]

    generate_json_report(top_results, metadata, json_file)
    generate_markdown_report(top_results, metadata, md_file)

    print()
    print("=" * 60)
    print("✓ CANSLIM Screening Complete")
    print("=" * 60)
    print(f"  JSON Report: {json_file}")
    print(f"  Markdown Report: {md_file}")
    print()

    if args.disable_rs:
        # Per-stock 365-day RS fetch is skipped; M-side market calls remain
        # (VNINDEX quote + VIX quote + VNINDEX 365-day = 3 calls).
        print(
            f"  Estimated calls: ~{len(universe) * 6 + 3} "
            f"(3 market data calls + {len(universe)} stocks × 6 API calls each, --disable-rs)"
        )
    else:
        # Custom benchmark adds one extra fetch when it differs from VNINDEX.
        market_calls = 3 if args.benchmark == "VNINDEX" else 4
        print(
            f"  Estimated calls: ~{len(universe) * 7 + market_calls} "
            f"({market_calls} market data calls + {len(universe)} stocks × 7 API calls each)"
        )
    print("  Phase 3.1 includes all 7 CANSLIM components (C, A, N, S, L, I, M)")
    print()


if __name__ == "__main__":
    main()

