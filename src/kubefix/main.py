import csv
from pathlib import Path
import sys

import click
from ruamel.yaml import YAML

from kubefix.common import Warning, Stat
from kubefix.algo1 import algo1_normalize_labels
from kubefix.algo2 import algo2_label_intersection
from kubefix.algo3 import algo3_mark_isolated
from kubefix.algo4 import algo4_assign_unique_cluster_labels

yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)


def load_manifests(path):
    """Load all K8s resources from a YAML file.

    Handles multi-document files (separated by ---) and skips empty
    documents.

    Args:
        path: Path to the YAML file.

    Returns:
        A list of resources (dicts).
    """
    with path.open() as f:
        return [resource for resource in yaml.load_all(f) if resource is not None]


def dump_manifests(resources, path):
    """Write resources back to a YAML file.

    Creates the parent directory if it doesn't exist. Multiple resources
    are written as a multi-document YAML file.

    Args:
        resources: list of Kubernetes resources (dicts).
        path: Path to the output YAML file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump_all(resources, f)

def produce_stat_report(stats_by_algo, total_resources, path):
    """Write a Markdown summary of per-algo stats to a file.

    Args:
        stats_by_algo: dict mapping algo name to its list of Stat objects.
        total_resources: total number of resources in the manifest.
        path: Path to the output Markdown file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write("# Kubefix stat report\n\n")
        f.write(f"Total resources: {total_resources}\n\n")
        f.write("| Algo | Resources touched | % Resources touched | Labels changed |\n")
        f.write("|------|--------------------|----------------------|------------------|\n")
        for algo, stats in stats_by_algo.items():
            resources_touched = len(stats)
            labels_changed = sum(s.changed_labels for s in stats)
            pct_touched = 100 * resources_touched / total_resources if total_resources else 0
            f.write(f"| {algo} | {resources_touched} | {pct_touched:.1f}% | {labels_changed} |\n")


def produce_csv_report(diagram_name, stats_by_algo, total_resources, path):
    """Append one CSV row per algo with its stats for this manifest.

    Writes a header row the first time the file is created, then appends
    to it on subsequent calls so results from many manifests can be
    aggregated in a single file.

    Args:
        diagram_name: name identifying the manifest.
        stats_by_algo: dict mapping algo name to its list of Stat objects.
        total_resources: total number of resources in the manifest.
        path: Path to the output CSV file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["diagram", "algo", "resources_touched", "labels_changed", "total_resources"])
        for algo, stats in stats_by_algo.items():
            resources_touched = len(stats)
            labels_changed = sum(s.changed_labels for s in stats)
            writer.writerow([diagram_name, algo, resources_touched, labels_changed, total_resources])


@click.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file (default: stdout)")
@click.option("-s", "--stats", type=click.Path(path_type=Path), help="Write a Markdown stat report to this file")
@click.option("-c", "--csv", "csv_path", type=click.Path(path_type=Path), help="Append a CSV stat row per algo to this file")
def cli(input_path: Path, output: Path | None, stats: Path | None, csv_path: Path | None):
    """Run kubefix on a Kubernetes manifest."""
    resources = load_manifests(input_path)
    total_resources = len(resources)
    all_warnings: list[Warning] = []
    stats_by_algo: dict[str, list[Stat]] = {}

    # ALGO 1 : Label normalization
    resources, w, s = algo1_normalize_labels(resources)
    all_warnings.extend(w)
    stats_by_algo["algo1"] = s

    # ALGO 2 : Edge intersection
    resources, w, s = algo2_label_intersection(resources)
    all_warnings.extend(w)
    stats_by_algo["algo2"] = s

    # ALGO 4 : Label unlabeled resources with unambiguous resources
    resources, w, s = algo4_assign_unique_cluster_labels(resources)
    all_warnings.extend(w)
    stats_by_algo["algo4"] = s


    # ALGO 3 : Isolated-resource label
    resources, w, s = algo3_mark_isolated(resources)
    all_warnings.extend(w)
    stats_by_algo["algo3"] = s


    click.echo("")

    for w in all_warnings:
        click.echo(f"[warning] {w.resource_kind}/{w.resource_name}: {w.message}", err=True)

    # Print stats
    click.echo("Number of resources touched by algo :")

    for algo, algo_stats in stats_by_algo.items():
        click.echo(f"   {algo} : {len(algo_stats)}")

    click.echo("Number of labels changed by algo :")

    for algo, algo_stats in stats_by_algo.items():
        click.echo(f"   {algo} : {sum(s.changed_labels for s in algo_stats)}")

    # If there's output option
    if output:
        dump_manifests(resources, output)
        click.echo(f"Wrote {output}", err=True)
    else:
        yaml.dump_all(resources, sys.stdout)

    # If there's stats option
    if stats:
        produce_stat_report(stats_by_algo, total_resources, stats)
        click.echo(f"Wrote {stats}", err=True)

    # If there's csv option
    if csv_path:
        produce_csv_report(input_path.stem, stats_by_algo, total_resources, csv_path)
        click.echo(f"Wrote {csv_path}", err=True)


if __name__ == "__main__":
    cli()