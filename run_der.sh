cd "$(dirname "$0")"
mkdir -p results/der
L=results/der/batch.log
echo "start $(date)" > $L
python -u keep_awake.py --log $L --until "DER FINISHED" > results/der/keep_awake.log 2>&1 &
for c in chile brazil; do
  for s in S0_H7 S3_H7; do
    echo "run $c $s $(date)" >> $L
    python -u analysis/scenarios.py --config analysis/config/${c}_der.json --scenarios analysis/config/scenarios_horizon.csv --out results/der/$c --only $s >> results/der/$c.log 2>&1 || echo "FAIL $c $s" >> $L
  done
done
echo "DER FINISHED $(date)" >> $L
