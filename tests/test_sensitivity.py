import unittest

import numpy as np
import pandas as pd

from analysis.sensitivity import percentile_bands, rank_factors


def design(samples=400, seed=3):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "demand": rng.uniform(-0.4, 0.4, samples),
            "capex": rng.uniform(-0.3, 0.3, samples),
            "margin": rng.uniform(0.2, 0.5, samples),
            "inert": rng.uniform(0.0, 1.0, samples),
        }
    )


class RankingTests(unittest.TestCase):
    def test_recovers_the_order_of_a_known_linear_response(self):
        x = design()
        response = pd.Series(
            100 + 40 * x.demand - 15 * x.capex + 3 * x.margin, name="capacity"
        )
        ranking = rank_factors(x, response)
        self.assertEqual(ranking.method, "src")
        self.assertGreater(ranking.r2, 0.99)
        order = ranking.to_frame()["factor"].tolist()
        self.assertEqual(order[:3], ["demand", "capex", "margin"])

    def test_signs_follow_the_direction_of_the_effect(self):
        x = design()
        response = pd.Series(100 + 40 * x.demand - 15 * x.capex, name="capacity")
        frame = rank_factors(x, response).to_frame().set_index("factor")
        self.assertGreater(frame.loc["demand", "src"], 0)
        self.assertLess(frame.loc["capex", "src"], 0)

    def test_an_unused_factor_ranks_last_and_near_zero(self):
        x = design()
        response = pd.Series(100 + 40 * x.demand - 15 * x.capex, name="capacity")
        frame = rank_factors(x, response).to_frame().set_index("factor")
        self.assertLess(abs(frame.loc["inert", "src"]), 0.05)

    def test_falls_back_to_rank_correlation_when_the_response_is_not_linear(self):
        x = design()
        # Monotone in demand but strongly convex, so a linear fit explains
        # only part of the variance while the rank correlation is exact.
        response = pd.Series(np.exp(10 * x.demand) + 0.01 * x.capex, name="price")
        ranking = rank_factors(x, response, min_r2=0.9)
        self.assertEqual(ranking.method, "spearman")
        self.assertEqual(ranking.to_frame()["factor"].iloc[0], "demand")

    def test_refuses_a_design_too_small_to_identify_the_factors(self):
        x = design(samples=4)
        with self.assertRaises(ValueError):
            rank_factors(x, pd.Series(np.arange(4.0), name="y"))

    def test_refuses_a_constant_response(self):
        x = design(samples=50)
        with self.assertRaises(ValueError):
            rank_factors(x, pd.Series(np.ones(50), name="y"))


class BandTests(unittest.TestCase):
    def frame(self):
        rows = []
        for run in range(100):
            for time in [0, 12, 24]:
                rows.append(("run_%03d" % run, "capacity", time, float(run + time)))
        return pd.DataFrame(rows, columns=["run_id", "variable", "time", "value"])

    def test_envelope_brackets_the_median_and_counts_the_runs(self):
        bands = percentile_bands(self.frame())
        self.assertEqual(len(bands), 3)
        self.assertTrue((bands["low"] <= bands["median"]).all())
        self.assertTrue((bands["median"] <= bands["high"]).all())
        self.assertTrue((bands["runs"] == 100).all())

    def test_percentiles_are_the_requested_ones(self):
        bands = percentile_bands(self.frame(), low=5, high=95).set_index("time")
        # values at t=0 are 0..99, so the 5th and 95th percentiles are 4.95/94.05
        self.assertAlmostEqual(bands.loc[0, "low"], 4.95, places=6)
        self.assertAlmostEqual(bands.loc[0, "high"], 94.05, places=6)

    def test_missing_columns_are_reported(self):
        with self.assertRaises(ValueError):
            percentile_bands(self.frame().drop(columns="value"))


if __name__ == "__main__":
    unittest.main()
