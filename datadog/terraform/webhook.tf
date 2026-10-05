# Routes Datadog notifications to the same on-call receiver as Prometheus and Zabbix (its /datadog
# endpoint understands this payload). Created only when oncall_webhook_url is set.
resource "datadog_webhook" "oncall" {
  count     = var.oncall_webhook_url == "" ? 0 : 1
  name      = "darviq-oncall"
  url       = var.oncall_webhook_url
  encode_as = "json"
  payload = jsonencode({
    alert_id   = "$ALERT_ID"
    title      = "$EVENT_TITLE"
    transition = "$ALERT_TRANSITION"
    priority   = "$ALERT_PRIORITY"
    scope      = "$ALERT_SCOPE"
    summary    = "$EVENT_MSG"
  })
}
