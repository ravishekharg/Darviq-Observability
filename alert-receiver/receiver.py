"""The on-call end of the alert pipeline. Every monitoring tool in this repo sends its notifications
here, so one page shows what is wrong regardless of which tool noticed:

  POST /alert     Alertmanager webhook (Prometheus metric alerts and Loki log alerts)
  POST /zabbix    Zabbix webhook media type (zabbix/provision.py sets it up)
  POST /datadog   Datadog webhook integration (payload template in datadog/README.md)
  POST /splunk    Splunk webhook alert action (splunk/app/default/savedsearches.conf)

Each status change is logged as one JSON line, and the latest 50 are listed at
http://localhost:9099/. Standard library only. In production this is where Slack, email or
PagerDuty would sit; a plain webhook proves the routing end to end without accounts.
"""
import html
import json
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RECENT = deque(maxlen=50)
# Alertmanager re-sends a group's full alert list on every change, so the same alert arrives again
# and again with an unchanged status. Only record an alert when its status actually changes.
LAST_STATUS = {}
COLORS = {"critical": "#d64545", "high": "#d64545", "disaster": "#a51d1d", "warning": "#d99a1e",
          "average": "#e07a1f", "info": "#4a7fd6", "none": "#6b7280"}
SOURCE_COLORS = {"prometheus": "#e6522c", "loki": "#f2c94c", "zabbix": "#d40000", "datadog": "#632ca6",
                 "splunk": "#e20082"}


def from_alertmanager(body):
    for a in body.get("alerts", []):
        labels = a.get("labels", {})
        source = labels.get("source", "prometheus")  # Loki's log alerts are labelled source=loki
        yield (a.get("fingerprint") or json.dumps(labels, sort_keys=True), source, a.get("status"),
               labels.get("alertname"), labels.get("severity", "none"), a.get("annotations", {}).get("summary", ""))


def from_zabbix(body):
    # {EVENT.STATUS} is PROBLEM or RESOLVED; the event id ties a recovery to its problem.
    status = "resolved" if str(body.get("status", "")).upper() == "RESOLVED" else "firing"
    yield (f"zabbix-{body.get('event_id') or body.get('name')}", "zabbix", status, body.get("name"),
           str(body.get("severity", "none")).lower(), f"{body.get('host', '')}: {body.get('summary', '')}".strip(": "))


def from_datadog(body):
    # Datadog's $ALERT_TRANSITION is Triggered, Recovered, Warn, No Data...
    status = "resolved" if str(body.get("transition", "")).lower() == "recovered" else "firing"
    yield (f"datadog-{body.get('alert_id')}-{body.get('scope', '')}", "datadog", status, body.get("title"),
           str(body.get("priority") or body.get("severity") or "warning").lower(), body.get("summary", ""))


def from_splunk(body):
    # Splunk's webhook carries the search name, the search job id (sid) and the first result row,
    # where the saved search puts its own severity and summary. Splunk alerts are one-off events
    # with no "resolved" notice, so each trigger (its own sid) is recorded as firing.
    result = body.get("result") or {}
    yield (f"splunk-{body.get('sid')}-{result.get('project', '')}-{result.get('service', '')}", "splunk", "firing",
           body.get("search_name"), str(result.get("severity", "warning")).lower(), result.get("summary", ""))


PARSERS = {"/alert": from_alertmanager, "/zabbix": from_zabbix, "/datadog": from_datadog, "/splunk": from_splunk}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        parse = PARSERS.get(self.path)
        if parse is None:
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        received = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        for key, source, status, name, severity, summary in parse(body):
            if LAST_STATUS.get(key) == status:
                continue
            LAST_STATUS[key] = status
            entry = {"received": received, "source": source, "status": status, "alertname": name,
                     "severity": severity, "summary": summary}
            RECENT.appendleft(entry)
            print(json.dumps(entry), flush=True)
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        rows = "".join(
            f'<tr><td>{html.escape(a["received"])}</td>'
            f'<td><span class="src" style="border-color:{SOURCE_COLORS.get(a["source"], "#6b7280")}">'
            f'{html.escape(a["source"])}</span></td>'
            f'<td><span class="pill" style="background:{"#2f9e6b" if a["status"] == "resolved" else COLORS.get(a["severity"], "#6b7280")}">'
            f'{html.escape(a["status"] or "")}</span></td>'
            f'<td><b>{html.escape(a["alertname"] or "")}</b><br><span class="sev">{html.escape(a["severity"])}</span></td>'
            f'<td>{html.escape(a["summary"])}</td></tr>'
            for a in RECENT
        ) or '<tr><td colspan="5">No notifications yet.</td></tr>'
        page = f"""<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="10">
<title>On-call notifications</title><style>
body{{font:15px/1.5 system-ui,sans-serif;margin:32px;background:#0f1424;color:#e6e9f2}}
h1{{font-size:22px;margin:0 0 4px}} p{{color:#9aa3bf;margin:0 0 20px}}
table{{border-collapse:collapse;width:100%;background:#161c30;border-radius:10px;overflow:hidden}}
th,td{{text-align:left;padding:12px 14px;border-bottom:1px solid #252d48;vertical-align:top}}
th{{color:#9aa3bf;font-weight:600;font-size:13px;text-transform:uppercase;letter-spacing:.04em}}
.pill{{color:#fff;border-radius:999px;padding:2px 10px;font-size:13px;font-weight:600}}
.src{{border:1.5px solid;border-radius:6px;padding:1px 8px;font-size:13px;font-weight:600}}
.sev{{color:#9aa3bf;font-size:13px}}</style></head><body>
<h1>On-call notifications</h1><p>From Prometheus, Loki, Zabbix, Datadog and Splunk. Newest first, refreshes every 10 seconds.</p>
<table><tr><th>Received</th><th>Source</th><th>Status</th><th>Alert</th><th>Summary</th></tr>{rows}</table></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page.encode("utf-8"))

    def log_message(self, *args):
        pass  # one JSON line per alert change is the log; skip per-request noise


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9099), Handler).serve_forever()
