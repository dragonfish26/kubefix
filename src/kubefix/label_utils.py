"""Helpers shared by the algos: config loading, label access and label naming."""

import re
from pathlib import Path

import yaml

from kubefix.edges.helpers import query_path
from kubefix.common import Warning, Stat, LABEL_HIERARCHY


# Default location of the edges config.
DEFAULT_CONFIG_PATH = Path(__file__).parent / "edges" / "kubefix.yaml"

# Below this length a suggested name is meaningless, so a default is used instead.
MIN_NAME_LENGTH = 3

_MAX_LABEL_VALUE_LENGTH = 63
_INVALID_LABEL_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


# config

def load_config(config_path=None):
    with open(config_path or DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cluster_label_keys(config):
    """Labels that map to clusters in kubefix.yaml.
    Falls back to LABEL_HIERARCHY if the config has no clusters section."""
    keys = [c.get("label") for c in config.get("clusters", []) if "label" in c]
    return keys if keys else list(LABEL_HIERARCHY)


# label access

def labels(resource):
    """Returns the labels of a resource ({} if none)."""
    result = query_path(resource, "metadata.labels", {}) or {}
    return result if isinstance(result, dict) else {}


def set_label(resource, key, value):
    """Set a label of a resource, creating metadata.labels if needed."""
    current = query_path(resource, "metadata.labels")
    if not isinstance(current, dict):
        current = {}
        if not isinstance(resource.get("metadata"), dict):
            resource["metadata"] = {}
        resource["metadata"]["labels"] = current
    current[key] = value


def label_stat(resource, changed_labels=1):
    return Stat(
        resource_kind=resource.get("kind", "?"),
        resource_name=query_path(resource, "metadata.name", "?"),
        changed_labels=changed_labels,
    )


# naming

def longest_common_substring(names):
    """Longest continuous string present in every name ("" if no names).
    Ties go to the leftmost one in the shortest name."""
    if not names:
        return ""
    shortest = min(names, key=lambda n: (len(n), n))
    for length in range(len(shortest), 0, -1):
        for start in range(len(shortest) - length + 1):
            candidate = shortest[start:start + length]
            if all(candidate in name for name in names):
                return candidate
    return ""


def to_label_value(s):
    """Make s a valid label value: replace invalid chars by -,
    cut to max number of chars, strip non-alphanumeric chars at both ends."""
    s = _INVALID_LABEL_CHARS.sub("-", s)[:_MAX_LABEL_VALUE_LENGTH]
    return s.strip("-_.")


def suggest_name(names, default, warnings, resource_kind, resource_name):
    """Label value from the longest common substring of names, or default
    (with a warning attached to resource_kind/resource_name) when it is too short."""
    value = to_label_value(longest_common_substring(names))
    if len(value) < MIN_NAME_LENGTH:
        warnings.append(Warning(
            resource_kind=resource_kind,
            resource_name=resource_name,
            message=f"No common name for {sorted(names)}; using default '{default}'.",
        ))
        value = default
    return value
