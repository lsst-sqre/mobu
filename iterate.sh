#!/bin/bash -ex
if [ -f dev-chart.tgz ]
then
  CHART=dev-chart.tgz
else
  CHART=lsst-sqre/mobu
fi

helm delete mobu-dev -n mobu-dev || true
docker build -t lsstsqre/mobu:dev .
helm upgrade --install mobu-dev $CHART --create-namespace --namespace mobu-dev --values dev-values.yaml
