from pathlib import Path
import sys

import click
from ruamel.yaml import YAML

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


@click.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file (default: stdout)")
def cli(input_path: Path, output: Path | None):
    """Run kubefix on a Kubernetes manifest."""
    resources = load_manifests(input_path)
    all_warnings = []  

    # ALGO 1 : Label normalization
    resources, w = algo1_normalize_labels(resources)
    all_warnings.extend(w)  

    # ALGO 2 : Edge intersection 
    resources, w = algo2_label_intersection(resources)
    all_warnings.extend(w) 

    # ALGO 4 : Label unlabeled resources with unambiguous resources
    resources, w = algo4_assign_unique_cluster_labels(resources)
    all_warnings.extend(w)

    # ALGO 3 : Isolated-resource label
    resources, w = algo3_mark_isolated(resources)
    all_warnings.extend(w)

    for w in all_warnings:
        click.echo(f"[warning] {w.resource_kind}/{w.resource_name}: {w.message}", err=True)

    if output:
        dump_manifests(resources, output)
        click.echo(f"Wrote {output}", err=True)
    else:
        yaml.dump_all(resources, sys.stdout)


if __name__ == "__main__":
    cli()