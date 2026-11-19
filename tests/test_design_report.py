import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from analysis.design_report import unit_design


def write_design(directory: Path, rows, factors) -> None:
    (directory / "metadata.json").write_text(json.dumps({"factors": factors}), encoding="utf-8")
    with (directory / "samples.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class UnitDesignTest(unittest.TestCase):
    def test_linear_factor_maps_onto_the_unit_interval(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            write_design(
                directory,
                [{"run_id": "run_00001", "a": 100.0}, {"run_id": "run_00002", "a": 400.0}],
                [{"id": "a", "lower": 100.0, "upper": 400.0, "log": False}],
            )
            unit, names = unit_design(directory)
        self.assertEqual(names, ["a"])
        np.testing.assert_allclose(unit[:, 0], [0.0, 1.0])

    def test_log_factor_is_mapped_through_log10(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            write_design(
                directory,
                [{"run_id": "run_00001", "theta": 1e8}],
                [{"id": "theta", "lower": 1e7, "upper": 1e9, "log": True}],
            )
            unit, _ = unit_design(directory)
        # 1e8 is the geometric centre of [1e7, 1e9] and must land at 0.5.
        self.assertAlmostEqual(unit[0, 0], 0.5)

    def test_run_id_is_not_treated_as_a_factor(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            write_design(
                directory,
                [{"run_id": "run_00001", "a": 0.5}],
                [{"id": "a", "lower": 0.0, "upper": 1.0, "log": False}],
            )
            _, names = unit_design(directory)
        self.assertNotIn("run_id", names)


class ShippedDesignTest(unittest.TestCase):
    """The properties quoted in Appendix C.6 of the article."""

    def test_both_designs_are_proper_latin_hypercubes(self):
        for country in ("brazil", "chile"):
            with self.subTest(country=country):
                unit, names = unit_design(Path(__file__).parent.parent / "analysis" / "designs" / country)
                samples = unit.shape[0]
                self.assertEqual((samples, len(names)), (500, 12))
                strata = np.minimum((unit * samples).astype(int), samples - 1)
                for index, name in enumerate(names):
                    self.assertEqual(len(set(strata[:, index])), samples, f"{name} is not stratified")

    def test_the_two_countries_share_one_unit_hypercube(self):
        """Common random numbers: sample k is the same quantile in both countries.

        Eleven factors have identical ranges and therefore identical values;
        L_g is sampled around a country-specific reference, so its values
        differ while its position in the design does not.
        """
        designs = Path(__file__).parent.parent / "analysis" / "designs"
        brazil, names = unit_design(designs / "brazil")
        chile, other = unit_design(designs / "chile")
        self.assertEqual(names, other)
        np.testing.assert_allclose(brazil, chile, atol=1e-12)

    def test_only_the_lifetime_column_differs_between_countries(self):
        designs = Path(__file__).parent.parent / "analysis" / "designs"
        rows = {}
        for country in ("brazil", "chile"):
            with (designs / country / "samples.csv").open(encoding="utf-8", newline="") as handle:
                rows[country] = list(csv.DictReader(handle))
        differing = {
            name
            for name in rows["brazil"][0]
            if [row[name] for row in rows["brazil"]] != [row[name] for row in rows["chile"]]
        }
        self.assertEqual(differing, {"lifetime"})

    def test_factors_are_close_to_uncorrelated(self):
        unit, _ = unit_design(Path(__file__).parent.parent / "analysis" / "designs" / "chile")
        correlation = np.corrcoef(unit, rowvar=False) - np.eye(unit.shape[1])
        self.assertLess(np.abs(correlation).max(), 0.15)


if __name__ == "__main__":
    unittest.main()
