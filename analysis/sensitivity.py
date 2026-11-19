"""Turn a completed Latin Hypercube design into the figures and tables of B5.

Two products are computed from ``results.csv`` and ``trajectories.csv``:

*bands*    the 5-95 % percentile envelope of every output trajectory, which is
           drawn behind the scenario lines of Figures 7-10;
*tornado*  a ranking of the uncertain factors by their contribution to the
           variance of each scalar output, from standardised regression
           coefficients on the standardised design.

Standardised regression coefficients are only meaningful while the linear
model explains most of the variance, so the coefficient of determination is
reported next to every ranking and a Spearman rank correlation is computed
alongside it. When R^2 falls below ``--min-r2`` the ranking is reported from
the rank correlation instead, and the figure says so.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

DEFAULT_LOW = 5.0
DEFAULT_HIGH = 95.0


# --------------------------------------------------------------------------- #
# Sensitivity indices
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Ranking:
    output: str
    factors: tuple[str, ...]
    src: np.ndarray
    spearman: np.ndarray
    r2: float
    method: str

    def to_frame(self) -> pd.DataFrame:
        frame = pd.DataFrame(
            {
                "factor": self.factors,
                "src": self.src,
                "spearman": self.spearman,
            }
        )
        frame["ranked_by"] = self.method
        frame["r2"] = self.r2
        frame["output"] = self.output
        key = "src" if self.method == "src" else "spearman"
        return frame.reindex(
            frame[key].abs().sort_values(ascending=False).index
        ).reset_index(drop=True)


def _standardise(values: np.ndarray) -> np.ndarray:
    spread = values.std(axis=0, ddof=1)
    if np.any(spread == 0):
        raise ValueError("a column of the design has zero variance")
    return (values - values.mean(axis=0)) / spread


def rank_factors(
    design: pd.DataFrame, response: pd.Series, min_r2: float = 0.7
) -> Ranking:
    """Rank the factors driving one scalar output."""
    if len(design) != len(response):
        raise ValueError("design and response must have the same length")
    if len(design) <= design.shape[1] + 1:
        raise ValueError(
            f"{len(design)} samples cannot identify {design.shape[1]} factors"
        )
    x = _standardise(design.to_numpy(dtype=float))
    y = response.to_numpy(dtype=float)
    if y.std(ddof=1) == 0:
        raise ValueError(f"output {response.name!r} is constant across the design")
    y_std = (y - y.mean()) / y.std(ddof=1)

    coefficients, *_ = np.linalg.lstsq(x, y_std, rcond=None)
    residual = y_std - x @ coefficients
    r2 = float(1.0 - residual.var(ddof=1) / y_std.var(ddof=1))

    ranks_x = design.rank().to_numpy(dtype=float)
    ranks_y = pd.Series(y).rank().to_numpy(dtype=float)
    spearman = np.array(
        [np.corrcoef(ranks_x[:, i], ranks_y)[0, 1] for i in range(ranks_x.shape[1])]
    )
    return Ranking(
        output=str(response.name),
        factors=tuple(design.columns),
        src=coefficients,
        spearman=spearman,
        r2=r2,
        method="src" if r2 >= min_r2 else "spearman",
    )


def percentile_bands(
    trajectories: pd.DataFrame, low: float = DEFAULT_LOW, high: float = DEFAULT_HIGH
) -> pd.DataFrame:
    """Collapse the per-run trajectories into a percentile envelope."""
    required = {"run_id", "variable", "time", "value"}
    missing = required.difference(trajectories.columns)
    if missing:
        raise ValueError(f"trajectories.csv is missing {', '.join(sorted(missing))}")
    grouped = trajectories.groupby(["variable", "time"])["value"]
    bands = grouped.agg(
        runs="count",
        median="median",
        mean="mean",
        low=lambda values: np.percentile(values, low),
        high=lambda values: np.percentile(values, high),
    ).reset_index()
    bands.attrs["low"] = low
    bands.attrs["high"] = high
    return bands


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #


def tornado_figure(rankings: Sequence[Ranking], path: Path, country: str) -> None:
    """Draw the tornado diagram, sized and typed for the journal column."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 9,
            "pdf.fonttype": 42,
            "savefig.bbox": "tight",
        }
    )
    columns = min(len(rankings), 2)
    rows = (len(rankings) + columns - 1) // columns
    figure, axes = plt.subplots(
        rows, columns, figsize=(7.2, 2.6 * rows), squeeze=False
    )
    for axis, ranking in zip(axes.ravel(), rankings, strict=False):
        frame = ranking.to_frame()
        key = "src" if ranking.method == "src" else "spearman"
        values = frame[key].to_numpy()[::-1]
        labels = frame["factor"].to_numpy()[::-1]
        positions = np.arange(len(values))
        # A diverging pair, not red/green: the sign is the direction of the
        # effect and must stay readable in greyscale and for colour vision
        # deficiency.
        colours = ["#2c6fb5" if value >= 0 else "#c26a2b" for value in values]
        axis.barh(positions, values, color=colours, height=0.7)
        axis.set_yticks(positions, labels)
        axis.axvline(0.0, color="0.3", linewidth=0.8)
        axis.set_xlabel(
            "Standardised regression coefficient"
            if ranking.method == "src"
            else "Spearman rank correlation"
        )
        axis.set_title(f"{ranking.output}\n$R^2$ = {ranking.r2:.2f}", loc="left")
        axis.grid(axis="x", color="0.9", linewidth=0.6)
        axis.set_axisbelow(True)
    for axis in axes.ravel()[len(rankings) :]:
        axis.set_visible(False)
    figure.suptitle(f"Sensitivity ranking — {country}", x=0.01, ha="left")
    figure.tight_layout()
    figure.savefig(path)
    plt.close(figure)


