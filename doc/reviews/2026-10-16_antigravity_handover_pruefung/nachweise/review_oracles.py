"""Independent arithmetic for numerical claims, with no runtime or platform data."""
import json
import math
from pathlib import Path

monthly = 0.025
result = {
    "antigravity_example": {
        "monthly_return_pct": 2.5, "months": 3.5, "dd_pct": 2,
        "period_return_pct": math.expm1(3.5 * math.log1p(monthly)) * 100,
        "annual_return_pct": math.expm1(12 * math.log1p(monthly)) * 100,
        "annual_calmar": math.expm1(12 * math.log1p(monthly)) * 100 / 2,
    },
    "quoted_source_test_counts": {
        "five_sources_java": 105 + 176 + 147 + 49 + 107,
        "five_sources_java_and_vantage_python": 105 + 176 + 147 + 49 + 6 + 107,
        "seven_projects_user_summary": 105 + 176 + 147 + 55 + 107 + 57 + 156,
        "claimed_634_is_sum": False,
    },
    "limits": [
        "Passing tests establish tested behavior, not absence of all defects.",
        "H1 sampled portfolio estimates do not guarantee a lower bound on actual broker equity drawdown.",
        "No universal profitable pip threshold or future ranking follows from the reviewed code."
    ]
}
target = Path(__file__).with_name("review_oracles.json")
target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
