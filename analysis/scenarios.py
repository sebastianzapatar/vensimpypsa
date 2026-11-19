"""Run the eight scenarios of Section 5.1 (experiment A1) from Python.

This is the same execution path as the Latin-hypercube driver: Vensim DSS is
called through ``vendll64``, and a scenario is applied by writing the input
workbook and reloading the model, because the switches and the delay increments
are read through ``GET XLS CONSTANTS`` and are evaluated at load time. No Vensim
window is opened and nothing is done by hand.

A scenario is declared as a list of cell writes in ``config/scenarios.csv``, so
that the definition of S0-S7 is auditable next to the results rather than
buried in code. The same file is what the Data Availability statement promises
as ``scenarios/scenarios.csv``.

Usage:
    python analysis/scenarios.py --config analysis/config/brazil.json \
        --scenarios analysis/config/scenarios.csv --out results/scenarios/brazil

    python analysis/scenarios.py --config analysis/config/chile.json \
        --scenarios analysis/config/scenarios.csv --out results/scenarios/chile

Add --dry-run to check the workbook writes without a Vensim licence: it reports,
per scenario, which cells would change and from what value to what value.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Sequence

import openpyxl

# lhs.py sits next to this file; importing it works whether the driver is run
# as analysis/scenarios.py from the repository root or from inside analysis/.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lhs import (  # noqa: E402
    Experiment,
    VensimDSS,
    append_trajectories,
    flatten_workbook,
    release_workbook_lock,
    write_rows,
)


# --------------------------------------------------------------------------- #
# Scenario definition
# --------------------------------------------------------------------------- #


def read_scenarios(path: Path, country: str) -> "OrderedDict[str, list[dict[str, Any]]]":
    """Read the scenario table, keeping the file order of the scenarios.

    Rows whose ``country`` is empty apply to both countries; a row naming a
    country overrides the shared row for the same scenario and cell, which is
    how the country-specific increments are expressed without duplicating the
    whole table.
    """
    shared: dict[tuple[str, str, str], dict[str, Any]] = {}
    specific: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: "OrderedDict[str, None]" = OrderedDict()

    with path.open(newline="", encoding="utf-8-sig") as stream:
        for line, row in enumerate(csv.DictReader(stream), start=2):
            if not row.get("scenario") or row["scenario"].lstrip().startswith("#"):
                continue
            missing = [k for k in ("sheet", "ref", "value") if not row.get(k)]
            if missing:
                raise ValueError(f"{path}:{line} is missing {', '.join(missing)}")
            try:
                value = float(row["value"])
            except ValueError as exc:
                raise ValueError(f"{path}:{line} value is not a number") from exc

            mode = (row.get("mode") or "absolute").strip().lower()
            if mode not in ("absolute", "relative", "flatten"):
                raise ValueError(
                    f"{path}:{line} mode must be absolute, relative or flatten"
                )
            entry = {
                "sheet": row["sheet"].strip(),
                "ref": row["ref"].strip().upper(),
                "value": value,
                "mode": mode,
                "skip_zero": (row.get("skip_zero") or "").strip().lower()
                in ("1", "true", "yes"),
                "note": (row.get("note") or "").strip(),
            }
            key = (row["scenario"].strip(), entry["sheet"], entry["ref"])
            order.setdefault(key[0], None)
            target = specific if (row.get("country") or "").strip() else shared
            if (row.get("country") or "").strip().lower() not in ("", country.lower()):
                continue
            target[key] = entry

    merged: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
    for scenario in order:
        writes = {k: v for k, v in shared.items() if k[0] == scenario}
        writes.update({k: v for k, v in specific.items() if k[0] == scenario})
        merged[scenario] = [writes[k] for k in sorted(writes)]
    if not merged:
        raise ValueError(f"No scenarios found in {path}")
    return merged


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _cells(sheet: Any, ref: str) -> list[list[Any]]:
    """Return the cells of a single reference or of a range, always as a grid."""
    block = sheet[ref]
    if not isinstance(block, tuple):                 # a single cell
        return [[block]]
    if block and not isinstance(block[0], tuple):    # a single row or column
        return [list(block)]
    return [list(row) for row in block]


def apply_scenario(workbook: Path, writes: Sequence[dict[str, Any]]) -> list[str]:
    """Write one scenario's cells and report what changed, old value to new.

    A write targets either one cell or a rectangular range, and does one of
    three things to every numeric cell it covers:

    ``absolute``  replace the value -- the switches and the delay increments;
    ``relative``  multiply by ``1 + value``, which shifts the level of a month-
                  or zone-varying profile while preserving its shape (the
                  hydrological conditions of B6, the demand step of V4.2);
    ``flatten``   replace each column by the mean of its own numeric cells,
                  removing the intra-annual variation of a profile while holding
                  its annual total (counterfactual CF1).

    ``skip_zero`` leaves zero cells untouched, because a zero in these workbooks
    marks a technology or a corridor that does not exist in that zone rather
    than a quantity that happens to be nil.
    """
    book = openpyxl.load_workbook(workbook)
    changes: list[str] = []
    try:
        for write in writes:
            if write["sheet"] not in book.sheetnames:
                raise KeyError(
                    f"Sheet {write['sheet']!r} is not in {workbook.name}. "
                    f"Available: {', '.join(book.sheetnames)}"
                )
            sheet = book[write["sheet"]]
            grid = _cells(sheet, write["ref"])
            mode = write.get("mode", "absolute")
            skip_zero = write.get("skip_zero", False)
            written = 0
            first_before: Any = None
            first_after: Any = None

            if mode == "flatten":
                for column in zip(*grid):
                    values = [
                        float(c.value) for c in column
                        if _is_number(c.value)
                        and not (skip_zero and c.value == 0)
                    ]
                    if not values:
                        continue
                    mean = sum(values) / len(values)
                    for cell in column:
                        if not _is_number(cell.value):
                            continue
                        if skip_zero and cell.value == 0:
                            continue
                        if first_before is None:
                            first_before, first_after = cell.value, mean
                        cell.value = mean
                        written += 1
            else:
                for row in grid:
                    for cell in row:
                        if not _is_number(cell.value):
                            continue
                        current = float(cell.value)
                        if skip_zero and current == 0.0:
                            continue
                        new_value = (
                            write["value"] if mode == "absolute"
                            else current * (1.0 + write["value"])
                        )
                        if first_before is None:
                            first_before, first_after = current, new_value
                        cell.value = new_value
                        written += 1

            if written == 0:
                raise ValueError(
                    f"{write['sheet']}!{write['ref']} matched no numeric cell; "
                    "the reference or the skip_zero flag is wrong"
                )
            shown = (
                f"{first_before!r} -> {first_after:g}" if written == 1
                else f"{written} cells, first {first_before!r} -> {first_after:g}"
            )
            changes.append(
                f"{write['sheet']}!{write['ref']} [{mode}]: {shown}"
                + (f"  ({write['note']})" if write["note"] else "")
            )
        book.save(workbook)
    finally:
        book.close()
    return changes


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #


def run_scenarios(
    experiment: Experiment,
    scenarios: "OrderedDict[str, list[dict[str, Any]]]",
    output_dir: Path,
    dry_run: bool,
) -> list[dict[str, Any]]:
    if not dry_run and experiment.model.suffix.lower() != ".vpmx":
        raise ValueError("The executable model must be a published .vpmx file")
    if not experiment.workbook.exists():
        raise FileNotFoundError(f"Input workbook not found: {experiment.workbook}")

    # SPECIAL>LOADMODEL changes the process working directory to the directory of
    # the model, so a relative output path means something different after the
    # first load -- and Vensim answers a run file it cannot create with a modal
    # save dialog rather than an error.  Resolve once, here, while the working
    # directory is still the one the driver was launched from.
    output_dir = output_dir.resolve()

    output_dir.mkdir(parents=True, exist_ok=True)
    sandbox = output_dir / "sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)
    # The scenario workbook is built here and only then copied into the sandbox;
    # see the note on apply_scenario for why it must not be written in place.
    staging = output_dir / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    workbook_name = experiment.workbook.name.replace(".flat.xlsx", ".xlsx")
    workbook_copy = sandbox / workbook_name
    pristine = staging / (workbook_name + ".orig")
    staged = staging / workbook_name
    # Reuse an already-flattened workbook when supplied.  The B5 execution
    # produced and validated these copies; flattening a million-cell workbook
    # again is unnecessary and can exhaust memory on Windows.
    if experiment.workbook.name.endswith(".flat.xlsx"):
        shutil.copy2(experiment.workbook, pristine)
        print("staging workbook copied from validated flattened input", flush=True)
    else:
        counts = flatten_workbook(experiment.workbook, pristine)
        print(
            f"staging workbook flattened: {counts['cells']} cells, "
            f"{counts['formulas']} formulas replaced by their cached value",
            flush=True,
        )

    model_copy = sandbox / experiment.model.name
    if not dry_run:
        shutil.copy2(experiment.model, model_copy)

    savelist = output_dir / "savelist.lst"
    savelist.write_text("\n".join(experiment.savelist) + "\n", encoding="utf-8")

    raw_dir = output_dir / "runs"
    raw_dir.mkdir(parents=True, exist_ok=True)

    vensim = None if dry_run else VensimDSS()
    results: list[dict[str, Any]] = []

    for index, (scenario, writes) in enumerate(scenarios.items(), start=1):
        # Every scenario starts from the shipped workbook, so a scenario never
        # inherits the previous one's cells.  The writes are applied in the
        # staging directory and the finished workbook is then byte-copied into
        # the sandbox: Vensim refuses to run against a workbook that openpyxl
        # rewrote in the directory it reads from, and blocks on a modal save
        # dialog rather than returning an error.  Excel is closed first because
        # Vensim reads the workbook through Excel automation and leaves that
        # process holding the file open.
        shutil.copy2(pristine, staged)
        changes = apply_scenario(staged, writes)
        if not dry_run:
            release_workbook_lock()
            shutil.copy2(staged, workbook_copy)
        print(f"\n[{index}/{len(scenarios)}] {scenario}")
        for change in changes:
            print(f"    {change}")
        if dry_run:
            continue

        vensim.load(model_copy)
        vensim.save_list(savelist)

        # Not raw_dir / scenario, and not a name built from it either: Vensim
        # accepts SIMULATE>RUNNAME for names such as S0 or run_01_B1_g00_i00 and
        # then refuses MENU>RUN for them, blocking on a modal save dialog rather
        # than returning an error.  The run_NNNNN form is the one the 200
        # simulations of the B5 design validated, so the run file is numbered and
        # runs/index.csv carries the mapping back to the scenario.
        run_file = raw_dir / f"run_{index:05d}"
        write_rows(raw_dir / "index.csv",
                   [{"run_id": r["run_id"], "scenario": r["scenario"]}
                    for r in results] + [{"run_id": run_file.name,
                                          "scenario": scenario}])
        vensim.run(run_file)
        vdfx = run_file.with_suffix(".vdfx")

        # The scalar is the last point of the trajectory, read from the run file.
        # vensim_get_val, which lhs.py uses, returns the missing-value sentinel
        # (-1.298e33) here, so the value is taken from the series instead: it is
        # the same quantity by definition -- the output at the end of the horizon
        # -- and it comes from the file that is archived rather than from the
        # engine's in-memory state.
        result: dict[str, Any] = {"run_id": run_file.name, "scenario": scenario}
        for output in experiment.outputs:
            _, values = vensim.get_series(vdfx, output, max_points=8192)
            result[output] = float(values[-1])
        results.append(result)
        write_rows(output_dir / "results.csv", results)

        append_trajectories(
            output_dir / "trajectories.csv",
            vensim,
            vdfx,
            scenario,
            experiment.outputs,
            write_header=index == 1,
        )
        print(f"    completed -> {run_file.with_suffix('.vdfx').name}", flush=True)

    return results


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path,
                        help="the country configuration used by lhs.py")
    parser.add_argument("--scenarios", required=True, type=Path,
                        help="CSV declaring the cell writes of each scenario")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true",
                        help="report the workbook writes without running Vensim")
    parser.add_argument("--only",
                        help="run one scenario by name (keeps peak memory bounded "
                             "on Windows and makes a batch restartable)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    experiment = Experiment.load(args.config)
    scenarios = read_scenarios(args.scenarios, experiment.country)
    if args.only:
        if args.only not in scenarios:
            raise SystemExit(
                f"{args.only} is not in {args.scenarios}. "
                f"Available: {', '.join(scenarios)}"
            )
        scenarios = OrderedDict([(args.only, scenarios[args.only])])
    print(f"{experiment.country}: {len(scenarios)} scenarios "
          f"({', '.join(scenarios)})")
    results = run_scenarios(experiment, scenarios, args.out, args.dry_run)
    if args.dry_run:
        print("\ndry run: no simulation was executed")
    else:
        print(f"\nwrote {args.out / 'results.csv'} with {len(results)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
