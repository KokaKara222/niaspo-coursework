#!/bin/sh
set -eu
cd "$(dirname "$0")"
nodes() { docker compose -f nodes.yaml "$@"; }
engine() { node=$1; shift; nodes exec -T "$node" docker "$@"; }
nodes up -d
for node in manager worker1 worker2; do
  tries=0
  until engine "$node" info >/dev/null 2>&1; do
    tries=$((tries+1))
    [ "$tries" -lt 60 ] || exit 1
    sleep 2
  done
done
manager_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$(nodes ps -q manager)")
if [ "$(engine manager info -f '{{.Swarm.LocalNodeState}}')" = inactive ]; then
  engine manager swarm init --advertise-addr "$manager_ip" >/dev/null
fi
token=$(engine manager swarm join-token -q worker)
for worker in worker1 worker2; do
  if [ "$(engine "$worker" info -f '{{.Swarm.LocalNodeState}}')" = inactive ]; then
    engine "$worker" swarm join --token "$token" "$manager_ip:2377"
  fi
  docker image save niaspo-payments-app:latest | engine "$worker" load
done
docker image save postgres:17-alpine nginx:1.28-alpine prom/prometheus:v3.5.0 | engine manager load
nodes exec -T manager mkdir -p /tmp/payment-stack
tar -cf - stack.yaml swarm-nginx.conf swarm-prometheus.yml | nodes exec -T manager tar -xf - -C /tmp/payment-stack
nodes exec -T -w /tmp/payment-stack manager docker stack deploy --resolve-image never -c stack.yaml payments
engine manager node ls
engine manager stack services payments
