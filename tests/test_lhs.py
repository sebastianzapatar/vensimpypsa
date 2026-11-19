import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import openpyxl
import pandas as pd

from analysis.lhs import (
    Experiment,
    Factor,
    Target,
    apply_sample,
    flatten_workbook,
    latin_hypercube,
)


def make_factor(**kwargs):
    base = {"id": "x", "mode": "absolute", "lower": 0.0, "upper": 1.0,
            "targets": [{"sheet": "S", "ref": "A1"}]}
    base.update(kwargs)
    return Factor.from_dict(base)


class FactorTests(unittest.TestCase):
    def test_rejects_inverted_bounds(self):
        with self.assertRaises(ValueError):
            make_factor(lower=1.0, upper=1.0)

    def test_rejects_unknown_mode(self):
        with self.assertRaises(ValueError):
            make_factor(mode="triangular")

    def test_growth_requires_a_workbook_target(self):
        with self.assertRaises(ValueError):
            make_factor(mode="growth", targets=[], constant="Some Constant")

    def test_log_bounds_must_be_positive(self):
        with self.assertRaises(ValueError):
            make_factor(lower=0.0, upper=1e9, log=True)

    def test_log_sampling_is_uniform_in_the_exponent(self):
        factor = make_factor(lower=1e7, upper=1e9, log=True)
        self.assertAlmostEqual(factor.scale(0.0), 1e7)
        self.assertAlmostEqual(factor.scale(1.0), 1e9)
        self.assertAlmostEqual(factor.scale(0.5), 1e8)

    def test_integer_factor_is_rounded_and_clipped(self):
        factor = make_factor(lower=0, upper=24, integer=True)
        for unit in np.linspace(0.0, 1.0, 25):
            value = factor.scale(unit)
            self.assertIsInstance(value, int)
            self.assertGreaterEqual(value, 0)
            self.assertLessEqual(value, 24)

    def test_categorical_levels_are_reachable_and_bounded(self):
        factor = Factor.from_dict(
            {"id": "hydro", "mode": "categorical", "levels": ["wet", "median", "dry"]}
        )
        self.assertEqual(factor.scale(0.0), "wet")
        self.assertEqual(factor.scale(0.5), "median")
        self.assertEqual(factor.scale(1.0), "dry")

    def test_columns_matching_requires_a_header_row(self):
        with self.assertRaises(ValueError):
            Target.from_dict({"sheet": "S", "ref": "A1:C9", "columns_matching": ["PV"]})


class LatinHypercubeTests(unittest.TestCase):
    def setUp(self):
        self.factors = [
            make_factor(id="continuous", lower=10.0, upper=20.0),
            make_factor(id="integer", lower=0, upper=24, integer=True),
        ]

    def test_design_is_reproducible_and_bounded(self):
        first = latin_hypercube(self.factors, samples=12, seed=7)
        second = latin_hypercube(self.factors, samples=12, seed=7)
        self.assertEqual(first, second)
        for row in first:
            self.assertGreaterEqual(row["continuous"], 10)
            self.assertLessEqual(row["continuous"], 20)
            self.assertIsInstance(row["integer"], int)

    def test_a_different_seed_gives_a_different_design(self):
        self.assertNotEqual(
            latin_hypercube(self.factors, samples=12, seed=7),
            latin_hypercube(self.factors, samples=12, seed=8),
        )

    def test_each_continuous_stratum_is_used_once(self):
        design = latin_hypercube(self.factors[:1], samples=20, seed=11)
        unit = [(row["continuous"] - 10) / 10 for row in design]
        strata = np.floor(np.asarray(unit) * 20).astype(int)
        self.assertEqual(sorted(strata.tolist()), list(range(20)))

    def test_rejects_invalid_sample_count(self):
        with self.assertRaises(ValueError):
            latin_hypercube(self.factors, samples=0, seed=1)


