"""Experiments B6 (hydrology) and V4 (extreme condition): tables from the runs.

B6 fills Table 8 of Section 5.7 -- what the response to expansion delay does
under a wet, a median and a dry inflow profile -- as differences rather than
levels, because the question is whether the hydro advantage the paper attributes
to Brazil survives a dry year.

V4 fills the "Obtained" column of Table S5 in Supplementary Appendix C.4.  It
does not write that column: an extreme-condition test is judged on the sign and
the shape of the response, and turning a trajectory into a sentence is not
something to automate.  What it produces is the evidence to write from -- for
each test and country, the indicator against its S0 value, plus the monotonicity
and oscillation of the capacity margin, which is what test V4.5 turns on.

Usage:  python analyse_b6_v4.py [--results C:/b5/vensimpypsa/results]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def _trajectories(directory):
    """Shipped as trajectories.csv.gz in the replication package; pandas reads both."""
    from pathlib import Path as _P
    p = _P(directory) / "trajectories.csv"
    return p if p.exists() else p.with_suffix(".csv.gz")

HERE = Path(__file__).resolve().parent

CAPACITY = "Total Generation Capacity"
TRANSMISSION = "Total Transmission"
PRICE = "Aggregated Generation Tariff[f0]"
MARGIN = "Capacity Margin[f0]"
CONGESTION = "Congestion Tariff[f0]"
COST = "Total System Cost"


def load(directory: Path) -> pd.DataFrame:
    path = _trajectories(directory)
    if not path.exists():
        raise SystemExit(f"missing {path}")
    frame = pd.read_csv(path)
    for column in ("time", "value"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.dropna(subset=["time", "value"])


def series(frame: pd.DataFrame, run: str, variable: str) -> pd.Series:
    block = frame[(frame["run_id"] == run) & (frame["variable"] == variable)]
    return block.sort_values("time")["value"]


def summary(frame: pd.DataFrame, run: str) -> dict[str, float]:
    cap = series(frame, run, CAPACITY)
    trans = series(frame, run, TRANSMISSION)
    price = series(frame, run, PRICE)
    margin = series(frame, run, MARGIN)
    congestion = series(frame, run, CONGESTION)
    cost = series(frame, run, COST)
    if cap.empty:
        return {}
    return {
        "capacity_GW": float(cap.iloc[-1]),
        "transmission_GW": float(trans.iloc[-1]) / 1000 if not trans.empty else np.nan,
        "price_mean": float(price.mean()) if not price.empty else np.nan,
        "price_p95": float(price.quantile(0.95)) if not price.empty else np.nan,
        "margin_min": float(margin.min()) if not margin.empty else np.nan,
        "margin_final": float(margin.iloc[-1]) if not margin.empty else np.nan,
        "congestion_mean": float(congestion.mean()) if not congestion.empty else np.nan,
        "cost_final": float(cost.iloc[-1]) if not cost.empty else np.nan,
    }


def shape(frame: pd.DataFrame, run: str, variable: str) -> dict[str, float]:
    """Monotonicity and turning points -- what V4.5 is actually asking about."""
    values = series(frame, run, variable).to_numpy(float)
    if values.size < 3:
        return {}
    diff = np.diff(values)
    sign = np.sign(diff)
    sign = sign[sign != 0]
    turns = int(np.count_nonzero(np.diff(sign))) if sign.size > 1 else 0
    return {
        "start": float(values[0]),
        "end": float(values[-1]),
        "min": float(values.min()),
        "max": float(values.max()),
        "share_falling": float(np.mean(diff < 0)),
        "direction_changes": turns,
    }


def do_b6(results: Path) -> None:
    print("\n=========== B6 -- hydrological conditions ===========")
    lines = []
    for country, folder in (("Brazil", "B6_hydrology/brazil"), ("Chile", "B6_hydrology/chile")):
        directory = results / folder
        if not (_trajectories(directory)).exists():
            print(f"{country}: not run yet")
            continue
        frame = load(directory)
        for tag, label in (("wet", "Wet"), ("med", "Median"), ("dry", "Dry")):
            s0 = summary(frame, f"B6_S0_{tag}")
            s3 = summary(frame, f"B6_S3_{tag}")
            s6 = summary(frame, f"B6_S6_{tag}")
            if not (s0 and s3 and s6):
                print(f"{country} {label}: incomplete")
                continue
            # Percentages, not levels: the sampled tariff and margin are the
            # model's own aggregates and not the zonal mean price and derated
            # margin of Table 6, so a level would invite the two to be read as
            # the same quantity.  A percentage of the country's own nominal case
            # also makes the two countries comparable.
            def pc(before: float, after: float) -> float:
                return 100.0 * (after / before - 1.0)

            d_cap = pc(s0["capacity_GW"], s3["capacity_GW"])
            d_price = pc(s0["price_mean"], s3["price_mean"])
            d_margin = pc(s0["margin_min"], s3["margin_min"])
            d_flex = pc(s3["price_mean"], s6["price_mean"])
            print(f"{country:7s} {label:7s}  nominal cap {s0['capacity_GW']:8.2f} GW  "
                  f"| S3-S0: cap {d_cap:+6.2f}%  price {d_price:+6.2f}%  "
                  f"margin {d_margin:+6.2f}%  | S6-S3 price {d_flex:+6.2f}%")
            lines.append(f"\\new{{{country}}} & \\new{{{label}}} & "
                         f"\\new{{{s0['capacity_GW']:.1f}}} & "
                         f"\\new{{{d_cap:+.2f}}} & \\new{{{d_price:+.2f}}} & "
                         f"\\new{{{d_margin:+.2f}}} & \\new{{{d_flex:+.2f}}}"
                         + chr(92) * 2)
    if lines:
        out = HERE / "generated" / "b6_table.tex"
        out.parent.mkdir(exist_ok=True)
        out.write_text("% Generated by analyse_b6_v4.py -- do not edit by hand.\n"
                       + "\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nwrote {out}")


def do_v4(results: Path) -> None:
    print("\n=========== V4 -- extreme-condition tests ===========")
    tests = ["V4_1_no_renewables", "V4_2_double_demand", "V4_3_no_interconnection",
             "V4_4_no_delay", "V4_5_delay_120", "V4_6_no_bess_duration"]
    for country, folder in (("Brazil", "V4_extreme_conditions/brazil"), ("Chile", "V4_extreme_conditions/chile")):
        directory = results / folder
        if not (_trajectories(directory)).exists():
            print(f"{country}: not run yet")
            continue
        frame = load(directory)
        base = summary(frame, "V4_0_baseline") or {}
        print(f"\n--- {country} ---")
        header = ("test", "capGW", "transGW", "price", "marginMin", "marginEnd",
                  "congest", "falling", "turns")
        print("  " + "".join(f"{h:>13s}" for h in header))
        for test in tests:
            s = summary(frame, test)
            if not s:
                print(f"  {test:>13s}   (missing)")
                continue
            sh = shape(frame, test, MARGIN)
            print("  " + f"{test.replace('V4_', '')[:12]:>13s}"
                  + f"{s['capacity_GW']:>13.2f}"
                  + f"{s['transmission_GW']:>13.2f}"
                  + f"{s['price_mean']:>13.2f}"
                  + f"{s['margin_min']:>13.3f}"
                  + f"{s['margin_final']:>13.3f}"
                  + f"{s['congestion_mean']:>13.3f}"
                  + f"{sh.get('share_falling', float('nan')):>13.2f}"
                  + f"{sh.get('direction_changes', -1):>13d}")
        if base:
            print("  (compare against the S0 run of results/b1_* or the archived S0)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path,
                        default=Path(__file__).resolve().parents[1] / "results")
    args = parser.parse_args()
    do_b6(args.results)
    do_v4(args.results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
