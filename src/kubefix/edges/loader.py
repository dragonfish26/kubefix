"""Read manifest files into a {rid: resource} dict.

This is the first phase of the pipeline. After loading, hand the dict
to create_new_nodes() and then process_edges() in process.py.
"""

import yaml

from .process import compute_rid


def load_manifests(filenames, config):
    """Read one or more yaml files. Handles multi-doc files and *List
    wrappers (e.g. PodList). Duplicate rids print a warning and the
    later one wins."""
    resources = {}
    for fn in filenames:
        with open(fn, encoding="utf-8") as f:
            for doc in yaml.safe_load_all(f):
                if doc is None:
                    continue
                if doc.get("kind", "").endswith("List") and "items" in doc:
                    for item in doc["items"]:
                        _add(resources, item, config)
                else:
                    _add(resources, doc, config)
    return resources


def _add(resources, resource, config):
    rid = compute_rid(resource, config)
    if rid in resources:
        print(f"[Warning] duplicate rid {rid}")
    resources[rid] = resource