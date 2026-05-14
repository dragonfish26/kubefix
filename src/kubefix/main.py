from pathlib import Path
import sys

import click
from ruamel.yaml import YAML
from dataclasses import dataclass

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

# ALGO 1 : Label normalization

@dataclass
class Warning:
    resource_kind: str
    resource_name: str
    message: str

LABEL_MAPPING: dict[str, str] = {
    "release": "app.kubernetes.io/instance",
    "chart":   "helm.sh/chart",
    "app":     "app.kubernetes.io/name",
}

RECOMMENDED_LABELS: set[str] = {
    "app.kubernetes.io/instance",
    "helm.sh/chart",
    "app.kubernetes.io/name",
    "app.kubernetes.io/component",
}

def algo1_normalize_labels(docs: list[dict]) -> tuple[list[dict], list[Warning]]:
    """Replace non-recommended labels with their recommended equivalents."""
    warnings: list[Warning] = []

    for resource in docs:
        labels = resource.get("metadata", {}).get("labels")
        if not labels:
            continue

        for old_key, value in list(labels.items()):
            if old_key not in LABEL_MAPPING:
                continue  # already recommended, or unknown, so leave it alone

            new_key = LABEL_MAPPING[old_key]

            if new_key in labels:
                # recommended label already present
                if labels[new_key] == value:
                    # same value, just drop the duplicate
                    del labels[old_key]
                else:
                    # different values : keep recommended, drop non-recommended, warn
                    warnings.append(Warning(
                        resource_kind=resource.get("kind", "?"),
                        resource_name=resource.get("metadata", {}).get("name", "?"),
                        message=(
                            f"Conflict: '{old_key}={value}' vs "
                            f"'{new_key}={labels[new_key]}'. Kept recommended."
                        ),
                    ))
                    del labels[old_key]
            else:
                # recommended label not present, simple rename
                labels[new_key] = value
                del labels[old_key]

    return docs, warnings

@click.command()
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Output file (default: stdout)")
def cli(input_path: Path, output: Path | None):
    """Run kubefix on a Kubernetes manifest."""
    docs = load_manifests(input_path)
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