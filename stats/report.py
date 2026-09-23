#!/usr/bin/env python3
"""Build the Markdown stats report from a kubefix stats CSV. See README.md.

Usage: report.py data.csv > diagrams_stats.md
"""
import csv
import sys
from collections import defaultdict

ALGOS = ["algo1", "algo2", "algo3", "algo4"]


def load_rows(csv_path):
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def main_table(rows):
    by_diagram = {}
    for row in rows:
        by_diagram.setdefault(row["diagram"], {})[row["algo"]] = row

    lines = [
        "Resources touched per algo, and total resources, for each diagram.\n",
        "| Diagram | " + " | ".join(ALGOS) + " | Total resources |",
        "|---------|" + "|".join(["------------"] * len(ALGOS)) + "|------------------|",
    ]
    for diagram, algo_rows in by_diagram.items():
        total = next(iter(algo_rows.values()))["total_resources"]
        touched = [algo_rows[algo]["resources_touched"] for algo in ALGOS]
        lines.append(f"| {diagram} | " + " | ".join(touched) + f" | {total} |")
    return "\n".join(lines)


def summary_table(rows):
    pct_by_algo = defaultdict(list)
    for row in rows:
        total = int(row["total_resources"])
        touched = int(row["resources_touched"])
        pct = 100 * touched / total if total else 0
        pct_by_algo[row["algo"]].append(pct)

    lines = [
        "# Summary\n",
        "| Algo | Resources touched % mean |",
        "|------|---------------------------|",
    ]
    for algo in ALGOS:
        pcts = pct_by_algo[algo]
        mean_pct = sum(pcts) / len(pcts)
        lines.append(f"| {algo} | {mean_pct:.1f}% |")
    return "\n".join(lines)

def algo_usage_table(rows):
    by_diagram = {}
    for row in rows:
        by_diagram.setdefault(row["diagram"], {})[row["algo"]] = row

    pct_by_algo = defaultdict(list)
    for row in rows:
        used = 1 if int(row["resources_touched"]) > 0 else 0
        pct_by_algo[row["algo"]].append(used)

    for diagram, algo_rows in by_diagram.items():
        unused = 1
        for algo in ALGOS :
            if int(algo_rows[algo]["resources_touched"]) != 0 :
                unused = 0
        pct_by_algo["none"].append(unused)


    lines = [
        "| Algo | Used by % manifests |",
        "|------|---------------------------|",
    ]
    for algo in ALGOS + ["none"]:
        pcts = pct_by_algo[algo]
        mean_pct = 100 * sum(pcts) / len(pcts)
        lines.append(f"| {algo} | {mean_pct:.1f}% |")
    return "\n".join(lines)


def main(csv_path):
    rows = load_rows(csv_path)
    print("# Kubefix diagram stats\n")
    print(main_table(rows))
    print()
    print(summary_table(rows))
    print()
    print(algo_usage_table(rows))


if __name__ == "__main__":
    main(sys.argv[1])
