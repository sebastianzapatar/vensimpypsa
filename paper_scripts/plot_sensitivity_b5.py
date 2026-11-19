"""Figures of Appendix C.6 from the completed B5 Latin-hypercube design.

Reads the two ``sensitivity_indices.csv`` written by ``analysis/sensitivity.py``
and draws one tornado panel per output and country, on a factor ordering that is
common to the two countries so that the panels of a row can be read against each
other. Two figures are produced: the outputs whose linear ranking is identified
(R^2 >= 0.7 in both countries) and the outputs where it is not.

Usage:
    python plot_sensitivity_b5.py --results ../../resultados_B5 --out figures
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

POS = "#2166AC"
NEG = "#B2182B"

LABEL = {
    "m_bar": r"$\bar m$  desired margin",
    "sigma": r"$\sigma$  grid security margin",
    "f_min": r"$F_{\min}$  min. grid increment",
    "alpha_get": r"$\alpha_i$  allowed GET share",
    "pi_star": r"$\Pi^{*}$  profitability threshold",
    "theta": r"$\theta$  logit scale",
    "lifetime": r"$L_g$  technical lifetime",
    "discount": r"$r$  discount rate",
    "trans_cost": "transmission cost",
    "capex_res": "CAPEX PV / wind / BESS",
    "demand_growth": "demand growth",
    "hydro_inflow": "hydrological inflows",
}

SHORT = {
    "Total Generation Capacity": "Installed generation capacity",
    "Total Transmission": "Total transmission capacity",
    "Total Interconnection Capacity": "Interconnection capacity",
    "Capacity Margin[f0]": "Capacity margin",
    "Aggregated Generation Tariff[f0]": "Generation tariff",
    "Congestion Tariff[f0]": "Congestion charge",
    "Total New Investment": "New investment",
    "Total System Cost": "Total system cost",
}

IDENTIFIED = [
    "Total Generation Capacity",
    "Total Transmission",
    "Capacity Margin[f0]",
    "Total System Cost",
]
WEAK = [
    "Total Interconnection Capacity",
    "Aggregated Generation Tariff[f0]",
    "Congestion Tariff[f0]",
    "Total New Investment",
]


def load(root: Path) -> dict[str, pd.DataFrame]:
    return {
        "Brazil": pd.read_csv(root / "brazil" / "sensitivity_indices.csv"),
        "Chile": pd.read_csv(root / "chile" / "sensitivity_indices.csv"),
    }


def panel(ax, frame: pd.DataFrame, order: list[str], title: str,
          lim: float | None = None) -> None:
    """One tornado panel: bars on ``order``, top of the axis first."""
    if frame is None or frame.empty:
        ax.text(0.5, 0.5, "output constant\nacross the design",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=7.5, color="0.35", style="italic")
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels([""] * len(order))
        ax.tick_params(axis="y", length=0)
        ax.set_title(title, fontsize=8, loc="left")
        ax.set_xlim(-(lim or 1.0), lim or 1.0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        return

    f = frame.set_index("factor")
    method = f["ranked_by"].iloc[0]
    key = "src" if method == "src" else "spearman"
    r2 = float(f["r2"].iloc[0])
    v = f.reindex(order)[key].fillna(0.0).values

    y = np.arange(len(order))[::-1]
    ax.barh(y, v, height=0.68,
            color=[POS if x >= 0 else NEG for x in v],
            edgecolor="none")
    ax.axvline(0, color="0.25", lw=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels([LABEL[o] for o in order], fontsize=7)
    ax.tick_params(axis="x", labelsize=7)
    ax.tick_params(axis="y", length=0)
    ax.set_ylim(-0.7, len(order) - 0.3)
    if lim is None:
        lim = max(0.35, 1.12 * float(np.abs(v).max()))
    ax.set_xlim(-lim, lim)
    tag = "SRC" if method == "src" else "Spearman rank corr."
    ax.set_title(f"{title}\n$R^2={r2:.2f}$   ranked by {tag}",
                 fontsize=8, loc="left", linespacing=1.35)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x", lw=0.4, color="0.85")
    ax.set_axisbelow(True)


def common_order(frames: dict[str, pd.DataFrame], output: str) -> list[str]:
    """Factor order shared by the two panels of a row: pooled mean |index|."""
    pooled: dict[str, list[float]] = {}
    for frame in frames.values():
        sub = frame[frame["output"] == output]
        if sub.empty:
            continue
        key = "src" if sub["ranked_by"].iloc[0] == "src" else "spearman"
        for factor, value in zip(sub["factor"], sub[key]):
            pooled.setdefault(factor, []).append(abs(float(value)))
    if not pooled:
        return list(LABEL)
    return sorted(pooled, key=lambda k: -float(np.mean(pooled[k])))


def row_limit(frames: dict[str, pd.DataFrame], output: str) -> float:
    """One x-scale per row, so the two country panels are read against each other."""
    peak = 0.0
    for frame in frames.values():
        sub = frame[frame["output"] == output]
        if sub.empty:
            continue
        key = "src" if sub["ranked_by"].iloc[0] == "src" else "spearman"
        peak = max(peak, float(sub[key].abs().max()))
    return max(0.35, 1.12 * peak)


def figure(frames: dict[str, pd.DataFrame], outputs: list[str], path: Path) -> None:
    n = len(outputs)
    # Sized to the text width of the manuscript, so the labels come out at the
    # size they are set here rather than shrunk by \includegraphics. Twelve
    # factor names need about 2.7 in of panel height to stay legible, which is
    # why the outputs are drawn two at a time rather than four.
    fig, axes = plt.subplots(n, 2, figsize=(6.7, 2.7 * n), sharey=False)
    axes = np.atleast_2d(axes)
    for i, output in enumerate(outputs):
        order = common_order(frames, output)
        lim = row_limit(frames, output)
        left_has_data = not frames["Brazil"][
            frames["Brazil"]["output"] == output].empty
        for j, country in enumerate(("Brazil", "Chile")):
            sub = frames[country]
            sub = sub[sub["output"] == output]
            panel(axes[i, j], sub if not sub.empty else None, order,
                  f"{country} — {SHORT.get(output, output)}", lim=lim)
            # the factor names are printed once per row, on whichever panel has data
            if (j == 1 and left_has_data) or (j == 0 and not left_has_data):
                axes[i, j].set_yticklabels([])
            elif j == 1:
                axes[i, j].set_yticks(np.arange(len(order))[::-1])
                axes[i, j].set_yticklabels([LABEL[o] for o in order], fontsize=7)
            if i == n - 1:
                axes[i, j].set_xlabel("standardised index", fontsize=7.5)
    fig.tight_layout(h_pad=1.9, w_pad=0.9)
    fig.savefig(path, bbox_inches="tight")
    fig.savefig(path.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {path} and {path.with_suffix('.png')}")


# --------------------------------------------------------------------------- #
# Envelopes
# --------------------------------------------------------------------------- #

BAND_UNIT = {
    "Total Generation Capacity": "GW",
    "Total Transmission": "km",
    "Capacity Margin[f0]": "ratio",
    "Total System Cost": "MMUSD",
}

START_YEAR = 2025


def bands(root: Path, outputs: list[str], path: Path) -> None:
    """P5-P95 envelope of each trajectory, one row per output, one column per country."""
    frames = {"Brazil": pd.read_csv(root / "brazil" / "bands.csv"),
              "Chile": pd.read_csv(root / "chile" / "bands.csv")}
    n = len(outputs)
    fig, axes = plt.subplots(n, 2, figsize=(6.7, 1.55 * n))
    axes = np.atleast_2d(axes)
    for i, output in enumerate(outputs):
        for j, country in enumerate(("Brazil", "Chile")):
            ax = axes[i, j]
            sub = frames[country]
            sub = sub[sub["variable"] == output].sort_values("time")
            year = START_YEAR + sub["time"].values / 12.0
            ax.fill_between(year, sub["low"], sub["high"], color=POS, alpha=0.18,
                            linewidth=0, label="P5--P95 over the design")
            ax.plot(year, sub["median"], color=POS, lw=1.3, label="median")
            ax.set_title(f"{country} — {SHORT.get(output, output)}",
                         fontsize=8, loc="left")
            ax.set_ylabel(BAND_UNIT.get(output, ""), fontsize=7.5)
            ax.tick_params(labelsize=7)
            # no shared exponent above the axis: the magnitudes differ by country
            ax.yaxis.set_major_formatter(
                matplotlib.ticker.FuncFormatter(
                    lambda v, _: f"{v:,.0f}" if abs(v) >= 100 else f"{v:g}"))
            ax.grid(lw=0.4, color="0.88")
            ax.set_axisbelow(True)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            ax.set_xlim(year.min(), year.max())
            if i == n - 1:
                ax.set_xlabel("year", fontsize=7.5)
            if i == 0 and j == 0:
                ax.legend(fontsize=6.5, frameon=False, loc="upper left")
    fig.tight_layout(h_pad=1.5, w_pad=1.2)
    fig.savefig(path, bbox_inches="tight")
    fig.savefig(path.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {path} and {path.with_suffix('.png')}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="../results/B5_latin_hypercube", type=Path)
    ap.add_argument("--out", default="figures", type=Path)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    frames = load(args.results)
    figure(frames, IDENTIFIED[:2], args.out / "tornado_quantity.pdf")
    figure(frames, IDENTIFIED[2:], args.out / "tornado_adequacy.pdf")
    figure(frames, WEAK[:2], args.out / "tornado_weak_a.pdf")
    figure(frames, WEAK[2:], args.out / "tornado_weak_b.pdf")
    bands(args.results, IDENTIFIED, args.out / "sensitivity_bands.pdf")


if __name__ == "__main__":
    main()
