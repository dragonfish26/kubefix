# Kubefix 

Detect and correct architectural defects in Kubernetes manifests.

## Install and run

Create and activate a virtual environment

    python3 -m venv .venv
    source .venv/bin/activate   

and then run : 

    pip install -e .
    kubefix ex.yaml
    kubefix ex.yaml -o fixed.yaml

or :

    python src/kubefix/main.py examples/ex.yaml -o output/output.yaml

## Generate diagram 

Install KubeDiagrams :

    source .venv/bin/activate   # if not already active
    pip install KubeDiagrams

Also install Graphviz if not already installed.

And then :

    kube-diagrams -o output/output.png output/output.yaml