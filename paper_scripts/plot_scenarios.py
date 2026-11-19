"""Figures 7-10: the eight scenario trajectories, as vector output.

Replaces the raster figures lifted from the submitted manuscript, which
Reviewer #4 could not read.  What changes:

* PDF rather than PNG, so nothing is resampled at final column width;
* 8 pt minimum type size anywhere in the figure, 7.2 in wide (Applied Energy
  full column), which is the size the figure is placed at, so no shrinking
  happens after export;
* every scenario carries **both** a colour and a dash pattern, so the panels
  survive greyscale printing and the common forms of colour vision deficiency;
* the two countries are separate panels of the same figure rather than one
  crowded axis.

The 5--95 % envelope of the Latin-hypercube experiment is drawn behind the
scenario lines on the two figures where the sampled output is the same
quantity the figure plots -- ``Total Generation Capacity`` and
``Total Transmission``.  It is deliberately *not* drawn on the price and margin
figures: the sensitivity experiment records ``Aggregated Generation Tariff[f0]``
and ``Capacity Margin[f0]``, which are different aggregates from the zonal mean
price and the derated peak margin that those figures report, and overlaying one
on the other would put a band around a quantity it was not computed for.

Usage:
    python plot_scenarios.py
    python plot_scenarios.py --no-bands
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "results" / "H_horizon_table3" / "annual_results.csv"
BANDS = HERE.parent / "results" / "B5_latin_hypercube"
OUTDIR = HERE / "figures"

# The scenario matrix of Table 4, in the order it is presented there.
SCENARIOS = ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7"]
LABELS = {
    "S0": "S0 nominal",
    "S1": "S1 generation delay",
    "S2": "S2 transmission delay",
    "S3": "S3 combined delay",
    "S4": "S4 combined + BESS",
    "S5": "S5 combined + GETs",
    "S6": "S6 combined + BESS + GETs",
    "S7": "S7 nominal + BESS + GETs",
}
# Colour and dash are assigned together: the figure has to read in greyscale.
STYLE = {
    "S0": ("#1b1b1b", (None, None), 1.6),
    "S1": ("#0072B2", (4, 1.6), 1.3),
    "S2": ("#009E73", (1.4, 1.4), 1.3),
    "S3": ("#D55E00", (None, None), 1.6),
    "S4": ("#CC79A7", (5, 1.4, 1.2, 1.4), 1.3),
    "S5": ("#56B4E9", (2.6, 1.2, 0.8, 1.2), 1.3),
    "S6": ("#E69F00", (6, 1.8), 1.3),
    "S7": ("#7A5195", (1.2, 1.0), 1.3),
}

# metric -> (axis label, sampled variable that is the same quantity, scale)
METRICS = {
    "installed_capacity": ("Installed generation capacity (GW)",
                           "Total Generation Capacity", 1.0),
    "total_transmission": ("Total transmission line length (thousand km)",
                           "Total Transmission", 1e-3),
    "electricity_price": ("Average electricity price (USD/MWh)", None, 1.0),
    "peak_margin": ("Peak demand capacity margin (%)", None, 1.0),
}
COUNTRY_DIR = {"Brazil": "brazil", "Chile": "chile"}

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.labelsize": 9,
    "axes.titlesize": 10,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "axes.linewidth": 0.6,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.dpi": 150,
    "savefig.bbox": "tight",
    "pdf.fonttype": 42,          # embed as TrueType, not Type 3
})


def load_bands(country: str, variable: str, scale: float) -> pd.DataFrame | None:
    """Return the 5-95 % envelope on a calendar-year axis, or None."""
    path = BANDS / COUNTRY_DIR[country] / "bands.csv"
    if not path.exists():
        return None
    band = pd.read_csv(path)
    band = band[band["variable"] == variable].copy()
    if band.empty:
        return None
    for column in ("time", "low", "high"):
        band[column] = pd.to_numeric(band[column], errors="coerce")
    band = band.dropna(subset=["time", "low", "high"])
    # The model runs 300 months from 2025; the figures are on calendar years.
    band["year"] = 2025 + band["time"] / 12.0
    band["low"] *= scale
    band["high"] *= scale
    return band.sort_values("year")


def panel(ax, data: pd.DataFrame, band: pd.DataFrame | None, ylabel: str,
          title: str) -> None:
    if band is not None:
        ax.fill_between(band["year"], band["low"], band["high"],
                        color="#9aa0a6", alpha=0.22, linewidth=0, zorder=1,
                        label="5-95 % parameter envelope")
    # Several scenarios produce trajectories that coincide to the resolution of
    # the figure -- that is a result, not a plotting artefact -- so each line is
    # drawn slightly thinner than the one before it and every one carries its
    # own dash period.  A covered curve then still shows through the gaps of the
    # curves above it instead of disappearing under the last one drawn.
    for order, scenario in enumerate(SCENARIOS):
        series = data[data["Scenario"] == scenario].sort_values("Year")
        if series.empty:
            continue
        colour, dashes, _ = STYLE[scenario]
        line, = ax.plot(series["Year"], series["Value"], color=colour,
                        linewidth=2.1 - 0.13 * order, zorder=3 + order,
                        solid_capstyle="butt", label=LABELS[scenario])
        if dashes[0] is not None:
            line.set_dashes(dashes)
    ax.set_xlabel("Year")
    ax.set_ylabel(ylabel)
    ax.set_title(title, loc="left", fontweight="bold")
    ax.grid(True, which="major", axis="y", color="#e3e3e3", linewidth=0.5)
    ax.set_axisbelow(True)
    ax.margins(x=0.01)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-bands", action="store_true",
                        help="omit the Latin-hypercube envelope")
    args = parser.parse_args()

    if not RESULTS.exists():
        raise SystemExit(f"missing {RESULTS}")
    frame = pd.read_csv(RESULTS)
    OUTDIR.mkdir(exist_ok=True)

    written = []
    for metric, (ylabel, variable, scale) in METRICS.items():
        for country in ("Brazil", "Chile"):
            data = frame[(frame["Country"] == country)
                         & (frame["Metric"] == metric)]
            if data.empty:
                print(f"  skip {country} {metric}: not in {RESULTS.name}")
                continue
            band = None
            if variable and not args.no_bands:
                band = load_bands(country, variable, scale)

            fig, ax = plt.subplots(figsize=(7.2, 3.1))
            panel(ax, data, band, ylabel, f"{country}")
            handles, labels = ax.get_legend_handles_labels()
            ax.legend(handles, labels, ncol=3, frameon=False,
                      loc="upper left", bbox_to_anchor=(0.0, -0.24),
                      handlelength=2.6, columnspacing=1.4)
            out = OUTDIR / f"{country.lower()}_{metric}.pdf"
            fig.savefig(out)
            plt.close(fig)
            written.append((out.name, "with band" if band is not None else "no band"))

    for name, note in written:
        print(f"  wrote figures/{name}  ({note})")
    print(f"{len(written)} vector figures written to {OUTDIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
