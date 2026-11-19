"""Units check A1: effect of the DER term in 'Generation Capacity Cost by Tech' on 'Total System Cost'.

Model:   Generation Capacity Cost by Tech[ZTech] = K[ZTech]*c[ZTech] + Total DER Capacity*c[Z1PV]
         summed over the 84 ZTech elements, with Total DER Capacity in GW and c in USD/MW,
         so DER enters as 84 * D_GW * c_PV.
Correct: D_MW * c_PV = 1000 * D_GW * c_PV.
Corrected Total System Cost (MMUSD) = TSC + (1000 - 84) * D_GW * c_PV / 1e6.

Usage: python analysis/der_cost_check.py   (reads results/der/{country}_{S0,S3}/trajectories.csv)
"""
from pathlib import Path
import pandas as pd

NZT = 84
ROOT = Path(__file__).resolve().parents[1] / "results" / "der"


def final_values(country: str, scen: str):
    t = pd.read_csv(ROOT / f"{country}_{scen}" / "trajectories.csv")
    p = t.pivot_table(index="time", columns="variable", values="value").sort_index().ffill().dropna()
    d, c, tsc = p["Total DER Capacity"], p["Capital Generation Cost[Z1PV]"], p["Total System Cost"]
    corr = tsc + (1000 - NZT) * d * c / 1e6
    return d.iloc[-1], c.iloc[-1], tsc.iloc[-1], corr.iloc[-1], p["Total Generation Capacity"].iloc[-1]


rows = []
for country in ("chile", "brazil"):
    res = {}
    for scen in ("S0", "S3"):
        try:
            res[scen] = final_values(country, scen)
        except FileNotFoundError:
            print(f"{country} {scen}: missing")
            continue
        d, c, tsc, corr, k = res[scen]
        print(f"{country} {scen}: DER {d:.2f} GW (total gen {k:.2f} GW), c_PV {c:,.0f} USD/MW, "
              f"TSC 2050 {tsc:,.0f} -> corrected {corr:,.0f} MMUSD ({100*(corr/tsc-1):+.2f} %)")
    if len(res) == 2:
        a, b = res["S0"], res["S3"]
        rep, cor = 100 * (b[2] / a[2] - 1), 100 * (b[3] / a[3] - 1)
        print(f"{country} S3 vs S0 (2050): reported {rep:+.2f} %  corrected {cor:+.2f} %")
        rows.append({"country": country, "reported_pct": rep, "corrected_pct": cor,
                     "level_bias_S0_pct": 100 * (a[3] / a[2] - 1)})
if rows:
    pd.DataFrame(rows).to_csv(ROOT / "der_cost_check.csv", index=False)
