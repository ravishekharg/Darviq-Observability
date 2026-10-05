"""Per-container metrics straight from the Docker Engine API, under cAdvisor's metric names (so the
same alert rules and dashboards work with either).

Why not just cAdvisor: on Docker Desktop with the containerd image store, cAdvisor (0.49-0.52)
cannot map containers to their layers and reports only the VM as a whole. The Engine API knows
every container on any Docker, so this works on a laptop and on a Linux server alike.

Standard library only. Talks to /var/run/docker.sock (mounted read-only); refreshes every 15 s in
the background so a scrape never waits on Docker.
"""
import http.client
import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SOCKET = "/var/run/docker.sock"
REFRESH_SECONDS = 15
_latest = "# no data yet\n"


class DockerSocket(http.client.HTTPConnection):
    def __init__(self):
        super().__init__("localhost", timeout=20)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(SOCKET)


def api(path):
    conn = DockerSocket()
    try:
        conn.request("GET", path)
        return json.loads(conn.getresponse().read())
    finally:
        conn.close()


def started_at(iso):
    # Docker gives nanosecond precision ("2026-10-05T09:43:51.123456789Z"); Python parses microseconds
    head, _, frac = iso.rstrip("Z").partition(".")
    return datetime.fromisoformat(head + "+00:00").timestamp() + float("0." + (frac or "0")[:6])


def container_sample(c):
    cid, name = c["Id"], c["Names"][0].lstrip("/")
    stats = api(f"/containers/{cid}/stats?stream=false&one-shot=true")
    info = api(f"/containers/{cid}/json")
    mem = stats.get("memory_stats", {})
    inactive = mem.get("stats", {}).get("inactive_file", mem.get("stats", {}).get("total_inactive_file", 0))
    nets = stats.get("networks", {}) or {}
    return {
        "name": name,
        "image": c.get("Image", ""),
        "cpu": stats.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0) / 1e9,
        "mem": max(0, mem.get("usage", 0) - inactive),
        "mem_limit": mem.get("limit", 0),
        "rx": sum(n.get("rx_bytes", 0) for n in nets.values()),
        "tx": sum(n.get("tx_bytes", 0) for n in nets.values()),
        "start": started_at(info["State"]["StartedAt"]),
        "restarts": info.get("RestartCount", 0),
    }


def esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"')


def render(samples, took):
    out = []
    def metric(name, kind, help_, key):
        out.append(f"# HELP {name} {help_}\n# TYPE {name} {kind}")
        for s in samples:
            out.append(f'{name}{{name="{esc(s["name"])}",image="{esc(s["image"])}"}} {s[key]}')
    metric("container_cpu_usage_seconds_total", "counter", "CPU time consumed, seconds.", "cpu")
    metric("container_memory_working_set_bytes", "gauge", "Memory in use, excluding reclaimable page cache.", "mem")
    metric("container_spec_memory_limit_bytes", "gauge", "Memory limit (host total when unlimited).", "mem_limit")
    metric("container_network_receive_bytes_total", "counter", "Bytes received.", "rx")
    metric("container_network_transmit_bytes_total", "counter", "Bytes sent.", "tx")
    metric("container_start_time_seconds", "gauge", "When the container last started, unix seconds.", "start")
    metric("container_restart_count", "gauge", "Restarts by Docker's restart policy.", "restarts")
    now = time.time()
    for s in samples:
        s["seen"] = now
    metric("container_last_seen", "gauge", "Last time the container was seen running, unix seconds.", "seen")
    out.append(f"# TYPE docker_exporter_refresh_seconds gauge\ndocker_exporter_refresh_seconds {took:.3f}")
    return "\n".join(out) + "\n"


def refresh_forever():
    global _latest
    pool = ThreadPoolExecutor(max_workers=16)
    while True:
        start = time.time()
        try:
            containers = api("/containers/json")
            samples = [s for s in pool.map(lambda c: _safe(container_sample, c), containers) if s]
            _latest = render(samples, time.time() - start)
        except Exception as e:  # Docker restarting, socket missing: keep serving the last good data
            print(f"refresh failed: {e}", flush=True)
        time.sleep(max(1, REFRESH_SECONDS - (time.time() - start)))


def _safe(fn, c):
    try:
        return fn(c)
    except Exception:
        return None  # a container that stopped mid-refresh


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = _latest.encode()
        self.send_response(200 if self.path == "/metrics" else 404)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(body if self.path == "/metrics" else b"see /metrics")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    threading.Thread(target=refresh_forever, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 9417), Handler).serve_forever()
