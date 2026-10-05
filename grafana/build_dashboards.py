"""Generates the Grafana dashboards in grafana/dashboards/ from code, so they are reviewed and
versioned like everything else (Grafana is provisioned read-only from these files).

    python grafana/build_dashboards.py

Queries use the recording rules in prometheus/rules/recording.yml wherever one exists, so a panel
and the alert that pages someone always agree on what "error ratio" or "p95" means.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "dashboards"
DS = {"type": "prometheus", "uid": "prometheus"}
GREEN, AMBER, RED, BLUE = "#3fb27f", "#e0a526", "#e05252", "#5b8def"


class Layout:
    """Places panels left to right on Grafana's 24-column grid, wrapping to new rows."""

    def __init__(self):
        self.x = self.y = self.row_h = 0
        self.next_id = 1

    def place(self, w, h):
        if self.x + w > 24:
            self.x, self.y, self.row_h = 0, self.y + self.row_h, 0
        pos = {"x": self.x, "y": self.y, "w": w, "h": h}
        self.x += w
        self.row_h = max(self.row_h, h)
        self.next_id += 1
        return pos, self.next_id - 1


def targets(*queries):
    return [{"datasource": DS, "expr": q, "legendFormat": legend, "refId": chr(65 + i), "instant": False}
            for i, (q, legend) in enumerate(queries)]


def thresholds(*steps):
    return {"mode": "absolute", "steps": [{"color": c, "value": v} for v, c in steps]}


def stat(layout, title, query, unit="none", steps=((None, GREEN),), w=4, h=4, decimals=None, desc=""):
    pos, pid = layout.place(w, h)
    defaults = {"unit": unit, "thresholds": thresholds(*steps), "color": {"mode": "thresholds"}}
    if decimals is not None:
        defaults["decimals"] = decimals
    return {"type": "stat", "id": pid, "title": title, "description": desc, "gridPos": pos, "datasource": DS,
            "targets": targets((query, "")),
            "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"colorMode": "background", "graphMode": "area", "justifyMode": "center", "textMode": "value",
                        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}}}


def timeseries(layout, title, queries, unit="short", w=12, h=8, steps=None, stack=False, desc="", fill=12, no_value=None):
    pos, pid = layout.place(w, h)
    defaults = {"unit": unit, "color": {"mode": "palette-classic"},
                "custom": {"lineWidth": 2, "fillOpacity": fill, "gradientMode": "opacity", "showPoints": "never",
                           "stacking": {"mode": "normal" if stack else "none"},
                           "thresholdsStyle": {"mode": "line+area" if steps else "off"}}}
    if steps:
        defaults["thresholds"] = thresholds(*steps)
    if no_value:
        defaults["noValue"] = no_value
    return {"type": "timeseries", "id": pid, "title": title, "description": desc, "gridPos": pos, "datasource": DS,
            "targets": targets(*queries), "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"legend": {"displayMode": "table", "placement": "right", "calcs": ["lastNotNull", "max"]},
                        "tooltip": {"mode": "multi", "sort": "desc"}}}


def state_timeline(layout, title, query, legend, w=24, h=8, desc=""):
    pos, pid = layout.place(w, h)
    return {"type": "state-timeline", "id": pid, "title": title, "description": desc, "gridPos": pos, "datasource": DS,
            "targets": targets((query, legend)),
            "fieldConfig": {"defaults": {
                "color": {"mode": "thresholds"}, "thresholds": thresholds((None, RED), (1, GREEN)),
                "mappings": [{"type": "value", "options": {"0": {"text": "Down", "color": RED},
                                                           "1": {"text": "Up", "color": GREEN}}}],
                "custom": {"fillOpacity": 80, "lineWidth": 0}}, "overrides": []},
            "options": {"showValue": "never", "rowHeight": 0.8, "mergeValues": True,
                        "legend": {"showLegend": False}, "tooltip": {"mode": "single"}}}


