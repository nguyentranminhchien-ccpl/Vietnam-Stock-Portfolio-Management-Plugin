---
name: buffett-screener
description: Screen stocks using the Warren Buffett 2026 Margin of Safety methodology (value investing).
---

# Buffett Margin of Safety Screener (2026 Edition)

## Objective
This skill filters and ranks US stocks based on the modernized Warren Buffett "Margin of Safety" principles (2026 Edition). Unlike classic Graham filters that focus purely on P/B and net-net assets, this screener prioritizes:
1. **Free Cash Flow Yield** over Bond Yield
2. **ROIC > WACC** (Efficient capital allocation and Intangible Moat)
3. **Consistent Profitability** (History of positive Net Income)
4. **Growth-Adjusted P/E** (Tolerates higher P/E for high-ROIC compounders)
5. **Financial Health** (Low Debt/Equity)

## Capabilities
- Executes the `screen_buffett.py` script to generate scores from 0-100.
- Outputs detailed JSON and Markdown reports containing FCF Yield, ROIC, P/E, Debt/Equity, and profitability metrics.

## Instructions
When the user asks to filter or screen stocks in the style of Warren Buffett, Value Investing, or Margin of Safety:

1. Determine the target universe. If the user does not provide one, the default universe (`AAPL,MSFT,GOOG,AMZN,META,NVDA,BRK-B,JPM`) will be used. You can pass a custom universe via the `--universe` argument.
2. Run the screener:
```powershell
python "C:\Users\Thinkpad T14 gen 2\.gemini\config\plugins\vietnam-multiagent-portfolio\skills\buffett-screener\scripts\screen_buffett.py" --universe "AAPL,MSFT,BRK-B,KO,AXP"
```
3. Read the generated markdown report from `C:\Users\Thinkpad T14 gen 2\.gemini\config\plugins\vietnam-multiagent-portfolio\skills\buffett-screener\reports\buffett_report.md` using the `view_file` tool.
4. Present the top-ranked stocks to the user, highlighting their FCF Yield, ROIC, and Margin of Safety score.

## Understanding the Scores
- **80-100 (Buffett Wonderful)**: Exceptional compounders with strong moats (high ROIC), high cash flow, and reasonable valuation.
- **60-79 (Strong Margin of Safety)**: Solid value picks with good fundamentals.
- **40-59 (Average)**: Fair companies at fair prices, or good companies at high prices.
- **0-39 (Poor)**: Overvalued or poor fundamentals (Value traps, unprofitable tech, etc.).
