#!/usr/bin/env bash
# Run every remaining experiment table, in one process, one after the other.
#
# They must not overlap: the driver closes every Excel process before each
# scenario, because Vensim reads the input workbook through Excel automation and
# leaves that process holding the file open.  Two batches at once close each
# other's Excel and both fail at MENU>RUN.  Chaining them from separate waiters
# turned out to be exactly that mistake, so the sequence lives in one script.
set -u
cd "$(dirname "$0")" || exit 1

for job in scenarios_b1:b1 scenarios_b6:b6 scenarios_v4:v4; do
    csv="${job%%:*}"
    prefix="${job##*:}"
    echo "########## $(date +%H:%M:%S) start $prefix"
    bash run_batch.sh "$csv" "$prefix"
    echo "########## $(date +%H:%M:%S) done $prefix"
done
echo "########## $(date +%H:%M:%S) ALL EXPERIMENTS FINISHED"
