# Outside-in checks of the public site from Datadog's own locations (Mumbai and Ireland by
# default): availability, response time and TLS certificate validity.
resource "datadog_synthetics_test" "website" {
  for_each = {
    home = "https://darviq.com/"
    work = "https://darviq.com/products.html"
  }

  name      = "darviq.com ${each.key}"
  type      = "api"
  subtype   = "http"
  status    = "live"
  locations = var.synthetics_locations
  message   = "darviq.com ${each.key} is failing from outside. ${local.notify}"
  tags      = local.tags

  request_definition {
    method = "GET"
    url    = each.value
  }

  assertion {
    type     = "statusCode"
    operator = "is"
    target   = "200"
  }
  assertion {
    type     = "responseTime"
    operator = "lessThan"
    target   = "2000"
  }
  assertion {
    type     = "certificate"
    operator = "isInMoreThan"
    target   = "14"
  }

  options_list {
    tick_every = 300
    retry {
      count    = 1
      interval = 1000
    }
    monitor_options {
      renotify_interval = 120
    }
  }
}
