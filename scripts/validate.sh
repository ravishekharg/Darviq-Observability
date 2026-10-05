#!/usr/bin/env bash
# Checks everything the stack is configured with, using the same tools Prometheus and
# Alertmanager use themselves (run in containers, so nothing to install). CI runs this on every
# change; run it locally before committing.
#   bash scripts/validate.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export MSYS_NO_PATHCONV=1   # Git Bash on Windows: don't rewrite the /p paths below
ROOT="$(pwd -W 2>/dev/null || pwd)"
PROM="docker run --rm -v $ROOT/prometheus:/p -w /p --entrypoint promtool prom/prometheus:v2.55.1"

echo "== Prometheus config";  $PROM check config --syntax-only /p/prometheus.yml
echo "== Alert and recording rules"; $PROM check rules /p/rules/recording.yml /p/rules/alerts.yml
echo "== Rule unit tests";     $PROM test rules /p/tests/alerts_test.yml
echo "== Alertmanager config"
docker run --rm -v "$ROOT/alertmanager:/a" --entrypoint amtool prom/alertmanager:v0.27.0 check-config /a/alertmanager.yml
echo "== Every alert links to a runbook section that exists"
alerts=$(grep -c "alert: " prometheus/rules/alerts.yml)
links=$(grep -c "runbook: docs/runbooks.md#" prometheus/rules/alerts.yml)
[ "$alerts" = "$links" ] || { echo "$alerts alerts but $links runbook links"; exit 1; }
for anchor in $(grep -oE "runbooks.md#[a-z0-9]+" prometheus/rules/alerts.yml | cut -d# -f2 | sort -u); do
  grep -qiE "^## $anchor$" docs/runbooks.md || { echo "runbook link #$anchor has no section"; exit 1; }
done
echo "== Dashboards are up to date with build_dashboards.py"
python grafana/build_dashboards.py >/dev/null
git diff --quiet -- grafana/dashboards || { echo "dashboards changed: commit the regenerated JSON"; exit 1; }
echo "== Loki config"
docker run --rm -v "$ROOT/loki:/l" grafana/loki:3.2.1 -config.file=/l/loki.yml -verify-config >/dev/null && echo "  valid"
echo "== Python (provisioning, receiver, exporter) compiles"
python -m py_compile zabbix/provision.py alert-receiver/receiver.py docker-exporter/exporter.py grafana/build_dashboards.py && echo "  ok"
echo "== Datadog Terraform"
TF="docker run --rm -v $ROOT/datadog/terraform:/tf -w /tf hashicorp/terraform:1.9"
$TF fmt -check && $TF init -backend=false -input=false >/dev/null && $TF validate
echo "All checks passed."
