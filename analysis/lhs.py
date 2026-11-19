"""Generate and execute the Latin Hypercube uncertainty design (experiment B5).

The sample design is platform independent and is written to disk before any
simulation starts, so the experiment is fully specified and reproducible even
on machines that cannot run the model.

Execution deliberately uses the Vensim DSS DLL. Most of the uncertain factors
are read by the model through ``GET XLS CONSTANTS`` / ``GET XLS DATA``, which
are evaluated when the model is loaded, so a sample is applied by writing the
input workbook and reloading the model rather than by ``SIMULATE>SETVAL``.
Only factors that the model exposes as plain constants are set through SETVAL.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import ctypes.util
import json
import math
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

import numpy as np
import openpyxl
from openpyxl.utils import range_boundaries
from scipy.stats import qmc

MODES = {"absolute", "relative", "growth", "categorical"}


# --------------------------------------------------------------------------- #
# Experiment definition
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Target:
    """A location in the input workbook that one factor writes to."""

    sheet: str
    ref: str
    columns_matching: tuple[str, ...] = ()
    header_row: int | None = None
    skip_zero: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Target":
        if "sheet" not in value or "ref" not in value:
            raise ValueError("Every target needs a 'sheet' and a 'ref'")
        matching = tuple(str(item) for item in value.get("columns_matching", ()))
        header_row = value.get("header_row")
        if matching and header_row is None:
            raise ValueError(
                f"{value['sheet']}!{value['ref']}: 'columns_matching' also "
                "requires 'header_row'"
            )
        return cls(
            sheet=str(value["sheet"]),
            ref=str(value["ref"]),
            columns_matching=matching,
            header_row=int(header_row) if header_row is not None else None,
            skip_zero=bool(value.get("skip_zero", False)),
        )

    def bounds(self, sheet: Any) -> tuple[range, list[int]]:
        """Return the rows and the selected columns this target covers."""
        min_col, min_row, max_col, max_row = range_boundaries(self.ref)
        if None in (min_col, min_row, max_col, max_row):
            raise ValueError(f"{self.sheet}!{self.ref}: not a bounded range")
        return range(min_row, max_row + 1), self._selected_columns(sheet, min_col, max_col)

    def cells(self, sheet: Any) -> Iterator[tuple[int, int]]:
        """Yield the (row, column) pairs this target covers."""
        rows, columns = self.bounds(sheet)
        for row in rows:
            for column in columns:
                yield row, column

    def _selected_columns(self, sheet: Any, min_col: int, max_col: int) -> list[int]:
        columns = list(range(min_col, max_col + 1))
        if not self.columns_matching:
            return columns
        keep = []
        for column in columns:
            header = sheet.cell(row=self.header_row, column=column).value
            text = str(header) if header is not None else ""
            if any(token.lower() in text.lower() for token in self.columns_matching):
                keep.append(column)
        if not keep:
            raise ValueError(
                f"{self.sheet}!{self.ref}: no column header in row "
                f"{self.header_row} matches {list(self.columns_matching)}"
            )
        return keep


@dataclass(frozen=True)
class Factor:
    """One uncertain input of the experiment."""

    id: str
    label: str
    mode: str
    targets: tuple[Target, ...] = ()
    lower: float = 0.0
    upper: float = 0.0
    levels: tuple[str, ...] = ()
    integer: bool = False
    log: bool = False
    constant: str | None = None
    symbol: str = ""
    note: str = ""
    requires_patch: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Factor":
        identifier = str(value.get("id", "")).strip()
        if not identifier:
            raise ValueError("Every factor needs a non-empty 'id'")
        mode = str(value.get("mode", "absolute"))
        if mode not in MODES:
            raise ValueError(f"{identifier}: mode must be one of {sorted(MODES)}")

        levels = tuple(str(item) for item in value.get("levels", ()))
        lower = float(value.get("lower", 0.0))
        upper = float(value.get("upper", 0.0))
        if mode == "categorical":
            if len(levels) < 2:
                raise ValueError(f"{identifier}: a categorical factor needs 2+ levels")
        else:
            if not math.isfinite(lower) or not math.isfinite(upper):
                raise ValueError(f"{identifier}: bounds must be finite")
            if lower >= upper:
                raise ValueError(f"{identifier}: 'lower' must be below 'upper'")
            if value.get("log") and lower <= 0:
                raise ValueError(
                    f"{identifier}: log sampling needs a strictly positive lower bound"
                )

        constant = value.get("constant")
        targets = tuple(Target.from_dict(item) for item in value.get("targets", ()))
        if mode != "categorical" and not targets and not constant:
            raise ValueError(
                f"{identifier}: needs either workbook 'targets' or a Vensim 'constant'"
            )
        if mode == "growth" and not targets:
            raise ValueError(f"{identifier}: growth mode needs a workbook target")
        if mode == "relative" and constant and not targets:
            raise ValueError(
                f"{identifier}: relative mode needs a workbook target to read the "
                "reference value from"
            )
        return cls(
            id=identifier,
            label=str(value.get("label", identifier)),
            mode=mode,
            targets=targets,
            lower=lower,
            upper=upper,
            levels=levels,
            integer=bool(value.get("integer", False)),
            log=bool(value.get("log", False)),
            constant=str(constant) if constant else None,
            symbol=str(value.get("symbol", "")),
            note=str(value.get("note", "")),
            requires_patch=bool(value.get("requires_patch", False)),
        )

    def scale(self, unit: float) -> float | str:
        """Map one coordinate of the unit hypercube onto this factor."""
        if self.mode == "categorical":
            index = min(int(unit * len(self.levels)), len(self.levels) - 1)
            return self.levels[index]
        if self.log:
            # A scale parameter spanning orders of magnitude is sampled
            # log-uniformly; a uniform draw would put 90 % of the samples in
            # the top decade.
            exponent = math.log10(self.lower) + unit * (
                math.log10(self.upper) - math.log10(self.lower)
            )
            value = 10.0**exponent
        else:
            value = self.lower + unit * (self.upper - self.lower)
        if self.integer:
            return int(np.clip(round(value), self.lower, self.upper))
        return float(value)


@dataclass
class Experiment:
    country: str
    model: Path
    workbook: Path
    factors: list[Factor]
    outputs: list[str]
    savelist: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Experiment":
        with path.open(encoding="utf-8") as stream:
            config = json.load(stream)
        required = {"country", "model", "workbook", "factors", "outputs"}
        missing = required.difference(config)
        if missing:
            raise ValueError(f"Missing configuration keys: {', '.join(sorted(missing))}")
        factors = [Factor.from_dict(item) for item in config["factors"]]
        if not factors:
            raise ValueError("At least one uncertain factor is required")
        identifiers = [factor.id for factor in factors]
        duplicates = {name for name in identifiers if identifiers.count(name) > 1}
        if duplicates:
            raise ValueError(f"Duplicate factor ids: {', '.join(sorted(duplicates))}")
        if not config["outputs"]:
            raise ValueError("At least one output variable is required")
        base = path.parent
        return cls(
            country=str(config["country"]),
            model=(base / config["model"]).resolve(),
            workbook=(base / config["workbook"]).resolve(),
            factors=factors,
            outputs=[str(item) for item in config["outputs"]],
            savelist=[str(item) for item in config.get("savelist", config["outputs"])],
        )


# --------------------------------------------------------------------------- #
# Sample design
# --------------------------------------------------------------------------- #


def latin_hypercube(
    factors: Sequence[Factor], samples: int, seed: int
) -> list[dict[str, float | int | str]]:
    """Return a reproducible, non-optimised Latin Hypercube design."""
    if samples < 1:
        raise ValueError("samples must be at least 1")
    if not factors:
        raise ValueError("factors cannot be empty")
    unit = qmc.LatinHypercube(d=len(factors), seed=seed).random(samples)
    design: list[dict[str, float | int | str]] = []
    for row in unit:
        design.append(
            {
                factor.id: factor.scale(coordinate)
                for factor, coordinate in zip(factors, row, strict=True)
            }
        )
    return design


def write_rows(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("Cannot write an empty table")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


# --------------------------------------------------------------------------- #
# Applying a sample to the input workbook
# --------------------------------------------------------------------------- #


def reference_values(workbook: Path, factors: Sequence[Factor]) -> dict[str, list[float]]:
    """Read the shipped value of every workbook-backed factor."""
    book = openpyxl.load_workbook(workbook, data_only=True)
    reference: dict[str, list[float]] = {}
    for factor in factors:
        values: list[float] = []
        for target in factor.targets:
            if target.sheet not in book.sheetnames:
                raise KeyError(f"{workbook.name}: no sheet named {target.sheet!r}")
            sheet = book[target.sheet]
            for row, column in target.cells(sheet):
                cell = sheet.cell(row=row, column=column).value
                if not isinstance(cell, (int, float)) or isinstance(cell, bool):
                    continue
                if target.skip_zero and float(cell) == 0.0:
                    continue
                values.append(float(cell))
        reference[factor.id] = values
    book.close()
    return reference


def flatten_workbook(source: Path, destination: Path) -> dict[str, int]:
    """Write a values-only copy of the input workbook.

    The shipped workbooks are about a quarter formulas: the CAPEX trajectory,
    the hourly demand block and part of the inflow series are all computed from
    more compact source blocks. Vensim reads the cached value of a formula
    cell, and openpyxl drops that cache when it saves, so a workbook that still
    contains formulas after a round trip would be read by Vensim as blank.

    Flattening once, up front, avoids that: every cell becomes the number Excel
    last computed, the driver then overwrites the cells a sample touches, and
    Vensim reads plain numbers throughout. No formula in either workbook refers
    to a cell that the design varies, so nothing downstream is frozen at a
    stale value.
    """
    formulas = openpyxl.load_workbook(source)
    values = openpyxl.load_workbook(source, data_only=True)
    counts = {"cells": 0, "formulas": 0, "uncached": 0}
    for name in formulas.sheetnames:
        source_sheet, value_sheet = formulas[name], values[name]
        for row in source_sheet.iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                counts["cells"] += 1
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    counts["formulas"] += 1
                    if value_sheet.cell(row=cell.row, column=cell.column).value is None:
                        counts["uncached"] += 1
    formulas.close()
    destination.parent.mkdir(parents=True, exist_ok=True)
    values.save(destination)
    values.close()
    if counts["uncached"]:
        raise ValueError(
            f"{source.name}: {counts['uncached']} formula cells have no cached "
            "value. Open the workbook in Excel, force a full recalculation and "
            "save it before running the design."
        )
    return counts


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def apply_sample(
    workbook: Path,
    factors: Sequence[Factor],
    sample: dict[str, float | int | str],
) -> int:
    """Write one sample into a copy of the input workbook, in place.

    Only numeric cells are written, so labels and blanks inside a target range
    are left alone. The three numeric modes differ in what they do with the
    value already in the cell:

    ``absolute``  replace it with the sampled value;
    ``relative``  multiply it by ``1 + x``, which keeps a technology- or
                  month-varying profile intact while shifting its level;
    ``growth``    keep the first row of each column as the anchor and scale the
                  deviation from it by ``1 + x``, which changes the growth of a
                  time series without moving its starting point.

    A target marked ``skip_zero`` leaves zero cells untouched. The workbooks use
    a zero to mark a technology that cannot be built in that zone, and writing a
    live value there would silently enable it.

    Returns the number of cells written.
    """
    book = openpyxl.load_workbook(workbook)
    written = 0
    for factor in factors:
        if factor.mode == "categorical" or not factor.targets:
            continue
        value = sample[factor.id]
        if not _is_number(value):
            raise TypeError(f"{factor.id}: expected a numeric sample, got {value!r}")
        value = float(value)
        for target in factor.targets:
            if target.sheet not in book.sheetnames:
                raise KeyError(f"{workbook.name}: no sheet named {target.sheet!r}")
            sheet = book[target.sheet]
            rows, columns = target.bounds(sheet)
            for column in columns:
                anchor: float | None = None
                for row in rows:
                    cell = sheet.cell(row=row, column=column)
                    current = cell.value
                    if not _is_number(current):
                        continue
                    current = float(current)
                    if target.skip_zero and current == 0.0:
                        continue
                    if factor.mode == "absolute":
                        cell.value = value
                    elif factor.mode == "relative":
                        cell.value = current * (1.0 + value)
                    else:  # growth
                        if anchor is None:
                            anchor = current
                            continue
                        cell.value = anchor + (current - anchor) * (1.0 + value)
                    written += 1
    book.save(workbook)
    book.close()
    return written


# --------------------------------------------------------------------------- #
# Vensim DSS execution
# --------------------------------------------------------------------------- #


class VensimDSS:
    """Small, fail-fast wrapper around the 64-bit Vensim DSS DLL."""

    def __init__(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError(
                "Vensim execution requires Windows and a licensed 64-bit "
                "Vensim DSS installation. Use --sample-only on this platform."
            )
        dll_path = ctypes.util.find_library("vendll64")
        if not dll_path:
            raise FileNotFoundError(
                "vendll64 was not found. Install Vensim DSS and ensure its DLL "
                "directory is available on PATH."
            )
        self.dll = ctypes.WinDLL(dll_path)
        self.dll.vensim_command.argtypes = [ctypes.c_char_p]
        self.dll.vensim_command.restype = ctypes.c_int
        self.dll.vensim_get_val.argtypes = [
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_float),
        ]
        self.dll.vensim_get_val.restype = ctypes.c_int
        self.dll.vensim_get_data.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
        ]
        self.dll.vensim_get_data.restype = ctypes.c_int
        self.dll.vensim_be_quiet(2)

    def command(self, value: str) -> None:
        if self.dll.vensim_command(value.encode("utf-8")) == 0:
            raise RuntimeError(f"Vensim rejected command: {value}")

    def load(self, model: Path) -> None:
        self.command(f"SPECIAL>LOADMODEL|{model.resolve()}")

    def set_value(self, variable: str, value: float | int) -> None:
        self.command(f"SIMULATE>SETVAL|{variable}={value:.15g}")

    def save_list(self, path: Path) -> None:
        """Restrict the run file to the reported variables.

        Without this the model saves every subscripted array and a single run
        file is several gigabytes, which makes a 500-sample design impossible
        to store.
        """
        self.command(f"SIMULATE>SAVELIST|{path.resolve()}")

    def get_value(self, variable: str) -> float:
        result = ctypes.c_float()
        if not self.dll.vensim_get_val(variable.encode("utf-8"), ctypes.byref(result)):
            raise KeyError(f"Vensim could not read output variable: {variable}")
        return float(result.value)

    def get_series(
        self, run_file: Path, variable: str, max_points: int = 4096
    ) -> tuple[np.ndarray, np.ndarray]:
        values = (ctypes.c_float * max_points)()
        times = (ctypes.c_float * max_points)()
        count = self.dll.vensim_get_data(
            str(run_file.resolve()).encode("utf-8"),
            variable.encode("utf-8"),
            b"Time",
            values,
            times,
            max_points,
        )
        if count <= 0:
            raise KeyError(f"Vensim returned no series for {variable} in {run_file}")
        return np.array(times[:count]), np.array(values[:count])

    def run(self, run_name: Path) -> None:
        self.command(f"SIMULATE>RUNNAME|{run_name.resolve()}")
        self.command("MENU>RUN|o")


def release_workbook_lock() -> None:
    """Close any Excel process holding the sandbox workbook.

    Vensim reads .xlsx inputs through Excel automation and leaves the process
    running once the sample finishes, still holding the workbook open. The lock
    never clears on its own -- it outlives the driver -- so the next sample
    cannot overwrite the workbook and the run dies with WinError 32. Excel is
    therefore closed before every sample; the run book already requires that no
    workbook be open while the driver runs.
    """
    if platform.system() != "Windows":
        return
    subprocess.run(
        ["taskkill", "/IM", "EXCEL.EXE", "/F"],
        capture_output=True,
        check=False,  # exit code 128 simply means no Excel was running
    )
    time.sleep(1)  # let Windows release the handle before copying over it


def prepare_sandbox(experiment: Experiment, output_dir: Path) -> tuple[Path, Path]:
    """Copy the published model and its workbook into a writable sandbox.

    The model resolves its workbook through the ``?Datos`` alias, which is a
    bare filename and is therefore looked up next to the model file. Keeping
    both in one sandbox lets the driver rewrite the workbook per sample without
    touching the distributed inputs.
    """
    sandbox = output_dir / "sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)
    model_copy = sandbox / experiment.model.name
    workbook_copy = sandbox / experiment.workbook.name
    shutil.copy2(experiment.model, model_copy)
    counts = flatten_workbook(experiment.workbook, workbook_copy)
    print(
        f"sandbox workbook flattened: {counts['cells']} cells, "
        f"{counts['formulas']} formulas replaced by their cached value",
        flush=True,
    )
    return model_copy, workbook_copy


def execute_design(
    experiment: Experiment,
    design: Sequence[dict[str, float | int | str]],
    output_dir: Path,
) -> list[dict[str, Any]]:
    if experiment.model.suffix.lower() != ".vpmx":
        raise ValueError("The executable model must be a published .vpmx file")
    if not experiment.model.exists():
        raise FileNotFoundError(
            f"Published model not found: {experiment.model}. "
            "Publish the .mdl from Vensim DSS first."
        )
    if not experiment.workbook.exists():
        raise FileNotFoundError(f"Input workbook not found: {experiment.workbook}")

    # SPECIAL>LOADMODEL changes the working directory to the model's folder, so
    # a relative output path resolves differently after the first load.
    output_dir = output_dir.resolve()

    patched = [factor.id for factor in experiment.factors if factor.requires_patch]
    if patched:
        raise RuntimeError(
            "These factors need constants that the shipped model hardcodes: "
            f"{', '.join(patched)}. Run analysis/expose_constants.py on the .mdl "
            "and republish the .vpmx, or drop them from the configuration."
        )

    categorical = [f for f in experiment.factors if f.mode == "categorical"]
    if categorical:
        raise RuntimeError(
            "Categorical factors are applied by swapping an input series and are "
            "not automated yet: " + ", ".join(f.id for f in categorical)
        )

    raw_dir = output_dir / "runs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    model_copy, workbook_copy = prepare_sandbox(experiment, output_dir)
    pristine = workbook_copy.with_suffix(workbook_copy.suffix + ".orig")
    shutil.copy2(workbook_copy, pristine)

    savelist = output_dir / "savelist.lst"
    savelist.write_text("\n".join(experiment.savelist) + "\n", encoding="utf-8")

    vensim = VensimDSS()
    results: list[dict[str, Any]] = []
    for index, sample in enumerate(design, start=1):
        # Start every sample from the shipped workbook so that relative factors
        # scale the reference value and not the previous sample's value.
        release_workbook_lock()
        shutil.copy2(pristine, workbook_copy)
        apply_sample(workbook_copy, experiment.factors, sample)

        # Reloading re-reads the workbook and resets every stock.
        vensim.load(model_copy)
        vensim.save_list(savelist)
        for factor in experiment.factors:
            if factor.constant and not factor.targets:
                vensim.set_value(factor.constant, float(sample[factor.id]))

        run_id = f"run_{index:05d}"
        run_file = raw_dir / run_id
        vensim.run(run_file)
        result: dict[str, Any] = {"run_id": run_id, **sample}
        for output in experiment.outputs:
            # The scalar must come from the finished run file. vensim_get_val
            # reads the active simulation context, which after MENU>RUN holds
            # no run and yields Vensim's :NA: sentinel without raising.
            _, values = vensim.get_series(run_file.with_suffix(".vdfx"), output)
            result[output] = float(values[-1])
        results.append(result)
        write_rows(output_dir / "results.csv", results)

        # The percentile envelopes of the reported figures need the whole
        # trajectory, not just its final value. Appending run by run keeps an
        # interrupted design usable and keeps memory flat over 500 samples.
        append_trajectories(
            output_dir / "trajectories.csv",
            vensim,
            run_file.with_suffix(".vdfx"),
            run_id,
            experiment.outputs,
            write_header=index == 1,
        )
        print(f"[{index}/{len(design)}] {run_id} completed", flush=True)
    return results


def append_trajectories(
    path: Path,
    vensim: "VensimDSS",
    run_file: Path,
    run_id: str,
    variables: Sequence[str],
    write_header: bool,
) -> None:
    """Append one run's output trajectories in the long form sensitivity.py reads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if write_header else "a"
    with path.open(mode, encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if write_header:
            writer.writerow(["run_id", "variable", "time", "value"])
        for variable in variables:
            times, values = vensim.get_series(run_file, variable)
            writer.writerows(
                (run_id, variable, f"{time:.6g}", f"{value:.8g}")
                for time, value in zip(times, values)
            )


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=500)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument(
        "--sample-only",
        action="store_true",
        help="Write the design without starting Vensim (works on any OS).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config_path = args.config.resolve()
        experiment = Experiment.load(config_path)
        design = latin_hypercube(experiment.factors, args.samples, args.seed)
        rows = [{"run_id": f"run_{i:05d}", **row} for i, row in enumerate(design, 1)]
        output_dir = args.output_dir.resolve()
        write_rows(output_dir / "samples.csv", rows)

        reference: dict[str, list[float]] = {}
        if experiment.workbook.exists():
            reference = reference_values(experiment.workbook, experiment.factors)

        metadata = {
            "country": experiment.country,
            "samples": args.samples,
            "seed": args.seed,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "config": str(config_path),
            "model": str(experiment.model),
            "workbook": str(experiment.workbook),
            "sample_only": args.sample_only,
            "factors": [
                {
                    "id": factor.id,
                    "label": factor.label,
                    "symbol": factor.symbol,
                    "mode": factor.mode,
                    "lower": factor.lower,
                    "upper": factor.upper,
                    "log": factor.log,
                    "note": factor.note,
                    "levels": list(factor.levels),
                    "requires_patch": factor.requires_patch,
                    "reference_cells": len(reference.get(factor.id, [])),
                    "reference_min": min(reference[factor.id])
                    if reference.get(factor.id)
                    else None,
                    "reference_max": max(reference[factor.id])
                    if reference.get(factor.id)
                    else None,
                }
                for factor in experiment.factors
            ],
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"Latin Hypercube design written to {output_dir / 'samples.csv'}")
        if not args.sample_only:
            execute_design(experiment, design, output_dir)
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