class WorkbookTests(unittest.TestCase):
    """The write path is what turns a sample into a simulation, so the three
    numeric modes and the two guards are checked against a real .xlsx."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "book.xlsx"
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.title = "Data"
        sheet["A1"] = "PV"
        sheet["B1"] = "Biomass"
        for row, (pv, biomass) in enumerate(
            [(100.0, 50.0), (110.0, 55.0), (130.0, 60.0)], start=2
        ):
            sheet.cell(row=row, column=1, value=pv)
            sheet.cell(row=row, column=2, value=biomass)
        sheet["D1"] = 0.30
        sheet["D2"] = 0.0
        sheet["D3"] = "label"
        book.save(self.path)
        book.close()

    def tearDown(self):
        self.directory.cleanup()

    def read(self):
        book = openpyxl.load_workbook(self.path, data_only=True)
        sheet = book["Data"]
        values = {
            cell: sheet[cell].value
            for cell in ["A2", "A3", "A4", "B2", "B3", "B4", "D1", "D2", "D3"]
        }
        book.close()
        return values

    def test_absolute_mode_replaces_and_skip_zero_protects_inert_cells(self):
        factor = Factor.from_dict(
            {"id": "alpha", "mode": "absolute", "lower": 0.15, "upper": 0.45,
             "targets": [{"sheet": "Data", "ref": "D1:D3", "skip_zero": True}]}
        )
        apply_sample(self.path, [factor], {"alpha": 0.42})
        values = self.read()
        self.assertAlmostEqual(values["D1"], 0.42)
        self.assertEqual(values["D2"], 0.0, "a zero marks an inert entry")
        self.assertEqual(values["D3"], "label", "text is never written")

    def test_relative_mode_preserves_the_shape_of_the_profile(self):
        factor = Factor.from_dict(
            {"id": "capex", "mode": "relative", "lower": -0.3, "upper": 0.3,
             "targets": [{"sheet": "Data", "ref": "A2:B4"}]}
        )
        apply_sample(self.path, [factor], {"capex": 0.10})
        values = self.read()
        self.assertAlmostEqual(values["A2"], 110.0)
        self.assertAlmostEqual(values["A4"], 143.0)
        self.assertAlmostEqual(values["B2"], 55.0)

    def test_columns_matching_writes_only_the_named_technologies(self):
        factor = Factor.from_dict(
            {"id": "capex", "mode": "relative", "lower": -0.3, "upper": 0.3,
             "targets": [{"sheet": "Data", "ref": "A2:B4", "header_row": 1,
                          "columns_matching": ["PV"]}]}
        )
        apply_sample(self.path, [factor], {"capex": 0.50})
        values = self.read()
        self.assertAlmostEqual(values["A2"], 150.0)
        self.assertAlmostEqual(values["B2"], 50.0, msg="Biomass must be untouched")

    def test_growth_mode_holds_the_first_row_and_scales_the_deviation(self):
        factor = Factor.from_dict(
            {"id": "demand", "mode": "growth", "lower": -0.4, "upper": 0.4,
             "targets": [{"sheet": "Data", "ref": "A2:A4"}]}
        )
        apply_sample(self.path, [factor], {"demand": 0.50})
        values = self.read()
        self.assertAlmostEqual(values["A2"], 100.0, msg="the anchor never moves")
        self.assertAlmostEqual(values["A3"], 115.0)
        self.assertAlmostEqual(values["A4"], 145.0)

    def test_unknown_sheet_is_reported(self):
        factor = Factor.from_dict(
            {"id": "x", "mode": "absolute", "lower": 0.0, "upper": 1.0,
             "targets": [{"sheet": "Missing", "ref": "A1"}]}
        )
        with self.assertRaises(KeyError):
            apply_sample(self.path, [factor], {"x": 0.5})

    def test_flatten_replaces_formulas_with_their_cached_value(self):
        book = openpyxl.load_workbook(self.path)
        book["Data"]["F1"] = "=A2*2"
        book.save(self.path)
        book.close()
        destination = Path(self.directory.name) / "flat.xlsx"
        # openpyxl writes no cache for a formula it did not evaluate, which is
        # exactly the condition the guard exists to catch.
        with self.assertRaises(ValueError):
            flatten_workbook(self.path, destination)


class ConfigTests(unittest.TestCase):
    """The shipped configurations must stay loadable and point at real cells."""

    def test_shipped_configs_load_and_declare_table_b3_factors(self):
        expected = {
            "m_bar", "sigma", "f_min", "alpha_get", "pi_star", "theta",
            "lifetime", "discount", "trans_cost", "capex_res",
            "demand_growth", "hydro_inflow",
        }
        for name in ["brazil", "chile"]:
            path = Path("analysis/config") / f"{name}.json"
            experiment = Experiment.load(path)
            self.assertEqual({f.id for f in experiment.factors}, expected, name)
            self.assertTrue(experiment.outputs)
            # The shipped configs point at the *_exposed models, where Pi* and theta
            # are already named constants, so they need no further patch.
            named = {f.id for f in experiment.factors if getattr(f, "constant", None)}
            self.assertEqual(named, {"pi_star", "theta"}, name)
            self.assertFalse(any(f.requires_patch for f in experiment.factors), name)

    def test_duplicate_factor_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            factor = {"id": "x", "mode": "absolute", "lower": 0, "upper": 1,
                      "targets": [{"sheet": "S", "ref": "A1"}]}
            path.write_text(json.dumps({
                "country": "X", "model": "m.vpmx", "workbook": "w.xlsx",
                "factors": [factor, factor], "outputs": ["y"],
            }))
            with self.assertRaises(ValueError):
                Experiment.load(path)


if __name__ == "__main__":
    unittest.main()


class AppendTrajectoriesTest(unittest.TestCase):
    """The trajectory export cannot be exercised without Vensim, so the writer
    is tested against a stub that returns the series a run would return."""

    class StubVensim:
        def __init__(self):
            self.asked = []

        def get_series(self, run_file, variable, max_points=4096):
            self.asked.append((Path(run_file).name, variable))
            return np.array([2025.0, 2026.0]), np.array([10.0, 20.0])

    def test_header_is_written_once_and_rows_are_appended(self):
        from analysis.lhs import append_trajectories

        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "trajectories.csv"
            stub = self.StubVensim()
            append_trajectories(path, stub, Path("run_00001.vdfx"), "run_00001", ["A", "B"], True)
            append_trajectories(path, stub, Path("run_00002.vdfx"), "run_00002", ["A", "B"], False)
            rows = list(csv.reader(path.open(encoding="utf-8")))

        self.assertEqual(rows[0], ["run_id", "variable", "time", "value"])
        # two runs x two variables x two time points, plus the header
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[1], ["run_00001", "A", "2025", "10"])
        self.assertEqual(rows[5][0], "run_00002")
        self.assertEqual(stub.asked[0], ("run_00001.vdfx", "A"))

    def test_columns_match_what_sensitivity_requires(self):
        from analysis.lhs import append_trajectories
        from analysis.sensitivity import percentile_bands

        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "trajectories.csv"
            append_trajectories(path, self.StubVensim(), Path("r.vdfx"), "run_00001", ["A"], True)
            frame = pd.read_csv(path)
        # percentile_bands raises if any of run_id, variable, time, value is missing
        bands = percentile_bands(frame)
        self.assertEqual(len(bands), 2)
