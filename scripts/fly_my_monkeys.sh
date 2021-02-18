#!/bin/bash -xe
ENVIRONMENT=${1:-"http://localhost:8000"}
MONKEY_DIR=${2:-"nublado"}

cd $2
for MONKEY in *
do
  curl -X POST -d "@$MONKEY" -H "Content-Type: application/json" -u $ACCESS_TOKEN: $ENVIRONMENT /mobu/user | python -m json.tool
done
