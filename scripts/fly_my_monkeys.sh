#!/bin/bash -xe

curl -X POST -d "@lsptestuser01.json" -H "Content-Type: application/json" http://localhost:8000/sciencemonkey/user | python -m json.tool
curl -X POST -d "@lsptestuser02.json" -H "Content-Type: application/json" http://localhost:8000/sciencemonkey/user | python -m json.tool
curl -X POST -d "@lsptestuser03.json" -H "Content-Type: application/json" http://localhost:8000/sciencemonkey/user | python -m json.tool
curl -X POST -d "@lsptestuser04.json" -H "Content-Type: application/json" http://localhost:8000/sciencemonkey/user | python -m json.tool
curl -X POST -d "@lsptestuser05.json" -H "Content-Type: application/json" http://localhost:8000/sciencemonkey/user | python -m json.tool
