"""Diagnosis of the renewable-availability extreme test V4.1 (Supplementary Appendix C.4).

Compares the one-month shock (February 2033, t = 97) with its S0 reference and prints
the numbers quoted in Appendix C.4 and in the response R1.1:
  - minimum hourly availability margin just before and at the shock month;
  - the reported indicator (minimum over years of the annual mean) in both runs;
  - the investment order placed at t = 97 relative to all S0 orders over 2033-2045;
  - when ordering resumes, and final capacity.

Reads results/V4_1_diagnosis/{country}_{V4_1_no_renewables,S0}/trajectories.csv.gz.
Usage: python paper_scripts/diagnose_v4_1.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / "results" / "V4_1_diagnosis"


def wide(country: str, run: str) -> pd.DataFrame:
    data = pd.read_csv(ROOT / f"{country}_{run}" / "trajectories.csv.gz")
    return data.pivot_table(index="time", columns="variable", values="value").sort_index()


def at(series: pd.Series, t: float) -> float:
    return series.ffill().loc[series.index <= t].iloc[-1]


def main() -> int:
    for country in ("brazil", "chile"):
        shock, base = wide(country, "V4_1_no_renewables"), wide(country, "S0")
        m_s, m_b = shock["Min Availability Margin"], base["Min Availability Margin"]
        print(f"== {country}")
        print(f"  minimum hourly margin at t=97: S0 {100*at(m_b, 97):.1f} %, shock {100*at(m_s, 97):.1f} %"
              f"; at t=98: S0 {100*at(m_b, 98):.1f} %, shock {100*at(m_s, 98):.1f} %")
        annual = lambda s: (100 * s.ffill()).groupby(2025 + np.floor(s.index / 12)).mean()
        a_s, a_b = annual(m_s), annual(m_b)
        print(f"  reported indicator (min over years of annual mean): S0 {a_b.min():.2f} ({int(a_b.idxmin())})"
              f", shock {a_s.min():.2f} ({int(a_s.idxmin())}); 2033 annual mean S0 {a_b[2033]:.2f}, shock {a_s[2033]:.2f}")
        i_s, i_b = shock["Total New Investment"].dropna(), base["Total New Investment"].dropna()
        pulse = i_s[(i_s.index > 96.9) & (i_s.index < 97.1)].sum()
        s0_orders = i_b[(i_b.index >= 96) & (i_b.index < 241)]
        print(f"  order at t=97 / all S0 orders 2033-2045: {pulse / s0_orders.sum():.2f}")
        resume = i_s[(i_s.index > 98) & (i_s > 0)].index.min()
        between = i_b[(i_b.index > 98) & (i_b.index < resume)]
        print(f"  shock run orders again at t={resume:.0f} (year {2025 + int(resume // 12)}); "
              f"S0 orders in {int((between > 0).sum())} of the quarter-month steps in between")
        k_s, k_b = shock["Total Generation Capacity"].dropna(), base["Total Generation Capacity"].dropna()
        print(f"  final capacity: S0 {k_b.iloc[-1]:.2f} GW, shock {k_s.iloc[-1]:.2f} GW "
              f"({100 * (k_s.iloc[-1] / k_b.iloc[-1] - 1):+.1f} %)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
