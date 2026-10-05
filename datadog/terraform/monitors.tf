# The same alerts as prometheus/rules/alerts.yml, expressed as Datadog monitors, so either tool can
# be the one that pages. Notifications go to the on-call webhook when one is configured.

locals {
  notify = var.oncall_webhook_url == "" ? "" : "@webhook-darviq-oncall"
  tags   = ["team:darviq", "managed-by:terraform"]
}

resource "datadog_monitor" "service_down" {
  name    = "[Darviq] {{instance.name}} is down"
  type    = "service check"
  query   = "\"http.can_connect\".over(\"*\").by(\"instance\").last(3).count_by_status()"
  message = "The HTTP check has failed 3 times in a row. Runbook: docs/runbooks.md#probefailed ${local.notify}"
  monitor_thresholds {
    critical = 2
    warning  = 1
    ok       = 1
  }
  notify_no_data    = true
  no_data_timeframe = 5
  tags              = local.tags
}

resource "datadog_monitor" "high_error_rate" {
  name    = "[Darviq] {{service.name}} is failing {{value}}% of requests"
  type    = "query alert"
  query   = "sum(last_5m):100 * sum:darviq.http.requests.count{status:5*} by {service}.as_count() / sum:darviq.http.requests.count{*} by {service}.as_count() > 5"
  message = "Over 5% of requests returned 5xx for 5 minutes. Runbook: docs/runbooks.md#higherrorrate ${local.notify}"
  monitor_thresholds {
    critical = 5
    warning  = 2
  }
  require_full_window = false
  tags                = local.tags
}

resource "datadog_monitor" "slow_responses" {
  name    = "[Darviq] {{instance.name}} takes over 2 s to respond"
  type    = "query alert"
  query   = "avg(last_5m):avg:network.http.response_time{*} by {instance} > 2"
  message = "Response time has averaged over 2 s for 5 minutes. Runbook: docs/runbooks.md#slowresponse ${local.notify}"
  monitor_thresholds {
    critical = 2
    warning  = 1
  }
  tags = local.tags
}

resource "datadog_monitor" "disk_will_fill" {
  name    = "[Darviq] {{device.name}} on {{host.name}} will fill within 24 hours"
  type    = "query alert"
  query   = "max(next_1d):forecast(max:system.disk.in_use{*} by {host,device}, 'linear', 1, interval='60m', history='6h') >= 1"
  message = "At the current rate this disk is full within a day. Runbook: docs/runbooks.md#diskwillfillin24h ${local.notify}"
  monitor_thresholds {
    critical = 1
    warning  = 0.95
  }
  tags = local.tags
}

resource "datadog_monitor" "container_crash_restarts" {
  name    = "[Darviq] container {{container_name.name}} is crash-restarting"
  type    = "query alert"
  query   = "sum(last_15m):sum:docker.containers.restarts{*} by {container_name}.as_count() > 0"
  message = "Docker restarted this container after a crash. Runbook: docs/runbooks.md#containerrestarting ${local.notify}"
  monitor_thresholds {
    critical = 0
  }
  tags = local.tags
}

resource "datadog_monitor" "error_log_spike" {
  name    = "[Darviq] {{service.name}} logged {{value}} errors in 5 minutes"
  type    = "log alert"
  query   = "logs(\"status:error\").index(\"*\").rollup(\"count\").by(\"service\").last(\"5m\") > 20"
  message = "Error-level log lines are spiking. Runbook: docs/runbooks.md#errorlogspike ${local.notify}"
  monitor_thresholds {
    critical = 20
  }
  tags = local.tags
}
