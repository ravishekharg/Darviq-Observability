#!/usr/bin/env bash
# Starts the stack with Zabbix and configures Zabbix through its API, in one command.
#   bash scripts/zabbix-up.sh
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose --profile zabbix up -d
echo "== Waiting for the Zabbix web UI"
until curl -fs -o /dev/null http://localhost:8081/; do sleep 5; done
# A brand-new Zabbix database has no planner statistics, and Zabbix's template-linking query then
# runs for many minutes (found the hard way: it pinned Postgres at 100% CPU). ANALYZE takes 2 s.
echo "== Updating database statistics"
docker compose exec -T zabbix-db psql -U zabbix -d zabbix -qc "ANALYZE"
python zabbix/provision.py
