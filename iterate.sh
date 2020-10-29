#!/bin/bash -ex
helm delete --purge mobu-dev || true
docker build -t lsstsqre/mobu:dev .
helm upgrade --install mobu-dev lsstsqre/mobu --namespace mobu-dev --values dev-values.yaml