def bargauge(layout, title, query, legend, unit, steps, w=12, h=8, desc="", minv=None, maxv=None):
    pos, pid = layout.place(w, h)
    defaults = {"unit": unit, "thresholds": thresholds(*steps), "color": {"mode": "thresholds"}}
    if minv is not None:
        defaults["min"] = minv
    if maxv is not None:
        defaults["max"] = maxv
    return {"type": "bargauge", "id": pid, "title": title, "description": desc, "gridPos": pos, "datasource": DS,
            "targets": [{**targets((query, legend))[0], "instant": True}],
            "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"displayMode": "gradient", "orientation": "horizontal", "showUnfilled": True,
                        "valueMode": "color", "namePlacement": "left",
                        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}}}


def alert_list(layout, title, w=24, h=7):
    pos, pid = layout.place(w, h)
    return {"type": "table", "id": pid, "title": title, "gridPos": pos, "datasource": DS,
            "targets": [{"datasource": DS, "refId": "A", "instant": True, "format": "table",
                         "expr": 'ALERTS{alertstate="firing", alertname!="Watchdog"}'}],
            "transformations": [{"id": "organize", "options": {
                "excludeByName": {"Time": True, "Value": True, "__name__": True, "alertstate": True, "job": True},
                "indexByName": {"severity": 0, "alertname": 1, "product": 2, "instance": 3},
                "renameByName": {"alertname": "Alert", "severity": "Severity", "product": "Product",
                                 "instance": "Instance", "service": "Service"}}}],
            "fieldConfig": {"defaults": {"custom": {"align": "left"}, "noValue": "No alerts firing"},
                            "overrides": [{"matcher": {"id": "byName", "options": "Severity"}, "properties": [
                                {"id": "custom.cellOptions", "value": {"type": "color-background"}},
                                {"id": "mappings", "value": [{"type": "value", "options": {
                                    "critical": {"color": RED, "text": "critical"},
                                    "warning": {"color": AMBER, "text": "warning"}}}]}]}]},
            "options": {"showHeader": True, "cellHeight": "sm"}}


def dashboard(uid, title, description, panels, refresh="30s", time_from="now-1h", templating=None, tags=()):
    return {"uid": uid, "title": title, "description": description, "tags": ["darviq", *tags],
            "timezone": "browser", "schemaVersion": 39, "version": 1, "editable": False,
            "graphTooltip": 1, "refresh": refresh, "time": {"from": time_from, "to": "now"},
            "templating": {"list": templating or []}, "annotations": {"list": []}, "links": [
                {"type": "dashboards", "tags": ["darviq"], "asDropdown": False, "title": "Dashboards"}],
            "panels": panels}


def product_var():
    return {"name": "product", "label": "Product", "type": "query", "datasource": DS,
            "query": {"query": "label_values(up{job=\"apps\"}, product)", "refId": "product"},
            "definition": "label_values(up{job=\"apps\"}, product)",
            "includeAll": True, "multi": True, "allValue": ".*", "current": {"text": "All", "value": "$__all"},
            "refresh": 2, "sort": 1}


