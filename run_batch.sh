#!/usr/bin/env bash
# Run one experiment table over both countries.
#
# One process per country, as the B5 design did: the driver accumulates
# results.csv after every scenario and appends to trajectories.csv, so an
# interrupted batch still leaves every finished scenario on disk, while running
# each scenario in its own process would truncate results.csv to a single row.
#
# Usage: run_batch.sh <csv-basename> <out-prefix>
#   run_batch.sh scenarios_b1 b1
set -u

cd "$(dirname "$0")" || exit 1
PY=./.venv/Scripts/python.exe
CSV="analysis/config/$1.csv"
PREFIX="$2"

for country in chile brazil; do
    echo "=== $(date +%H:%M:%S) start $PREFIX $country ==="
    "$PY" -u analysis/scenarios.py \
        --config "analysis/config/${country}_flat.json" \
        --scenarios "$CSV" \
        --out "results/${PREFIX}_${country}"
    echo "=== $(date +%H:%M:%S) end $PREFIX $country (status $?) ==="
done
echo "=== $(date +%H:%M:%S) batch $PREFIX finished ==="
