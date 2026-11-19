"""Build the annual scenario series behind the scenario figures and Table 3.

Reads the H7 runs (identical to the implemented rule, see README Section 7) from
results/H_horizon_table3/{brazil,chile}/trajectories.csv.gz and writes
results/H_horizon_table3/annual_results.csv in the long format used by plot_scenarios.py.

Annual aggregation follows the article (Section 3.6):
  installed_capacity   Total Generation Capacity, last value of each year (GW)
  total_transmission   Total Transmission, last value of each year (thousand km)
  electricity_price    mean over the six zones of Electricity Tariff[Regulated, z], annual mean
  peak_margin          100 * Min Availability Margin, annual mean (%)

Usage: python paper_scripts/build_annual_results.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / "results" / "H_horizon_table3"
ZONES = [f"Electricity Tariff[Regulated,Z{i}]" for i in range(1, 7)]
METRICS = {
    "installed_capacity": ("Total installed capacity", "GW"),
    "total_transmission": ("Total transmission line length", "thousand km"),
    "electricity_price": ("Average electricity price", "USD/MWh"),
    "peak_margin": ("Peak demand capacity margin", "%"),
}


def annual(frame: pd.DataFrame) -> dict[str, pd.Series]:
    wide = frame.pivot_table(index="time", columns="variable", values="value").sort_index()
    years = 2025 + np.floor(wide.index.values / 12).astype(int)
    by_year = wide.groupby(years)
    return {
        "installed_capacity": by_year["Total Generation Capacity"].last(),
        "total_transmission": by_year["Total Transmission"].last() / 1000,
        "electricity_price": wide[ZONES].mean(axis=1).groupby(years).mean(),
        "peak_margin": (100 * wide["Min Availability Margin"]).groupby(years).mean(),
    }


def main() -> int:
    rows = []
    for country in ("brazil", "chile"):
        data = pd.read_csv(ROOT / country / "trajectories.csv.gz")
        for run, frame in data.groupby("run_id", sort=False):
            scenario, horizon = run.split("_")
            if horizon != "H7":
                continue
            for metric, series in annual(frame).items():
                label, unit = METRICS[metric]
                for year, value in series.items():
                    rows.append({"Country": country.capitalize(), "Metric": metric,
                                 "Metric label": label, "Unit": unit, "Year": int(year),
                                 "Scenario": scenario, "Value": float(value)})
    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "annual_results.csv", index=False)
    print(f"wrote {ROOT / 'annual_results.csv'}: {len(out)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
