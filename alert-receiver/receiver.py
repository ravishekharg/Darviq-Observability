"""The on-call end of the alert pipeline: Alertmanager posts notifications here (webhook), each is
logged as one JSON line, and the latest 50 are listed at http://localhost:9099/.

Standard library only. In production this is where Slack, email or PagerDuty would sit; keeping a
plain webhook here proves the routing, grouping and resolve messages end to end without accounts.
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
COLORS = {"critical": "#d64545", "warning": "#d99a1e", "none": "#6b7280"}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/alert":
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        received = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        for alert in body.get("alerts", []):
            key = alert.get("fingerprint") or json.dumps(alert.get("labels", {}), sort_keys=True)
            if LAST_STATUS.get(key) == alert.get("status"):
                continue
            LAST_STATUS[key] = alert.get("status")
            entry = {
                "received": received,
                "status": alert.get("status"),
                "alertname": alert.get("labels", {}).get("alertname"),
                "severity": alert.get("labels", {}).get("severity", "none"),
                "summary": alert.get("annotations", {}).get("summary", ""),
                "labels": alert.get("labels", {}),
            }
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
            f'<td><span class="pill" style="background:{"#2f9e6b" if a["status"] == "resolved" else COLORS.get(a["severity"], "#6b7280")}">'
            f'{html.escape(a["status"] or "")}</span></td>'
            f'<td><b>{html.escape(a["alertname"] or "")}</b><br><span class="sev">{html.escape(a["severity"])}</span></td>'
            f'<td>{html.escape(a["summary"])}</td></tr>'
            for a in RECENT
        ) or '<tr><td colspan="4">No notifications yet.</td></tr>'
        page = f"""<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="refresh" content="10">
<title>On-call notifications</title><style>
body{{font:15px/1.5 system-ui,sans-serif;margin:32px;background:#0f1424;color:#e6e9f2}}
h1{{font-size:22px;margin:0 0 4px}} p{{color:#9aa3bf;margin:0 0 20px}}
table{{border-collapse:collapse;width:100%;background:#161c30;border-radius:10px;overflow:hidden}}
th,td{{text-align:left;padding:12px 14px;border-bottom:1px solid #252d48;vertical-align:top}}
th{{color:#9aa3bf;font-weight:600;font-size:13px;text-transform:uppercase;letter-spacing:.04em}}
.pill{{color:#fff;border-radius:999px;padding:2px 10px;font-size:13px;font-weight:600}}
.sev{{color:#9aa3bf;font-size:13px}}</style></head><body>
<h1>On-call notifications</h1><p>Delivered by Alertmanager to this webhook. Newest first, refreshes every 10 seconds.</p>
<table><tr><th>Received</th><th>Status</th><th>Alert</th><th>Summary</th></tr>{rows}</table></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page.encode("utf-8"))

    def log_message(self, *args):
        pass  # one JSON line per alert is the log; skip per-request noise


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9099), Handler).serve_forever()