def platform_overview():
    L = Layout()
    p = '{product=~"$product"}'
    panels = [
        stat(L, "Services up", f'sum(up{{job="apps", product=~"$product"}})', w=4,
             steps=((None, RED), (1, GREEN)), desc="Application targets Prometheus can scrape."),
        stat(L, "Services down", f'count(up{{job="apps", product=~"$product"}} == 0) or vector(0)', w=4,
             steps=((None, GREEN), (1, RED))),
        stat(L, "Alerts firing", 'count(ALERTS{alertstate="firing", alertname!="Watchdog"}) or vector(0)', w=4,
             steps=((None, GREEN), (1, AMBER))),
        stat(L, "Requests / s", f"sum(service:http_requests:rate5m{p})", unit="reqps", decimals=1, w=4,
             steps=((None, BLUE),)),
        stat(L, "Error ratio (5 min)",
             f"sum(service:http_errors:rate5m{p}) / clamp_min(sum(service:http_requests:rate5m{p}), 1e-9)",
             unit="percentunit", decimals=2, w=4, steps=((None, GREEN), (0.01, AMBER), (0.05, RED))),
        stat(L, "Slowest p95", f"max(service:http_latency_p95:5m{p})", unit="s", decimals=2, w=4,
             steps=((None, GREEN), (0.25, AMBER), (0.5, RED))),
        alert_list(L, "Firing alerts", h=6),
        timeseries(L, "Requests per second by service", [(f"service:http_requests:rate5m{p}", "{{service}}")],
                   unit="reqps", stack=True),
        timeseries(L, "Error ratio by service (5xx)", [(f"service:http_error_ratio:rate5m{p}", "{{service}}")],
                   unit="percentunit", steps=((None, "transparent"), (0.05, RED)),
                   desc="The HighErrorRate alert fires above the red line (5%) when there is real traffic."),
        timeseries(L, "p95 latency by service", [(f"service:http_latency_p95:5m{p}", "{{service}}")],
                   unit="s", steps=((None, "transparent"), (0.5, AMBER)), fill=0,
                   desc="HighLatencyP95 fires above 500 ms."),
        timeseries(L, "Responses by status code", [
            (f'sum by (status) (rate(http_requests_total{{product=~"$product"}}[5m]))', "{{status}}")],
            unit="reqps", stack=True),
        state_timeline(L, "Service availability", f'up{{job="apps", product=~"$product"}}', "{{instance}}", h=10,
                       desc="Each row is one service; red is time Prometheus could not reach it."),
    ]
    return dashboard("platform-overview", "Platform overview",
                     "Health of every monitored application: traffic, errors, latency and availability.",
                     panels, templating=[product_var()], tags=("overview",))


def uptime():
    L = Layout()
    panels = [
        stat(L, "Checks passing", "sum(probe_success) / count(probe_success)", unit="percentunit", w=6,
             steps=((None, RED), (0.99, AMBER), (1, GREEN))),
        stat(L, "Uptime over the range", "avg(avg_over_time(probe_success[$__range]))", unit="percentunit",
             decimals=3, w=6, steps=((None, RED), (0.99, AMBER), (0.999, GREEN))),
        stat(L, "Slowest check", "max(probe_duration_seconds)", unit="s", decimals=2, w=6,
             steps=((None, GREEN), (1, AMBER), (2, RED))),
        stat(L, "Next certificate expiry", "min((probe_ssl_earliest_cert_expiry - time()) / 86400)", unit="d",
             decimals=0, w=6, steps=((None, RED), (14, AMBER), (30, GREEN)),
             desc="Days until the soonest TLS certificate among the HTTPS checks expires."),
        state_timeline(L, "Synthetic checks", "probe_success", "{{instance}}", h=8),
        timeseries(L, "Response time", [("probe_duration_seconds", "{{instance}}")], unit="s", w=12, h=9, fill=0,
                   steps=((None, "transparent"), (2, AMBER))),
        timeseries(L, "Response time by phase (darviq.com)", [
            ('avg by (phase) (probe_http_duration_seconds{product="darviq-website"})', "{{phase}}")],
            unit="s", w=12, h=9, stack=True,
            desc="Where the time goes: DNS lookup, TCP connect, TLS handshake, server processing, transfer."),
        bargauge(L, "TLS certificate days remaining", "(probe_ssl_earliest_cert_expiry - time()) / 86400",
                 "{{instance}}", "d", ((None, RED), (14, AMBER), (30, GREEN)), w=12, h=7, minv=0, maxv=90),
        bargauge(L, "Uptime per check (selected range)", "avg_over_time(probe_success[$__range])", "{{instance}}",
                 "percentunit", ((None, RED), (0.99, AMBER), (0.999, GREEN)), w=12, h=7, minv=0.95, maxv=1),
    ]
    return dashboard("uptime", "Uptime and certificates",
                     "Synthetic HTTP checks from outside the applications, including TLS certificate expiry.",
                     panels, tags=("uptime",))


