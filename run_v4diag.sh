#!/usr/bin/env bash
# V4.1 diagnosis (Supplementary Appendix C.4, review R1.1): rerun the one-month
# renewable-availability shock and its S0 reference, saving the hourly-margin
# outputs. One run per folder, because --only overwrites the output folder.
set -u
cd "$(dirname "$0")" || exit 1
PY=./.venv/Scripts/python.exe
for c in chile brazil; do
  for job in V4_1_no_renewables:scenarios_v4 S0:scenarios; do
    s=${job%%:*}; csv=${job##*:}
    "$PY" -u analysis/scenarios.py --config analysis/config/${c}_v4diag.json \
      --scenarios analysis/config/$csv.csv --out results/V4_1_diagnosis/${c}_$s --only $s
  done
done
