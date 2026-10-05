"""Configures Zabbix as code through its JSON-RPC API, so a fresh Zabbix is in a known state after
one command and nothing depends on clicks in the UI. Safe to re-run: everything is found by name
and updated, not duplicated.

    python zabbix/provision.py            (after: docker compose --profile zabbix up -d)

What it sets up:
  - host "docker-host": Zabbix agent 2 on the Docker host, with Zabbix's own "Linux by Zabbix
    agent" and "Docker by Zabbix agent 2" templates (CPU, memory, disks, every container)
  - host "websites": web scenarios for the public site and each app's health endpoint, each with
    a "down" trigger (high) and a "slow" trigger (warning)
  - a webhook media type and action sending problems and recoveries to the on-call receiver
  - a "Darviq overview" dashboard

Standard library only. Env: ZABBIX_URL (default http://localhost:8081), ZABBIX_USER / ZABBIX_PASSWORD
(default Admin / zabbix, Zabbix's out-of-the-box login: change it for anything beyond a laptop).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

URL = os.environ.get("ZABBIX_URL", "http://localhost:8081").rstrip("/") + "/api_jsonrpc.php"
USER = os.environ.get("ZABBIX_USER", "Admin")
PASSWORD = os.environ.get("ZABBIX_PASSWORD", "zabbix")
RECEIVER = "http://alert-receiver:9099/zabbix"   # reached from the Zabbix server's network

# name -> URL. The Zabbix server resolves host.docker.internal to the Docker host.
WEBSITES = {
    "darviq.com home": "https://darviq.com/",
    "darviq.com work": "https://darviq.com/products.html",
    "Darviq Health API": "http://host.docker.internal:8090/api/health",
    "Darviq Nyaya API": "http://host.docker.internal:8080/api/health",
}

_token = None


def api(method, params=None):
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}).encode()
    headers = {"Content-Type": "application/json-rpc"}
    if _token and method not in ("apiinfo.version", "user.login"):
        headers["Authorization"] = f"Bearer {_token}"
    # linking the large standard templates to a host can take a minute on a fresh database
    with urllib.request.urlopen(urllib.request.Request(URL, body, headers), timeout=300) as resp:
        reply = json.loads(resp.read())
    if "error" in reply:
        raise RuntimeError(f"{method}: {reply['error'].get('data') or reply['error'].get('message')}")
    return reply["result"]


def wait_for_zabbix(seconds=300):
    deadline = time.time() + seconds
    while True:
        try:
            print("Zabbix API", api("apiinfo.version"))
            return
        except (OSError, RuntimeError, json.JSONDecodeError):  # incl. timeouts while Zabbix creates its database
            if time.time() > deadline:
                sys.exit(f"Zabbix API not reachable at {URL}")
            time.sleep(5)


def one(method, filter_):
    found = api(f"{method}.get", {"filter": filter_, "output": "extend"})
    return found[0] if found else None


def upsert(kind, id_field, name_field, name, create, update=None):
    """Find by name; update it (if update given) or create it. Returns the id."""
    existing = one(kind, {name_field: name})
    if existing:
        if update is not None:
            api(f"{kind}.update", {id_field: existing[id_field], **update})
        return existing[id_field]
    return api(f"{kind}.create", create)[f"{id_field}s"][0]


def template_ids(*names):
    found = api("template.get", {"filter": {"host": list(names)}, "output": ["templateid", "host"]})
    missing = set(names) - {t["host"] for t in found}
    if missing:
        sys.exit(f"Templates not found in this Zabbix: {missing}")
    return [{"templateid": t["templateid"]} for t in found]


def provision():
    global _token
    wait_for_zabbix()
    _token = api("user.login", {"username": USER, "password": PASSWORD})

    group = upsert("hostgroup", "groupid", "name", "Darviq", {"name": "Darviq"})

    # Zabbix's own "Zabbix server" host expects an agent inside the server container; there isn't
    # one (the agent watches the Docker host instead), so disable it rather than leave it red.
    default = one("host", {"host": "Zabbix server"})
    if default and default["status"] == "0":
        api("host.update", {"hostid": default["hostid"], "status": 1})

    templates = template_ids("Linux by Zabbix agent", "Docker by Zabbix agent 2")
    agent_if = {"type": 1, "main": 1, "useip": 0, "ip": "", "dns": "zabbix-agent2", "port": "10050"}
    host = one("host", {"host": "docker-host"})
    if host:
        api("host.update", {"hostid": host["hostid"], "groups": [{"groupid": group}], "templates": templates})
        hostid = host["hostid"]
    else:
        hostid = api("host.create", {"host": "docker-host", "groups": [{"groupid": group}],
                                     "interfaces": [agent_if], "templates": templates})["hostids"][0]
    print("host docker-host", hostid)

    sites = upsert("host", "hostid", "host", "websites", {"host": "websites", "groups": [{"groupid": group}]})
    for name, url in WEBSITES.items():
        step = {"name": name, "url": url, "status_codes": "200", "no": 1, "follow_redirects": 1, "timeout": "15s"}
        upsert("httptest", "httptestid", "name", name,
               {"name": name, "hostid": sites, "delay": "1m", "retries": 2, "steps": [step]},
               {"delay": "1m", "retries": 2, "steps": [step]})
        for description, expression, priority in (
            (f"{name} is down", f"last(/websites/web.test.fail[{name}])<>0", 4),
            # slow only while it is up: a failing check is often slow too (a proxy waiting for a dead
            # upstream), and "down" already covers that; found when both fired for one outage
            (f"{name} is slow", f"avg(/websites/web.test.time[{name},{name},resp],5m)>2"
                                f" and last(/websites/web.test.fail[{name}])=0", 2),
        ):
            upsert("trigger", "triggerid", "description", description,
                   {"description": description, "expression": expression, "priority": priority},
                   {"expression": expression, "priority": priority})
    print("web scenarios", len(WEBSITES))

    script = """var p = JSON.parse(value), req = new HttpRequest();
