"""Run Vensim's Units Check on both country models and save the reports.

Supplementary Appendix C.2 states that the check "was run on both country models
and passes with no exceptions" and that the report is in the repository.  Nobody
had run it.  This runs it and writes the report, so the sentence is either true
and evidenced or corrected.

The check is a static analysis of the equations -- no simulation -- so it costs
seconds, and it is run on the .mdl rather than the published .vpmx because the
published file carries no unit definitions to check.

Usage:  python analysis/units_check.py --out validation/units_check
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lhs import VensimDSS  # noqa: E402

MODELS = {
    "brazil": Path(r"C:\b5\vensimpypsa\model\brazil\ModeloBR.mdl"),
    "chile": Path(r"C:\b5\vensimpypsa\model\chile\ModeloCL.mdl"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path,
                        default=Path(r"C:\b5\vensimpypsa\validation\units_check"))
    args = parser.parse_args()
    out = args.out.resolve()          # before Vensim changes the working directory
    out.mkdir(parents=True, exist_ok=True)

    vensim = VensimDSS()
    failures = 0
    for country, model in MODELS.items():
        report = out / f"units_{country}.txt"
        print(f"\n=== {country}: {model.name}", flush=True)
        vensim.load(model)
        # MENU>UNITSREPORT writes the full report; the return code only says the
        # command was accepted, so the verdict has to be read from the file.
        code = vensim.dll.vensim_command(
            f"MENU>UNITSREPORT|{report}".encode("utf-8")
        )
        print(f"    UNITSREPORT returned {code}", flush=True)
        if not report.exists():
            print("    no report written")
            failures += 1
            continue
        text = report.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        print(f"    report: {len(lines)} lines, {report}")
        for line in lines[:40]:
            print(f"      {line}")
        if len(lines) > 40:
            print(f"      ... ({len(lines) - 40} more lines)")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
