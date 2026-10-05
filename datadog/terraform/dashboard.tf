# A Datadog dashboard mirroring Grafana's Platform overview.
resource "datadog_dashboard_json" "platform" {
  dashboard = jsonencode({
    title       = "Darviq platform overview"
    description = "Managed by Terraform in Darviq-Observability. Mirrors the Grafana Platform overview."
    layout_type = "ordered"
    widgets = [
      {
        definition = {
          type     = "check_status"
          title    = "Health checks"
          check    = "http.can_connect"
          grouping = "cluster"
          group_by = []
          tags     = ["*"]
        }
      },
      {
        definition = {
          type     = "timeseries"
          title    = "Requests per second by service"
          requests = [{ q = "sum:darviq.http.requests.count{*} by {service}.as_rate()", display_type = "bars" }]
        }
      },
      {
        definition = {
          type  = "timeseries"
          title = "Error ratio by service (%)"
          requests = [{
            q            = "100 * sum:darviq.http.requests.count{status:5*} by {service}.as_count() / sum:darviq.http.requests.count{*} by {service}.as_count()"
            display_type = "line"
          }]
        }
      },
      {
        definition = {
          type     = "timeseries"
          title    = "Response time of HTTP checks"
          requests = [{ q = "avg:network.http.response_time{*} by {instance}", display_type = "line" }]
        }
      },
      {
        definition = {
          type     = "toplist"
          title    = "Container memory (top 10)"
          requests = [{ q = "top(avg:docker.mem.rss{*} by {container_name}, 10, 'mean', 'desc')" }]
        }
      },
      {
        definition = {
          type    = "log_stream"
          title   = "Error logs"
          query   = "status:error"
          columns = ["host", "service"]
          indexes = []
        }
      }
    ]
  })
}
