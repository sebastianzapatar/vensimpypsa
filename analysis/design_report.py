"""Report the space-filling properties of a Latin Hypercube design.

The design is verifiable without running the model, so the numbers quoted in
Appendix C.6 of the article can be checked on any machine:

    python -m analysis.design_report --design analysis/designs/chile

It reads ``samples.csv`` and the factor bounds recorded in ``metadata.json``,
maps every column back onto the unit hypercube (through log10 for factors
sampled log-uniformly) and reports the stratification, the centred L2
discrepancy and the largest pairwise correlation between factors.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Sequence

import numpy as np
from scipy.stats import qmc


def unit_design(design_dir: Path) -> tuple[np.ndarray, list[str]]:
    """Map the scaled samples back onto the unit hypercube."""
    metadata = json.loads((design_dir / "metadata.json").read_text(encoding="utf-8"))
    spec = {factor["id"]: factor for factor in metadata["factors"]}
    with (design_dir / "samples.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{design_dir / 'samples.csv'} is empty")
    names = [name for name in rows[0] if name != "run_id"]

    unit = np.empty((len(rows), len(names)))
    for index, name in enumerate(names):
        factor = spec[name]
        values = np.array([float(row[name]) for row in rows])
        lower, upper = float(factor["lower"]), float(factor["upper"])
        if factor.get("log"):
            values = np.log10(values)
            lower, upper = math.log10(lower), math.log10(upper)
        unit[:, index] = (values - lower) / (upper - lower)
    return unit, names


def report(design_dir: Path) -> None:
    unit, names = unit_design(design_dir)
    samples, dimensions = unit.shape

    # A Latin hypercube puts exactly one sample in each of the n strata of
    # every dimension; anything else means the design is not the one claimed.
    strata = np.minimum((unit * samples).astype(int), samples - 1)
    stratified = [name for i, name in enumerate(names) if len(set(strata[:, i])) == samples]

    correlation = np.corrcoef(unit, rowvar=False) - np.eye(dimensions)
    worst = np.unravel_index(np.abs(correlation).argmax(), correlation.shape)
    upper_triangle = np.abs(correlation)[np.triu_indices(dimensions, 1)]

    print(f"design            {design_dir}")
    print(f"samples x factors {samples} x {dimensions}")
    print(f"one per stratum   {len(stratified)}/{dimensions} factors", end="")
    print("" if len(stratified) == dimensions else f"  MISSING: {sorted(set(names) - set(stratified))}")
    print(f"unit coverage     [{unit.min():.5f}, {unit.max():.5f}]")
    print(f"centred L2 disc.  {qmc.discrepancy(unit, method='CD'):.6f}")
    print(
        f"max |pairwise r|  {np.abs(correlation).max():.4f} "
        f"({names[worst[0]]}, {names[worst[1]]});  mean {upper_triangle.mean():.4f}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, required=True, help="directory holding samples.csv and metadata.json")
    args = parser.parse_args(argv)
    try:
        report(args.design.resolve())
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"error: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
