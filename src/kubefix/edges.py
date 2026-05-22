import json
import yaml
import traceback


def query_path(data, path, default=None):
    """Query nested YAML/dict data by dot-separated path."""
    paths = path.split(".")
    for p in paths[:-1]:
        if not isinstance(data, dict):
            return default
        data = data.get(p)
        if data is None:
            return default
    if not isinstance(data, dict):
        return default
    data = data.get(paths[-1])
    if data is None:
        return default
    return data


def get_name(resource):
    return query_path(resource, "metadata.name") \
        or query_path(resource, "metadata.generateName", "NO-NAME")


def get_namespace(resource, default_namespace="default"):
    return query_path(resource, "metadata.namespace", default_namespace)


def get_type(resource):
    return query_path(resource, "kind", "kind-NOT-SET") + "/" \
        + query_path(resource, "apiVersion", "apiVersion-NOT-SET")


class EdgesDetector:
    """
    Detects edges between Kubernetes resources without any drawing logic.
    Produces a list of (from_id, to_id, edge_kind) tuples.
    """

    def __init__(self, resources, config):
        """
        resources : dict[resource_id -> resource_dict]
        config    : loaded kubefix.yaml as a dict
        """
        self.resources = resources
        self.config = config
        self.edges = []  # list of (from_id, to_id, edge_kind)

        # Current resource being processed; set per-resource in detect_all()
        self.rid = None
        self.resource = None
        self.namespace = None

        # Build plural -> kind mapping from config
        self.plural2kinds = {}
        for k, v in config.get("nodes", {}).items():
            if not isinstance(v, dict):
                continue
            node_kind = k.split("/")[0]
            plural = v.get("plural", node_kind.lower() + "s")
            self.plural2kinds[plural] = node_kind

    # Logging helpers

    def info(self, path, msg):
        name = get_name(self.resource) if self.resource else "?"
        print(f"[Info] {name}:{path} - {msg}.")

    def warning(self, path, msg):
        name = get_name(self.resource) if self.resource else "?"
        print(f"[Warning] {name}:{path} - {msg}!")

    def error(self, path, msg):
        name = get_name(self.resource) if self.resource else "?"
        print(f"[Error] {name}:{path} - {msg}!")

    # Node config helpers

    def _get_node_config(self, resource):
        resource_type = get_type(resource)
        node_config = self.config.get("nodes", {}).get(resource_type)
        while isinstance(node_config, str):
            node_config = self.config.get("nodes", {}).get(node_config)
        return node_config or {}

    def _get_node_config_of_resource_type(self, resource_type):
        node_config = self.config.get("nodes", {}).get(resource_type)
        while isinstance(node_config, str):
            node_config = self.config.get("nodes", {}).get(node_config)
        return node_config or {}

    # Main detection entry point

    def detect_all(self):
        """Run edge detection for every resource. Returns list of (from, to, kind)."""
        for resource_id, resource in self.resources.items():
            self._detect_for_resource(resource_id, resource)
        return self.edges

    def _detect_for_resource(self, resource_id, resource):
        """Run the edge snippet from kubefix.yaml for one resource."""
        self.rid = resource_id
        self.resource = resource
        self.namespace = get_namespace(resource)

        node_config = self._get_node_config(resource)
        code_to_exec = node_config.get("edges")
        if not code_to_exec:
            return

        # The yaml snippets reference 'edges' and 'resource' by name,
        # so we expose them as locals for exec().
        edges = self
        try:
            exec(code_to_exec) 
        except Exception as exc:
            print(f"Error running edge snippet for {resource_id}: {exc}")
            traceback.print_exc()

    # Core edge registration

    def _add_edge(self, from_id, to_id, edge_kind):
        """Record a detected edge as a plain tuple."""
        if to_id in self.resources:
            self.edges.append((from_id, to_id, edge_kind))

    def add_edge_to_rid(self, path, rid, edge_kind, data=None):
        """Add an edge directly by resource ID."""
        if rid in self.resources:
            self._add_edge(self.rid, rid, edge_kind)
        else:
            cluster_resources = self.config.get("cluster-resources", [])
            if rid in cluster_resources:
                self.info(path, f"'{rid}' provided by Kubernetes cluster")
            else:
                self.warning(path, f"'{rid}' undefined")

   