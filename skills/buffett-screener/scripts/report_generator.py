import json
from datetime import datetime

def generate_json_report(results: list[dict], metadata: dict, output_file: str):
    report = {"metadata": metadata, "results": results}
    with open(output_file, "w", encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"OK JSON report saved to: {output_file}")

def generate_markdown_report(results: list[dict], metadata: dict, output_file: str):
    lines = []
    lines.append("# Buffett Margin of Safety Screener Report (2026 Edition)")
    lines.append(f"**Generated:** {metadata.get('generated_at')}")
    lines.append(f"**Stocks Analyzed:** {metadata.get('candidates_analyzed')}")
    lines.append("")
    lines.append("> **Executive Summary - Buffett Screener:**")
    lines.append("> Bộ lọc Warren Buffett tập trung vào các doanh nghiệp có lợi thế cạnh tranh bền vững, ROE cao, nợ thấp và biên lợi nhuận ổn định. Phù hợp đầu tư giá trị dài hạn.")
    lines.append("")
    lines.append("## Summary Table")
    lines.append("| # | Symbol | Total Score | FCF Yield | ROIC | P/E | D/E | Profitable Yrs |")
    lines.append("|---|--------|-------------|-----------|------|-----|-----|----------------|")
    
    for idx, stock in enumerate(results, 1):
        m = stock.get("metrics", {})
        fcf = m.get("fcf_yield", 0) * 100
        roic = m.get("roic", 0) * 100
        pe = m.get("pe", 999)
        de = m.get("debt_to_equity", 999)
        yrs = m.get("positive_years", 0)
        score = stock.get("total_score", 0)
        lines.append(f"| {idx} | {stock.get('symbol')} | **{score}/100** | {fcf:.1f}% | {roic:.1f}% | {pe:.1f} | {de:.2f} | {yrs}/5 |")
        
    lines.append("")
    lines.append("## Detailed Component Breakdown")
    for stock in results:
        sym = stock.get('symbol')
        s = stock.get('scores', {})
        m = stock.get('metrics', {})
        score = stock.get('total_score', 0)
        
        rating = "Exceptional (Buffett Wonderful)" if score >= 80 else "Strong (Margin of Safety)" if score >= 60 else "Average" if score >= 40 else "Poor"
        
        lines.append(f"### {sym} - Score: {score}/100 ({rating})")
        
        if stock.get('error'):
            lines.append(f"**Error:** {stock['error']}\n")
            continue
            
        lines.append(f"- **FCF Yield:** {m.get('fcf_yield',0)*100:.1f}% (Score: {s.get('fcf',0)})")
        lines.append(f"- **ROIC:** {m.get('roic',0)*100:.1f}% (Score: {s.get('roic',0)})")
        lines.append(f"- **P/E Ratio:** {m.get('pe',999):.1f} (Score: {s.get('pe',0)})")
        lines.append(f"- **Debt to Equity:** {m.get('debt_to_equity',999):.2f} (Score: {s.get('health',0)})")
        lines.append(f"- **Consistent Profit:** {m.get('positive_years',0)}/5 years (Score: {s.get('profit',0)})")
        lines.append("")
        
    lines.append("## Vietnam Market Specific Notes")
    lines.append("> [!NOTE]")
    lines.append("> **Fact-Check Warning for Vietnam:** The criteria used above are standard US metrics. In the Vietnamese market:")
    lines.append("> 1. **ROIC > 15%** is extremely rare for capital-intensive industries (e.g., Power, Steel).")
    lines.append("> 2. **P/E scaling** might be skewed if EPS is deeply cyclical.")
    lines.append("> 3. **FCF Yield > 6%** might drop to 0% during major capex cycles (e.g. POW building Nhơn Trạch 3&4) but that doesn't always imply a 'value trap'.")

    with open(output_file, "w", encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"OK Markdown report saved to: {output_file}")
