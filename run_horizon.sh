cd "$(dirname "$0")"
mkdir -p results/horizon
L=results/horizon/batch2.log
echo "start $(date)" > $L
python -u keep_awake.py --log $L --until "BATCH2 FINISHED" > results/horizon/keep_awake.log 2>&1 &
python -u analysis/scenarios.py --config analysis/config/chile_horizon.json --scenarios analysis/config/scenarios_horizon.csv --out results/horizon/chile > results/horizon/chile.log 2>&1 &
C=$!
sleep 60
python -u analysis/scenarios.py --config analysis/config/brazil_horizon.json --scenarios analysis/config/scenarios_horizon.csv --out results/horizon/brazil > results/horizon/brazil.log 2>&1
wait $C
echo "BATCH2 FINISHED $(date)" >> $L
