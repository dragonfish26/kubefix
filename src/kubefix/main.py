from pathlib import Path
import sys

import click
from ruamel.yaml import YAML

from kubefix.algo1 import algo1_normalize_labels

yaml = YAML()
yaml.preserve_quotes = True
yaml.indent(mapping=2, sequence=4, offset=2)


def load_manifests(path: Path) -> list[dict]:
    """Load all K8s resources from a YAML file (handles multi-doc)."""
    with path.open() as f:
        return [doc for doc in yaml.load_all(f) if doc is not None]


def dump_manifests(docs: list[dict], path: Path) -> None:
    """Write resources back to YAML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump_all(docs, f)


@click.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file (default: stdout)")
def cli(input_path: Path, output: Path | None):
    """Run kubefix on a Kubernetes manifest."""
    docs = load_manifests(input_path)
    # ALGO 1 : Label normalization
    docs, warnings = algo1_normalize_labels(docs)

    for w in warnings:
        click.echo(f"[warning] {w.resource_kind}/{w.resource_name}: {w.message}", err=True)

    if output:
        dump_manifests(docs, output)
        click.echo(f"Wrote {output}", err=True)
    else:
        yaml.dump_all(docs, sys.stdout)


if __name__ == "__main__":
    cli()