def latex_table(rankings: Sequence[Ranking], country: str, top: int = 5) -> str:
    """Emit the ranking as the LaTeX body of the sensitivity table."""
    lines = [
        r"\begin{tabular}{@{}llrrr@{}}",
        r"\toprule",
        r"Output & Factor & SRC & Spearman & $R^2$\\",
        r"\midrule",
    ]
    for ranking in rankings:
        frame = ranking.to_frame().head(top)
        for position, row in enumerate(frame.itertuples()):
            output = ranking.output if position == 0 else ""
            r2 = f"{ranking.r2:.2f}" if position == 0 else ""
            lines.append(
                f"{output} & {row.factor} & {row.src:+.3f} & "
                f"{row.spearman:+.3f} & {r2}\\\\"
            )
        lines.append(r"\addlinespace")
    lines[-1] = r"\bottomrule"
    lines.append(r"\end{tabular}")
    lines.append(f"% ranking for {country}; top {top} factors per output")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #


def analyse(
    results_dir: Path, country: str, min_r2: float, low: float, high: float, top: int
) -> None:
    results_path = results_dir / "results.csv"
    if not results_path.exists():
        raise FileNotFoundError(
            f"{results_path} not found. Run the design with analysis/lhs.py first."
        )
    results = pd.read_csv(results_path)
    samples = pd.read_csv(results_dir / "samples.csv")
    factors = [column for column in samples.columns if column != "run_id"]
    outputs = [
        column
        for column in results.columns
        if column not in factors and column != "run_id"
    ]
    if not outputs:
        raise ValueError("results.csv holds no output columns")

    design = results[factors]
    rankings = [rank_factors(design, results[output], min_r2) for output in outputs]

    table = pd.concat([ranking.to_frame() for ranking in rankings], ignore_index=True)
    table.to_csv(results_dir / "sensitivity_indices.csv", index=False)
    (results_dir / "sensitivity_table.tex").write_text(
        latex_table(rankings, country, top) + "\n", encoding="utf-8"
    )
    tornado_figure(rankings, results_dir / "tornado.pdf", country)

    summary = {
        "country": country,
        "samples": int(len(results)),
        "factors": factors,
        "outputs": outputs,
        "min_r2": min_r2,
        "rankings": [
            {
                "output": ranking.output,
                "r2": ranking.r2,
                "ranked_by": ranking.method,
                "top": ranking.to_frame().head(top)["factor"].tolist(),
            }
            for ranking in rankings
        ],
    }

    trajectories_path = results_dir / "trajectories.csv"
    if trajectories_path.exists():
        bands = percentile_bands(pd.read_csv(trajectories_path), low, high)
        bands.to_csv(results_dir / "bands.csv", index=False)
        summary["bands"] = {
            "low_percentile": low,
            "high_percentile": high,
            "variables": sorted(bands["variable"].unique().tolist()),
            "runs_per_point": int(bands["runs"].min()),
        }
    else:
        summary["bands"] = None
        print(
            f"note: {trajectories_path.name} not found, percentile bands skipped",
            file=sys.stderr,
        )

    (results_dir / "sensitivity_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"sensitivity indices  -> {results_dir / 'sensitivity_indices.csv'}")
    print(f"LaTeX table body     -> {results_dir / 'sensitivity_table.tex'}")
    print(f"tornado diagram      -> {results_dir / 'tornado.pdf'}")
    if summary["bands"]:
        print(f"percentile bands     -> {results_dir / 'bands.csv'}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--country", default="")
    parser.add_argument("--min-r2", type=float, default=0.7)
    parser.add_argument("--low", type=float, default=DEFAULT_LOW)
    parser.add_argument("--high", type=float, default=DEFAULT_HIGH)
    parser.add_argument("--top", type=int, default=5)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        results_dir = args.results_dir.resolve()
        country = args.country or results_dir.name.capitalize()
        analyse(results_dir, country, args.min_r2, args.low, args.high, args.top)
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
