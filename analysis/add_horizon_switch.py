"""Add an explicit planning-horizon switch to a country model (experiment H1).

Reviewer 1 (Energy, EGY-D-26-23664) asked for the delay scenarios to be rerun
with a fixed planning horizon. In the shipped models the horizon is chosen by
two conditions:

* generation:   VMAX(Accumulated Generation Delays[ZTech!])>0 :OR:
                Generation Forecasting Switch=1      -> f7, otherwise f1
* transmission: Sum(Accumulated Transmission for Interconnection delays
                [TrasmTech!])=0 (and the [Lines] variant) -> f0, otherwise f7

Both accumulated delays include the reference lead times, so in the input
workbooks the first condition is always true and the second always false: every
reported run already uses the seven-year horizon. This script makes the choice
explicit and lets it be changed, without altering the reference behaviour:

    Planning Horizon Mode = 0   reference rule, unchanged (expected: f7)
                          = 1   long horizon forced  (generation f7, transmission f7)
                          = 2   short horizon forced (generation f1, transmission f0)

The mode is read from 'General Parameters'!B31, so the scenario driver can set
it like any other cell. Modes 0 and 1 must give identical results; that equality
is the check that the reference runs use f7.

Usage (writes a new file next to the original; the original is not touched):
    python analysis/add_horizon_switch.py modelo/chile/ModeloCL.mdl  modelo/chile/ModeloCL_H.mdl
    python analysis/add_horizon_switch.py modelo/brasil/ModeloBR.mdl modelo/brasil/ModeloBR_H.mdl
Then open each *_H.mdl in Vensim DSS and publish it as *_H.vpmx.
"""

from __future__ import annotations

import sys
from pathlib import Path

GEN_OLD = "VMAX(Accumulated Generation Delays[ZTech!])>0:OR:Generation Forecasting Switch=1"
GEN_NEW = "Use Long Generation Horizon=1"

TRANS_ALL_OLD = "Sum(Accumulated Transmission for Interconnection delays[TrasmTech!])=0"
TRANS_ALL_NEW = "Use Short Transmission Horizon=1"

TRANS_LINES_OLD = "Accumulated Transmission for Interconnection delays[Lines]=0 "
TRANS_LINES_NEW = "Use Short Transmission Horizon Lines=1 "

NEW_EQUATIONS = r"""
Planning Horizon Mode=
	GET XLS CONSTANTS('?Datos', 'General Parameters', 'B31')
	~	Dmnl
	~	0: reference rule (unchanged); 1: long horizon forced (f7); 2: short \
		horizon forced (generation f1, transmission f0). Added for the fixed-horizon \
		experiment requested in review (EGY-D-26-23664, R1.4).
	|

Use Long Generation Horizon=
	IF THEN ELSE(Planning Horizon Mode=0,
	  IF THEN ELSE(VMAX(Accumulated Generation Delays[ZTech!])>0:OR:Generation Forecasting Switch=1, 1, 0),
	  IF THEN ELSE(Planning Horizon Mode=1, 1, 0))
	~	Dmnl
	~	1 = generation investment uses the seven-year forecast (f7); 0 = one-year (f1).
	|

Use Short Transmission Horizon=
	IF THEN ELSE(Planning Horizon Mode=0,
	  IF THEN ELSE(Sum(Accumulated Transmission for Interconnection delays[TrasmTech!])=0, 1, 0),
	  IF THEN ELSE(Planning Horizon Mode=2, 1, 0))
	~	Dmnl
	~	1 = transmission investment uses the current year (f0); 0 = seven-year forecast (f7).
	|

Use Short Transmission Horizon Lines=
	IF THEN ELSE(Planning Horizon Mode=0,
	  IF THEN ELSE(Accumulated Transmission for Interconnection delays[Lines]=0, 1, 0),
	  IF THEN ELSE(Planning Horizon Mode=2, 1, 0))
	~	Dmnl
	~	As above, for the corridor reinforcement rule that tests line delays only.
	|
"""

SKETCH_MARK = "\\\\\\---/// Sketch information"


def patch(text: str) -> str:
    counts = {
        "generation": text.count(GEN_OLD),
        "transmission": text.count(TRANS_ALL_OLD),
        "transmission[Lines]": text.count(TRANS_LINES_OLD),
    }
    expected = {"generation": 2, "transmission": 4, "transmission[Lines]": 1}
    if counts != expected:
        raise SystemExit(f"unexpected model text, found {counts}, expected {expected}")
    if "Planning Horizon Mode" in text:
        raise SystemExit("model already contains Planning Horizon Mode")
    if SKETCH_MARK not in text:
        raise SystemExit("sketch marker not found")

    # The new equations reuse the original conditions verbatim, so they are
    # inserted after the replacements to keep those conditions intact.
    text = text.replace(GEN_OLD, GEN_NEW)
    text = text.replace(TRANS_ALL_OLD, TRANS_ALL_NEW)
    text = text.replace(TRANS_LINES_OLD, TRANS_LINES_NEW)
    head, tail = text.split(SKETCH_MARK, 1)
    return head.rstrip("\n") + "\n" + NEW_EQUATIONS + "\n" + SKETCH_MARK + tail


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    source, target = Path(argv[1]), Path(argv[2])
    if target.exists():
        raise SystemExit(f"{target} exists; refusing to overwrite")
    raw = source.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    target.write_bytes(patch(text).replace("\n", newline).encode("utf-8"))
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