req.addHeader('Content-Type: application/json');
req.post(p.url, JSON.stringify({status: p.status, event_id: p.event_id, name: p.name,
  severity: p.severity, host: p.host, summary: p.summary}));
if (req.getStatus() !== 200) { throw 'on-call receiver answered HTTP ' + req.getStatus(); }
return 'OK';"""
    params = [{"name": "url", "value": RECEIVER}, {"name": "status", "value": "{EVENT.STATUS}"},
              {"name": "event_id", "value": "{EVENT.ID}"}, {"name": "name", "value": "{EVENT.NAME}"},
              {"name": "severity", "value": "{EVENT.SEVERITY}"}, {"name": "host", "value": "{HOST.NAME}"},
              {"name": "summary", "value": "{EVENT.OPDATA}"}]
    templates_msg = [{"eventsource": 0, "recovery": r, "subject": "{EVENT.NAME}", "message": "{EVENT.NAME}"}
                     for r in (0, 1)]
    media = {"name": "Darviq on-call", "type": 4, "script": script, "parameters": params,
             "message_templates": templates_msg, "status": 0}
    mediatypeid = upsert("mediatype", "mediatypeid", "name", "Darviq on-call", media,
                         {k: v for k, v in media.items() if k != "name"})

    admin = api("user.get", {"filter": {"username": USER}, "output": ["userid"]})[0]["userid"]
    api("user.update", {"userid": admin, "medias": [
        {"mediatypeid": mediatypeid, "sendto": "oncall", "active": 0, "severity": 63, "period": "1-7,00:00-24:00"}]})

    action = {
        "name": "Darviq on-call", "eventsource": 0, "status": 0, "esc_period": "1h",
        "filter": {"evaltype": 0, "conditions": [{"conditiontype": 4, "operator": 5, "value": "2"}]},  # warning and up
        "operations": [{"operationtype": 0, "opmessage": {"default_msg": 1, "mediatypeid": mediatypeid},
                        "opmessage_usr": [{"userid": admin}]}],
        "recovery_operations": [{"operationtype": 11, "opmessage": {"default_msg": 1}}],
    }
    upsert("action", "actionid", "name", "Darviq on-call", action, {k: v for k, v in action.items() if k not in ("name", "eventsource")})
    print("on-call media type and action")

    dashboard(hostid)
    print("Done. Open", URL.replace("/api_jsonrpc.php", ""))


def dashboard(hostid):
    def field(type_, name, value):
        return {"type": type_, "name": name, "value": value}

    def graph(x, y, w, h, title, items):
        return {"type": "svggraph", "name": title, "x": x, "y": y, "width": w, "height": h, "fields": [
            field(1, "ds.0.hosts.0", items[0]), *[field(1, f"ds.0.items.{i}", it) for i, it in enumerate(items[1:])],
            field(0, "ds.0.transparency", 2), field(0, "ds.0.fill", 3), field(0, "legend", 1)]}

    widgets = [
        {"type": "problemsbysv", "name": "Problems by severity", "x": 0, "y": 0, "width": 36, "height": 3, "fields": []},
        {"type": "hostavail", "name": "Host availability", "x": 36, "y": 0, "width": 36, "height": 3, "fields": []},
        {"type": "problems", "name": "Current problems", "x": 0, "y": 3, "width": 36, "height": 6,
         "fields": [field(0, "show_tags", 1)]},
        {"type": "web", "name": "Web monitoring", "x": 36, "y": 3, "width": 36, "height": 6, "fields": []},
        graph(0, 9, 36, 5, "Docker host CPU utilization", ["docker-host", "CPU utilization"]),
        graph(36, 9, 36, 5, "Docker host memory utilization", ["docker-host", "Memory utilization"]),
        graph(0, 14, 72, 5, "Website response time", ["websites", "Avg response time for step \"*\" of scenario \"*\"."]),
    ]
    board = {"name": "Darviq overview", "display_period": 30, "auto_start": 1, "pages": [{"widgets": widgets}]}
    existing = one("dashboard", {"name": "Darviq overview"})
    if existing:
        api("dashboard.update", {"dashboardid": existing["dashboardid"], "pages": board["pages"]})
    else:
        api("dashboard.create", board)
    print("dashboard Darviq overview")


if __name__ == "__main__":
    provision()
