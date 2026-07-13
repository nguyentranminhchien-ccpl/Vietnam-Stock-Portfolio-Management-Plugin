import sys

class BuffettScorer:
    """
    Scores stocks based on Margin of Safety 2026 principles (Warren Buffett style):
    - FCF Yield > Bond Yield (Quality cash flow)
    - ROIC > WACC (Efficient capital allocation)
    - P/E adjusted for growth/ROIC
    - Debt to Equity (Financial Health)
    - Consistent Profitability (5 years)
    """

    def __init__(self, fmp_client):
        self.fmp = fmp_client

    def score_symbol(self, symbol: str) -> dict:
        try:
            # 1. Fetch data
            metrics_data = self.fmp.get_key_metrics(symbol, limit=1)
            income_data = self.fmp.get_income_statement(symbol, limit=5)
            quote_data = self.fmp.get_quote(symbol)

            if not metrics_data or not income_data or not quote_data:
                return {"symbol": symbol, "error": "Missing FMP data", "total_score": 0}

            metric = metrics_data[0]
            quote = quote_data[0]

            # 2. Extract values
            pe = metric.get('peRatio', 999) or 999
            pb = metric.get('pbRatio', 999) or 999
            roic = metric.get('roic', 0) or 0
            debt_to_equity = metric.get('debtToEquity', 999) or 999
            fcf_yield = metric.get('freeCashFlowYield', 0) or 0
            
            # Consistent profit: count years with positive net income
            positive_years = sum(1 for inc in income_data if (inc.get('netIncome', 0) or 0) > 0)

            # 3. Calculate Component Scores
            scores = {}
            
            # A. FCF Yield (Target > 6%)
            if fcf_yield >= 0.06: scores['fcf'] = 100
            elif fcf_yield >= 0.04: scores['fcf'] = 80
            elif fcf_yield > 0: scores['fcf'] = 50
            else: scores['fcf'] = 0

            # B. ROIC (Target > 15%)
            if roic >= 0.15: scores['roic'] = 100
            elif roic >= 0.10: scores['roic'] = 80
            elif roic > 0.05: scores['roic'] = 50
            else: scores['roic'] = 0

            # C. P/E Growth-Adjusted
            # If ROIC is very high, we tolerate higher P/E
            pe_tolerance = 15
            if roic >= 0.15: pe_tolerance = 25
            if roic >= 0.20: pe_tolerance = 35

            if pe > 0 and pe <= pe_tolerance * 0.6: scores['pe'] = 100
            elif pe > 0 and pe <= pe_tolerance: scores['pe'] = 80
            elif pe > 0 and pe <= pe_tolerance * 1.5: scores['pe'] = 50
            else: scores['pe'] = 0

            # D. Financial Health (Debt/Equity < 1.0)
            if debt_to_equity <= 0.5: scores['health'] = 100
            elif debt_to_equity <= 1.0: scores['health'] = 80
            elif debt_to_equity <= 1.5: scores['health'] = 50
            else: scores['health'] = 0

            # E. Consistent Profit
            if positive_years == 5: scores['profit'] = 100
            elif positive_years == 4: scores['profit'] = 80
            elif positive_years >= 2: scores['profit'] = 40
            else: scores['profit'] = 0

            # 4. Total Score (Weighted)
            weights = {'fcf': 0.25, 'roic': 0.30, 'pe': 0.15, 'health': 0.15, 'profit': 0.15}
            total = sum(scores[k] * weights[k] for k in weights)

            return {
                "symbol": symbol,
                "price": quote.get('price', 0),
                "total_score": round(total, 1),
                "metrics": {
                    "fcf_yield": fcf_yield,
                    "roic": roic,
                    "pe": pe,
                    "pb": pb,
                    "debt_to_equity": debt_to_equity,
                    "positive_years": positive_years
                },
                "scores": scores,
                "error": None
            }
        except Exception as e:
            return {"symbol": symbol, "error": str(e), "total_score": 0}
