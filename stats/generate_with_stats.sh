#!/bin/bash
cd "$(dirname "$0")/.."

echo Generate original diagrams...
for manifest in `ls examples/*`
do
  base_manifest=`basename $manifest`
  output_diagram="original/${base_manifest//.yaml/}"
  kube-diagrams --without-namespace $manifest -o $output_diagram
done

echo Generate modified diagrams and stats/diagrams_with_stats.md...
content=""
for manifest in `ls examples/*`
do
  base_manifest=`basename $manifest`
  name=${base_manifest//.yaml/}
  output_diagram="modified_diagrams/${name}"
  kubefix $manifest -o fixed-manifest.yaml -s fixed-manifest-stats.md
  kube-diagrams --without-namespace fixed-manifest.yaml -o $output_diagram -c src/kubefix/kubefix.kdc

  content+="## ${name}\n\n"
  content+="| Original diagram | Modified diagram |\n| :---: | :---: |\n"
  content+="| ![${name}](/original/${name}.png) | ![${name}](/modified_diagrams/${name}.png) |\n\n"
  content+="$(cat fixed-manifest-stats.md)\n\n"
done
echo -e "$content" > stats/diagrams_with_stats.md
echo stats/diagrams_with_stats.md generated.
