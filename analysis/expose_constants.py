"""Expose the two hardcoded decision parameters as named Vensim constants.

Table B.3 of the manuscript lists the profitability threshold and the logit
scale among the parameters varied in the sensitivity analysis, but the
submitted model writes both as numeric literals inside equations:

    Profitable Technologies[ZTech] =
        IF THEN ELSE( Profitability Indicator[ZTech] < 1.2, 0, ... )

    Selected Profitable Technologies[ZTech] =
        ... EXP( Profitable Power Technologies[ZTech] / 1e+08 ) ...

A literal cannot be reached by ``SIMULATE>SETVAL``, so neither parameter can be
sampled. This script replaces the literals with two new constants whose default
values are exactly the literals they replace, which leaves the behaviour of
every published scenario unchanged while making both parameters addressable.

The transformation is text-level, idempotent and reversible: it refuses to run
unless it finds the expected number of occurrences, and refuses to run twice.

After patching, open the model in Vensim DSS, confirm it compiles and that
*Units Check* still passes, then republish the ``.vpmx``.

    python -m analysis.expose_constants modelo/chile/ModeloCL.mdl
    python -m analysis.expose_constants modelo/brasil/ModeloBR.mdl --check
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Sequence

THRESHOLD_NAME = "Profitability Threshold"
THRESHOLD_LITERAL = "Profitability Indicator[ZTech]<1.2"
THRESHOLD_PATCHED = f"Profitability Indicator[ZTech]<{THRESHOLD_NAME}"
THRESHOLD_COUNT = 1

SCALE_NAME = "Logit Scale"
SCALE_LITERAL = "/1e+08"
SCALE_PATCHED = f"/{SCALE_NAME}"
SCALE_COUNT = 8

CONTROL_MARKER = "********************************************************\n\t.Control"

NEW_EQUATIONS = f"""{THRESHOLD_NAME}=
\t1.2
\t~\tDmnl
\t~\tMinimum ratio of net present value to discounted capital cost for a
\t\ttechnology to be considered profitable. Exposed as a constant for the
\t\tsensitivity analysis; the default is the value hardcoded in the
\t\tsubmitted model.
\t|

{SCALE_NAME}=
\t1e+08
\t~\tUSD
\t~\tScale of the logit that allocates investment across technologies.
\t\tExposed as a constant for the sensitivity analysis; the default is the
\t\tvalue hardcoded in the submitted model.
\t|

"""


def patch(text: str) -> str:
    threshold_found = text.count(THRESHOLD_LITERAL)
    scale_found = text.count(SCALE_LITERAL)
    if threshold_found != THRESHOLD_COUNT:
        raise ValueError(
            f"expected {THRESHOLD_COUNT} occurrence of {THRESHOLD_LITERAL!r}, "
            f"found {threshold_found}"
        )
    if scale_found != SCALE_COUNT:
        raise ValueError(
            f"expected {SCALE_COUNT} occurrences of {SCALE_LITERAL!r}, "
            f"found {scale_found}"
        )
    if CONTROL_MARKER not in text:
        raise ValueError("could not find the .Control section to insert before")
    text = text.replace(THRESHOLD_LITERAL, THRESHOLD_PATCHED)
    text = text.replace(SCALE_LITERAL, SCALE_PATCHED)
    return text.replace(CONTROL_MARKER, NEW_EQUATIONS + CONTROL_MARKER, 1)


def already_patched(text: str) -> bool:
    return f"{THRESHOLD_NAME}=" in text and f"{SCALE_NAME}=" in text


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path, help="the .mdl source to patch")
    parser.add_argument(
        "--check",
        action="store_true",
        help="report what would change without writing anything",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="write here instead of in place (the original is otherwise backed "
        "up next to it as .mdl.orig)",
    )
    args = parser.parse_args(argv)

    try:
        if args.model.suffix.lower() != ".mdl":
            raise ValueError("expected a Vensim .mdl source file")
        text = args.model.read_text(encoding="utf-8", errors="strict")
        if already_patched(text):
            print(f"{args.model.name}: already patched, nothing to do")
            return 0
        patched = patch(text)
        print(
            f"{args.model.name}: {THRESHOLD_COUNT} threshold literal and "
            f"{SCALE_COUNT} logit-scale literals replaced; "
            f"2 constants added before the .Control section"
        )
        if args.check:
            print("--check given, nothing written")
            return 0
        destination = args.output or args.model
        if destination == args.model:
            backup = args.model.with_suffix(".mdl.orig")
            if not backup.exists():
                shutil.copy2(args.model, backup)
                print(f"original backed up as {backup.name}")
        destination.write_text(patched, encoding="utf-8")
        print(f"written to {destination}")
        print(
            "Next: open the model in Vensim DSS, check that it compiles and "
            "that Units Check passes, then republish the .vpmx."
        )
        return 0
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
