"""Experiment B1: the response surface of the delay sweep, and its interaction term.

Reads the trajectories of the 5x5 sweep (results/b1_{chile,brazil}) and produces

  figures/delay_sweep_{country}.pdf   four response surfaces per country
  generated/b1_numbers.tex            the macros Section 5.3 cites in prose

The four indicators are the ones the mean-day representation supports:

  final installed generation capacity (GW)
  final transmission capacity (GW)
  mean generation tariff over the horizon (USD/MWh)
  minimum capacity margin over the horizon (dimensionless ratio)

For each one the surface is summarised by the linear model

    X = a + b*dtau_g + c*dtau_i + d*dtau_g*dtau_i

so that b and c are the marginal effect of one additional month of generation
and of transmission delay, and d answers the question the reviewers asked:
whether simultaneous delays are worse than the sum of the isolated ones
(d < 0 for a quantity that delay reduces), or merely additive (d = 0).  R^2 is
reported so that a reader can see whether the linear-plus-interaction summary is
a fair description of the surface or a smoothing of something more structured.

Usage:  python analyse_b1.py [--results C:/b5/vensimpypsa/results]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def _trajectories(directory):
    """Shipped as trajectories.csv.gz in the replication package; pandas reads both."""
    from pathlib import Path as _P
    p = _P(directory) / "trajectories.csv"
    return p if p.exists() else p.with_suffix(".csv.gz")

HERE = Path(__file__).resolve().parent
NAME = re.compile(r"^B1_g(\d+)_i(\d+)$")

INDICATORS = [
    ("Total Generation Capacity", "last", 1.0,
     "Final installed capacity", "GW"),
    ("Total Transmission", "last", 1e-3,
     "Final transmission capacity", "GW"),
    ("Aggregated Generation Tariff[f0]", "mean", 1.0,
     "Mean generation tariff", "% vs nominal"),
    ("Capacity Margin[f0]", "min", 1.0,
     "Minimum capacity margin", "% vs nominal"),
]

# Panels shown as a percentage change from the nominal cell (0,0) rather than in
# levels: the sampled tariff and margin are the model's own aggregates, not the
# zonal mean price and derated margin of Table 6, and putting a unit on them
# would invite the two to be read as the same quantity.
AS_PERCENT = {"Aggregated Generation Tariff[f0]", "Capacity Margin[f0]"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.labelsize": 9,
    "axes.titlesize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "legend.fontsize": 8, "axes.linewidth": 0.6, "savefig.bbox": "tight",
    "pdf.fonttype": 42,
})


def load(country_dir: Path) -> pd.DataFrame:
    path = _trajectories(country_dir)
    if not path.exists():
        raise SystemExit(f"missing {path} -- has the B1 batch finished?")
    frame = pd.read_csv(path)
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame["time"] = pd.to_numeric(frame["time"], errors="coerce")
    return frame.dropna(subset=["value", "time"])


def summarise(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for run_id, block in frame.groupby("run_id"):
        match = NAME.match(str(run_id))
        if not match:
            continue
        row = {"scenario": run_id,
               "dtau_g": int(match.group(1)),
               "dtau_i": int(match.group(2))}
        for variable, how, scale, _, _ in INDICATORS:
            series = block[block["variable"] == variable]["value"]
            if series.empty:
                row[variable] = np.nan
                continue
            if how == "last":
                value = block[block["variable"] == variable].sort_values("time")["value"].iloc[-1]
            elif how == "mean":
                value = series.mean()
            else:
                value = series.min()
            row[variable] = float(value) * scale
        rows.append(row)
    if not rows:
        raise SystemExit("no B1 scenarios found in the trajectories")
    return pd.DataFrame(rows).sort_values(["dtau_g", "dtau_i"]).reset_index(drop=True)


def fit(table: pd.DataFrame, variable: str) -> dict[str, float]:
    """Least squares for a + b*g + c*i + d*g*i, with R^2."""
    g = table["dtau_g"].to_numpy(float)
    i = table["dtau_i"].to_numpy(float)
    y = table[variable].to_numpy(float)
    keep = ~np.isnan(y)
    g, i, y = g[keep], i[keep], y[keep]
    design = np.column_stack([np.ones_like(g), g, i, g * i])
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    residual = y - design @ beta
    total = y - y.mean()
    r2 = 1.0 - float(residual @ residual) / float(total @ total) if total.any() else np.nan
    return {"intercept": beta[0], "b_gen": beta[1], "c_trans": beta[2],
            "d_inter": beta[3], "r2": r2, "n": int(keep.sum())}


def surface_figure(table: pd.DataFrame, country: str, out: Path) -> None:
    levels = sorted(table["dtau_g"].unique())
    fig, axes = plt.subplots(1, 4, figsize=(7.2, 2.15))
    for ax, (variable, _, _, label, unit) in zip(axes, INDICATORS):
        grid = table.pivot(index="dtau_g", columns="dtau_i", values=variable)
        values = grid.to_numpy(float)
        if variable in AS_PERCENT:
            values = 100.0 * (values / values[0, 0] - 1.0)
        image = ax.imshow(values, origin="lower", aspect="auto", cmap="viridis")
        ax.set_xticks(range(len(levels)), [str(v) for v in levels])
        ax.set_yticks(range(len(levels)), [str(v) for v in levels])
        ax.set_xlabel(r"$\Delta\tau^{i}$ (months)")
        ax.set_ylabel(r"$\Delta\tau^{g}$ (months)")
        ax.set_title(f"{label}\n({unit})", fontsize=8)
        bar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.03)
        bar.ax.tick_params(labelsize=7)
    fig.suptitle(country, x=0.02, ha="left", fontweight="bold", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(out)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path,
                        default=Path(__file__).resolve().parents[1] / "results")
    args = parser.parse_args()

    (HERE / "generated").mkdir(exist_ok=True)
    (HERE / "figures").mkdir(exist_ok=True)
    macros = []

    for country, folder in (("Brazil", "B1_delay_sweep/brazil"), ("Chile", "B1_delay_sweep/chile")):
        directory = args.results / folder
        table = summarise(load(directory))
        table.to_csv(HERE / "generated" / f"b1_{country.lower()}.csv", index=False)
        surface_figure(table, country,
                       HERE / "figures" / f"delay_sweep_{country.lower()}.pdf")
        print(f"{country}: {len(table)} of 25 cells")

        for variable, _, _, label, unit in INDICATORS:
            f = fit(table, variable)
            tag = f"{country[:2]}{variable.split()[1][:3] if len(variable.split()) > 1 else variable[:3]}"
            print(f"  {label:32s} b_gen={f['b_gen']:+.4g}  c_trans={f['c_trans']:+.4g}"
                  f"  d_inter={f['d_inter']:+.3g}  R2={f['r2']:.3f}")
            macros.append((country, label, unit, f))

    with (HERE / "generated" / "b1_numbers.tex").open("w", encoding="utf-8") as fh:
        fh.write("% Generated by analyse_b1.py -- do not edit by hand.\n")
        fh.write("% One row per country and indicator: marginal effect of one month of\n")
        fh.write("% generation delay, of one month of transmission delay, the interaction\n")
        fh.write("% term, and the R^2 of the linear-plus-interaction summary.\n")
        for country, label, unit, f in macros:
            fh.write(f"% {country} -- {label} ({unit})\n")
            fh.write(f"%   b_gen={f['b_gen']:.6g} c_trans={f['c_trans']:.6g} "
                     f"d_inter={f['d_inter']:.6g} R2={f['r2']:.4f} n={f['n']}\n")
        fh.write("\n")
        for country, label, unit, f in macros:
            row = (f"{country} & {label} ({unit}) & {f['b_gen']:+.3g} & "
                   f"{f['c_trans']:+.3g} & {f['d_inter']:+.2g} & {f['r2']:.2f}")
            fh.write(row + r" \\" + "\n")
    print(f"\nwrote {HERE / 'generated' / 'b1_numbers.tex'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
