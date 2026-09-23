#!/bin/bash
# Run kubefix over every example manifest, collect per-algo stats as CSV, then build the Markdown report from that CSV.
set -e
cd "$(dirname "$0")/.."

echo Generating stats/data.csv...
rm -f stats/data.csv
for manifest in examples/*
do
  kubefix "$manifest" -c stats/data.csv > /dev/null
done

echo Generating stats/resources_stats.md...
python3 stats/report.py stats/data.csv > stats/resources_stats.md

echo stats/resources_stats.md generated.