def by_disk(expr):
    """One series per physical disk, not per mountpoint: the same disk is often mounted in several
    places (bind mounts, Docker Desktop's WSL paths). Windows drives show as C:, D:."""
    return f'label_replace(max by (device) ({expr}), "device", "$1:", "device", "([A-Za-z]):.*")'


def hosts():
    L = Layout()
    # "drivers" and "rootfs" are Docker Desktop's internal views of disks that are already listed
    fs = 'fstype!~"tmpfs|overlay|squashfs|nsfs|fuse.*|rootfs", device!="drivers"'
    panels = [
        stat(L, "CPU busy", "avg(instance:cpu_busy_ratio:rate5m)", unit="percentunit", w=6,
             steps=((None, GREEN), (0.7, AMBER), (0.9, RED))),
        stat(L, "Memory used", "avg(instance:memory_used_ratio)", unit="percentunit", w=6,
             steps=((None, GREEN), (0.75, AMBER), (0.9, RED))),
        stat(L, "Lowest free disk", "min(instance:disk_free_ratio)", unit="percentunit", w=6,
             steps=((None, RED), (0.05, AMBER), (0.15, GREEN))),
        stat(L, "Containers running", 'count(container_last_seen{name!=""})', w=6, steps=((None, BLUE),)),
        timeseries(L, "CPU by mode", [
            ('sum by (mode) (rate(node_cpu_seconds_total{mode!="idle"}[5m])) / scalar(count(node_cpu_seconds_total{mode="idle"}))',
             "{{mode}}")], unit="percentunit", stack=True),
        timeseries(L, "Memory", [
            ("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "used"),
            ("node_memory_MemAvailable_bytes", "available")], unit="bytes", stack=True),
        bargauge(L, "Free space by disk", by_disk('instance:disk_free_ratio{fstype!="rootfs", device!="drivers"}'), "{{device}}", "percentunit",
                 ((None, RED), (0.05, AMBER), (0.15, GREEN)), w=12, h=8, minv=0, maxv=1),
        timeseries(L, "Hours until full at the current rate", [
            (by_disk(f"(node_filesystem_avail_bytes{{{fs}}} / clamp_min(-deriv(node_filesystem_avail_bytes{{{fs}}}[6h]), 1e-9)) / 3600 < 24 * 30"),
             "{{device}}")], unit="h", fill=0, steps=((None, RED), (24, AMBER), (72, "transparent")),
            desc="Only filesystems that are filling and would be full within 30 days. DiskWillFillIn24h fires below 24 h.",
            no_value="No disk is filling up"),
        timeseries(L, "Container CPU (top 10)", [
            ('topk(10, sum by (name) (rate(container_cpu_usage_seconds_total{name!=""}[5m])))', "{{name}}")],
            unit="percentunit", fill=0),
        timeseries(L, "Container memory (top 10)", [
            ('topk(10, sum by (name) (container_memory_working_set_bytes{name!=""}))', "{{name}}")],
            unit="bytes", fill=0),
        timeseries(L, "Network traffic", [
            ('sum(rate(node_network_receive_bytes_total{device!~"lo|veth.*|docker.*|br-.*"}[5m]))', "received"),
            ('-sum(rate(node_network_transmit_bytes_total{device!~"lo|veth.*|docker.*|br-.*"}[5m]))', "sent")],
            unit="Bps", w=24, h=7),
    ]
    return dashboard("hosts", "Hosts and containers",
                     "The machine running the workloads and every container on it: CPU, memory, disk and network.",
                     panels, tags=("infrastructure",))


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for board, name in ((platform_overview(), "platform-overview"), (uptime(), "uptime"), (hosts(), "hosts")):
        with open(OUT / f"{name}.json", "w", encoding="utf-8", newline="\n") as f:  # same bytes on every OS
            f.write(json.dumps(board, indent=2) + "\n")
        print(f"wrote dashboards/{name}.json ({len(board['panels'])} panels)")
