"""Table-3 indicators for the fixed-horizon reruns (review R1.4).

The indicators are computed exactly as in Supplementary Data summary_annual.csv:

* generation capacity and line length: value at the end of the horizon;
* price: annual mean of the zonal average of Electricity Tariff[Regulated, Z1..Z6]
  (verified against the published Brazil S0 series to 3e-4 USD/MWh), then the mean
  and the linearly interpolated 95th percentile of the 26 annual values;
* margin: annual mean of Min Availability Margin (in %), then its mean and minimum.

Years follow the published export: point k of the 0.25-month series belongs to
year 2025 + floor(t / 12), with the single point at t = 300 assigned to 2050.

Usage:
    python analysis/summarise_horizon.py results/horizon
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ZONES = [f"Electricity Tariff[Regulated,Z{i}]" for i in range(1, 7)]


def indicators(frame: pd.DataFrame) -> dict[str, float]:
    wide = frame.pivot_table(index="time", columns="variable", values="value")
    years = 2025 + np.floor(wide.index.values / 12).astype(int)
    price = wide[ZONES].mean(axis=1).groupby(years).mean()
    margin = (100 * wide["Min Availability Margin"]).groupby(years).mean()
    return {
        "gen_GW": wide["Total Generation Capacity"].iloc[-1],
        "lines_1000km": wide["Total Transmission"].iloc[-1] / 1000,
        "price_mean": price.mean(),
        "price_p95": price.quantile(0.95),
        "margin_mean": margin.mean(),
        "margin_min": margin.min(),
        "long_gen_horizon": wide["Use Long Generation Horizon"].mean(),
        "short_trans_horizon": wide["Use Short Transmission Horizon"].mean(),
    }


def main(root: Path) -> int:
    rows = []
    for country in ("brazil", "chile"):
        path = root / country / "trajectories.csv"
        if not path.exists():
            path = path.with_suffix(".csv.gz")  # as shipped in the replication package
        if not path.exists():
            continue
        data = pd.read_csv(path)
        for run, frame in data.groupby("run_id", sort=False):
            scenario, horizon = run.split("_")
            rows.append({"country": country.capitalize(), "scenario": scenario,
                         "horizon": horizon, **indicators(frame)})
    table = pd.DataFrame(rows)
    table.to_csv(root / "summary_horizon.csv", index=False)
    with pd.option_context("display.width", 200, "display.max_rows", 100):
        print(table.round(2).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "results/H_horizon_table3")))
