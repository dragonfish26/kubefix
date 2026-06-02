"""The EdgesContext class.

The yaml edge scripts call methods on an `edges` object. That object is
an EdgesContext. One EdgesContext is created per resource and collects
the edges found for that resource in `self.edges`.

This file is just the API the yaml scripts talk to. The driver code
that creates contexts and runs the scripts lives in process.py.
"""

import json

from .helpers import (
    get_name,
    get_namespace,
    get_node_config,
    get_node_config_of_resource_type,
    get_type,
    query_path,
)

# The class the yaml edge scripts call into.

class EdgesContext:
    """Holds the state for one resource while its edge script runs.

    The yaml scripts call self.add_* methods, which append tuples to
    self.edges. After the script runs, process.py reads self.edges
    and moves on to the next resource.
    """

    def __init__(self, rid, resource, resources, config, plural2kinds):
        """
        rid          : id of the resource we're processing (the `from` of
                       every edge added through add_edge_to etc.)
        resource     : the resource dict itself
        resources    : the full {rid: resource} dict, used to look up
                       edge targets and to scan for label matches
        config       : the loaded kubefix.yaml
        plural2kinds : map from plural names ('pods') to kinds ('Pod'),
                       built once by process.py and shared across contexts
        """
        self.rid = rid
        self.resource = resource
        self.resources = resources
        self.config = config
        self.plural2kinds = plural2kinds
        self.namespace = get_namespace(resource)
        self.edges = []  # (from_rid, to_rid, edge_kind) tuples for this resource

    # Logging.

    def _report(self, level, path, msg, end):
        rkind = query_path(self.resource, "kind", "NO-KIND")
        name = get_name(self.resource)
        loc = f":{path}" if path is not None else ""
        print(f"[{level}] {rkind}:{name}{loc} - {msg}{end}")

    def info(self, path, msg):
        self._report("Info", path, msg, ".")

    def warning(self, path, msg):
        self._report("Warning", path, msg, "!")

    def error(self, path, msg):
        self._report("Error", path, msg, "!")

    # Edge registration. These three methods are the chokepoint —
    # everything else eventually calls one of them.

    def _add_edge(self, from_id, to_id, edge_kind):
        # edge_kind is always a string ("REFERENCE", "SELECTOR", ...).
        if to_id in self.resources:
            self.edges.append((from_id, to_id, edge_kind))

    def add_edge_to_rid(self, path, rid, edge_kind, data=None):
        if rid in self.resources:
            self._add_edge(self.rid, rid, edge_kind)
        elif rid in self.config.get("cluster-resources", []):
            self.info(path, f"'{rid}' provided by Kubernetes cluster")
        else:
            self.warning(path, f"'{rid}' ined")

    def add_edge_to(self, path, name, namespace, kind, api_version, edge_kind, data=None):
        if name == ".":
            name = query_path(self.resource, path)
        if name is None:
            return
        if name == "":
            self.warning(path, 'Set to ""')
            return

        if namespace is not None:
            rid = f"{name}/{namespace}/{kind}/{api_version}"
        else:
            rid = f"{name}/{kind}/{api_version}"

        target_cfg = get_node_config_of_resource_type(
            f"{kind}/{api_version}", self.config
        )
        if not target_cfg.get("show", True):
            self.info(path, f"{kind} '{name}' hidden")
            return

        if rid in self.resources:
            self._add_edge(self.rid, rid, edge_kind)
        elif rid in self.config.get("cluster-resources", []):
            self.info(path, f"{kind} '{name}' provided by Kubernetes cluster")
        else:
            self.warning(path, f"{kind} '{name}' ined")

    # Label-matching edges.

    def add_all_resources_matching_labels(
        self,
        kind,
        path,
        match_labels=None,
        data=None,
        resource_labels_path="metadata.labels",
        edge_kind="SELECTOR",
        tooltip_data=None,
    ):
        if data is None:
            data = self.resource
        if match_labels is None:
            match_labels = query_path(data, path)
        if match_labels is None:
            return False

        resource_found = False
        for rid, resource in self.resources.items():
            if resource.get("kind") != kind:
                continue
            labels = query_path(resource, resource_labels_path, {})
            if not isinstance(labels, dict):
                continue
            if all(labels.get(k) == v for k, v in match_labels.items()):
                self.add_edge_to_rid(path, rid, edge_kind)
                resource_found = True
        return resource_found

    def add_all_workload_resources(
        self,
        path,
        selector=None,
        default_selector=None,
        edge_kind="SELECTOR",
    ):
        if selector is None:
            selector = query_path(self.resource, path, default_selector)
            if selector is None:
                return

        if query_path(self.resource, "metadata.uid") is not None:
            workload_label_paths = {"Pod": "metadata.labels"}
        else:
            workload_label_paths = {
                "Deployment": "spec.template.metadata.labels",
                "ReplicaSet": "spec.template.metadata.labels",
                "ReplicationController": "spec.template.metadata.labels",
                "StatefulSet": "spec.template.metadata.labels",
                "DaemonSet": "spec.template.metadata.labels",
                "Job": "spec.template.metadata.labels",
                "PodTemplate": "template.metadata.labels",
                "Pod": "metadata.labels",
            }

        resource_not_found = True
        for kind, label_path in workload_label_paths.items():
            if self.add_all_resources_matching_labels(
                kind, path, selector,
                resource_labels_path=label_path,
                edge_kind=edge_kind,
            ):
                resource_not_found = False
                if default_selector is None:
                    break

        if resource_not_found:
            self.warning(path, f"No workload resource matches labels {selector}")

    # Owner edges, based on metadata.ownerReferences.

    def get_owned_resources(self, owner_resource):
        result = []
        uid = query_path(owner_resource, "metadata.uid")
        if uid is None:
            return result
        for _, resource in self.resources.items():
            for owner_ref in query_path(resource, "metadata.ownerReferences", []):
                if owner_ref.get("uid") == uid:
                    result.append(resource)
        return result

    def add_owned_resources(self):
        for resource in self.get_owned_resources(self.resource):
            scope = get_node_config(resource, self.config).get("scope")
            namespace = get_namespace(resource) if scope == "Namespaced" else None
            self.add_edge_to(
                "owns",
                resource["metadata"]["name"],
                namespace,
                resource["kind"],
                resource["apiVersion"],
                "OWNER",
            )

    # Edges for specific resource types.

    def add_resource(self, path):
        target = query_path(self.resource, path)
        if target is None:
            return
        self.add_edge_to(
            path,
            target["name"],
            self.namespace,
            target["kind"],
            target["apiVersion"],
            "REFERENCE-UP",
        )

    def add_resources(self, path, name_path, namespace_path, kind, api_version):
        for ridx, resource in enumerate(query_path(self.resource, path, [])):
            self.add_edge_to(
                f"{path}[{ridx}]",
                resource[name_path],
                resource.get(namespace_path, self.namespace),
                kind,
                api_version,
                "REFERENCE",
            )

    def add_service_account(self, path):
        pod_spec = query_path(self.resource, path)
        if pod_spec is None:
            return
        sa_name = pod_spec.get("serviceAccountName")
        if sa_name is None:
            sa_name = pod_spec.get("serviceAccount")
            if sa_name is not None:
                self.warning(f"{path}.serviceAccount", "Deprecated field")
        if not sa_name:
            return
        self.add_edge_to(
            f"{path}.serviceAccountName",
            sa_name,
            self.namespace,
            "ServiceAccount",
            "v1",
            "REFERENCE",
        )

    def add_role(self, path):
        role_ref = self.resource.get(path)
        if role_ref is None:
            return
        api_group = query_path(role_ref, "apiGroup", "rbac.authorization.k8s.io")
        if api_group == "":
            self.warning(path, 'Set to ""')
            api_group = "rbac.authorization.k8s.io"
        namespace = self.namespace if role_ref.get("kind") == "Role" else None
        self.add_edge_to(
            path,
            role_ref["name"],
            namespace,
            role_ref["kind"],
            f"{api_group}/v1",
            "REFERENCE",
        )

    def add_subjects(self):
        for idx, subject in enumerate(query_path(self.resource, "subjects", [])):
            namespace = subject.get("namespace")
            if namespace is None and subject.get("kind") == "ServiceAccount":
                namespace = get_namespace(self.resource)
            if namespace is not None:
                api_version = query_path(subject, "apiGroup", "v1") or "v1"
            else:
                api_group = query_path(
                    subject, "apiGroup", "rbac.authorization.k8s.io"
                ) or "rbac.authorization.k8s.io"
                api_version = f"{api_group}/v1"
            self.add_edge_to(
                f"subjects[{idx}]",
                subject["name"],
                namespace,
                subject["kind"],
                api_version,
                "REFERENCE-UP",
            )

    def add_service(self, path, data=None, name=None):
        if data is None:
            data = self.resource
        if name is None:
            name = query_path(data, path)
        self.add_edge_to(path, name, self.namespace, "Service", "v1", "REFERENCE")

    def add_edges_for_service(self):
        self.add_all_workload_resources("spec.selector")
        self.add_all_resources_matching_labels(
            "EndpointSlice",
            "endpoint_slice",
            {"kubernetes.io/service-name": query_path(self.resource, "metadata.name")},
        )
        rid = (
            f"{query_path(self.resource, 'metadata.name')}"
            f"/{get_namespace(self.resource)}/Endpoints/v1"
        )
        if rid in self.resources:
            self._add_edge(self.rid, rid, "OWNER")

    # Volumes and env vars referenced from pod specs.

    def add_all_volume_resources(self, path):
        def process_volumes(volumes, current_path):
            for idx, volume in enumerate(volumes):
                if "configMap" in volume:
                    cm = volume["configMap"]
                    if cm is None:
                        continue
                    cm_name = cm.get("name")
                    cm_id = f"{cm_name}/{self.namespace}/ConfigMap/v1"
                    if cm.get("optional") is True and cm_id not in self.resources:
                        self.info(f"{current_path}[{idx}].configMap",
                                  f"ConfigMap '{cm_name}' ined but optional")
                        continue
                    self.add_edge_to(f"{current_path}[{idx}].configMap",
                                     cm_name, self.namespace, "ConfigMap", "v1", "REFERENCE")

                elif "secret" in volume:
                    secret = volume["secret"]
                    if secret is None:
                        continue
                    secret_name = secret.get("secretName") or secret.get("name")
                    secret_id = f"{secret_name}/{self.namespace}/Secret/v1"
                    if secret.get("optional") is True and secret_id not in self.resources:
                        self.info(f"{current_path}[{idx}].secret",
                                  f"Secret '{secret_name}' ined but optional")
                        continue
                    self.add_edge_to(f"{current_path}[{idx}].secret",
                                     secret_name, self.namespace, "Secret", "v1", "REFERENCE")

                elif "persistentVolumeClaim" in volume:
                    claim_name = query_path(volume, "persistentVolumeClaim.claimName")
                    self.add_edge_to(
                        f"{current_path}[{idx}].persistentVolumeClaim",
                        claim_name, self.namespace, "PersistentVolumeClaim", "v1", "REFERENCE",
                    )

                elif "projected" in volume:
                    sources = query_path(volume, "projected.sources")
                    if sources is not None:
                        process_volumes(sources, current_path + ".projected.sources")

        volumes = query_path(self.resource, path)
        if volumes is not None:
            process_volumes(volumes, path)

    def add_containers_env_value_from_and_env_from(self, path):
        containers = query_path(self.resource, path)
        if containers is None:
            return

        target_resource_ids = set()

        def collect(context, kind, name_path, optional_path):
            name = query_path(context, name_path)
            if name is None:
                return
            rid = f"{name}/{self.namespace}/{kind}/v1"
            if query_path(context, optional_path) is True and rid not in self.resources:
                return
            target_resource_ids.add(rid)

        for container in containers:
            for env in query_path(container, "env", []):
                collect(env, "ConfigMap",
                        "valueFrom.configMapKeyRef.name",
                        "valueFrom.configMapKeyRef.optional")
                collect(env, "Secret",
                        "valueFrom.secretKeyRef.name",
                        "valueFrom.secretKeyRef.optional")
            for env_from in query_path(container, "envFrom", []):
                collect(env_from, "ConfigMap", "configMapRef.name", "configMapRef.optional")
                collect(env_from, "Secret", "secretRef.name", "secretRef.optional")

        for rid in target_resource_ids:
            self.add_edge_to_rid(path, rid, "REFERENCE")

    def add_volume_claim_templates(self, path):
        for idx, vct in enumerate(query_path(self.resource, path, [])):
            self.add_edge_to(
                f"{path}[{idx}]",
                vct["metadata"]["name"],
                self.namespace,
                "PersistentVolumeClaim",
                "v1",
                "REFERENCE",
            )

    def add_wait_for_services(self, path):
        for ic in query_path(self.resource, path, []):
            if ic.get("name") == "wait-for-services":
                for arg in query_path(ic, "args", []):
                    if arg.startswith("-service="):
                        sn = arg[len("-service="):]
                        self.add_edge_to(path, sn, self.namespace,
                                         "Service", "v1", "DEPENDENCE")

    def add_networks(self, path):
        annotations = query_path(self.resource, path)
        if annotations is None:
            return
        networks_raw = annotations.get("k8s.v1.cni.cncf.io/networks")
        if networks_raw is None:
            return
        try:
            networks = json.loads(networks_raw)
        except json.JSONDecodeError:
            self.warning(f"{path}:k8s.v1.cni.cncf.io/networks",
                         f"Invalid JSON '{networks_raw}'")
            return
        for nidx, network in enumerate(networks):
            self.add_edge_to(
                f"{path}:k8s.v1.cni.cncf.io/networks[{nidx}]",
                network["name"],
                get_namespace(self.resource),
                "NetworkAttachmentDefinition",
                "k8s.cni.cncf.io/v1",
                "REFERENCE",
            )

    def add_priority_class(self, path):
        if query_path(self.resource, path) == "":
            return
        self.add_edge_to(path, ".", None, "PriorityClass", "scheduling.k8s.io/v1", "REFERENCE")

    # Webhooks.

    def add_webhooks(self):
        for idx, webhook in enumerate(query_path(self.resource, "webhooks", [])):
            service = query_path(webhook, "clientConfig.service")
            if service is not None:
                self.add_edge_to(
                    f"webhooks[{idx}].clientConfig.service",
                    service["name"],
                    service["namespace"],
                    "Service",
                    "v1",
                    "REFERENCE",
                )

    # NetworkPolicy ingress/egress rules.

    def add_ingress_and_egress_rules(self):
        selected_nodes = [e[1] for e in self.edges]

        for ridx, ingress_rule in enumerate(query_path(self.resource, "spec.ingress", [])):
            for fidx, ingress_from in enumerate(query_path(ingress_rule, "from", [])):
                if "podSelector" not in ingress_from:
                    continue
                before = len(self.edges)
                self.add_all_workload_resources(
                    f"spec.ingress[{ridx}].from[{fidx}]",
                    query_path(ingress_from, "podSelector.matchLabels", {}),
                    edge_kind="INVISIBLE",
                )
                from_workloads = [e[1] for e in self.edges[before:]]
                for rid_from in from_workloads:
                    for rid_to in selected_nodes:
                        self._add_edge(rid_from, rid_to, "COMMUNICATION")

        for egress_rule in query_path(self.resource, "spec.egress", []):
            for egress_to in query_path(egress_rule, "to", []):
                if "podSelector" not in egress_to:
                    continue
                before = len(self.edges)
                self.add_all_workload_resources(
                    "spec.egress",
                    query_path(egress_to, "podSelector.matchLabels", {}),
                    edge_kind="INVISIBLE",
                )
                to_workloads = [e[1] for e in self.edges[before:]]
                for rid_to in to_workloads:
                    for rid_from in selected_nodes:
                        self._add_edge(rid_from, rid_to, "COMMUNICATION")

    # RBAC rule edges (resourceNames in Role/ClusterRole).

    def add_rules_resource_names(self):
        for ridx, rule in enumerate(query_path(self.resource, "rules", [])):
            if not isinstance(rule, dict):
                continue
            resource_names = query_path(rule, "resourceNames")
            if resource_names is None:
                continue
            api_groups = query_path(rule, "apiGroups")
            if not api_groups or len(api_groups) != 1:
                self.error(f"rules[{ridx}]", "apiGroups should contain exactly one value")
                continue
            api_group = api_groups[0]
            api_version = "v1" if api_group == "" else f"{api_group}/v1"
            for resource in query_path(rule, "resources", []):
                if "/" in resource:
                    continue
                kind = self.plural2kinds.get(resource, resource)
                for rnidx, resource_name in enumerate(resource_names):
                    if not isinstance(resource_name, str) or "*" in resource_name:
                        continue
                    target_cfg = get_node_config_of_resource_type(
                        f"{kind}/{api_version}", self.config
                    )
                    scope = target_cfg.get("scope")
                    namespace = self.namespace if scope == "Namespaced" else None
                    self.add_edge_to(
                        f"rules[{ridx}].resourceNames[{rnidx}]",
                        resource_name, namespace, kind, api_version, "REFERENCE-UP",
                    )