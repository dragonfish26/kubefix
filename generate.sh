#!/bin/bash

echo Generate original diagrams...
for manifest in `ls examples/*`
do
  base_manifest=`basename $manifest`
  output_diagram="original/${base_manifest//.yaml/}"
  kube-diagrams --without-namespace $manifest -o $output_diagram
done

echo Generate modified diagrams...
for manifest in `ls examples/*`
do
  base_manifest=`basename $manifest`
  output_diagram="modified_diagrams/${base_manifest//.yaml/}"
  kubefix $manifest -o fixed-manifest.yaml
  kube-diagrams --without-namespace fixed-manifest.yaml -o $output_diagram -c src/kubefix/kubefix.kdc
done

echo Generate diagrams.md...
content="| Name | Original diagram | Modified diagram |\n| :---: | :---: | :---: |\n"
for file in `ls examples`
do
  name=${file//.yaml/}
  content+="| ${name} | ![${name}](original/${name}.png) | ![${name}](modified_diagrams/${name}.png) |\n"
done
echo -e $content > diagrams.md
echo diagrams.md generated.
