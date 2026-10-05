variable "datadog_api_key" {
  description = "Datadog API key (Organization settings > API keys)."
  type        = string
  sensitive   = true
}

variable "datadog_app_key" {
  description = "Datadog application key (Organization settings > Application keys)."
  type        = string
  sensitive   = true
}

variable "datadog_api_url" {
  description = "API endpoint for your Datadog site, e.g. https://api.datadoghq.com/ or https://api.us5.datadoghq.com/."
  type        = string
  default     = "https://api.datadoghq.com/"
}

variable "oncall_webhook_url" {
  description = "Where Datadog posts alerts. Must be reachable from the internet (the local on-call receiver is not, so use a tunnel or your real paging endpoint). Empty = no webhook."
  type        = string
  default     = ""
}

variable "synthetics_locations" {
  description = "Datadog-managed locations that test darviq.com from outside."
  type        = list(string)
  default     = ["aws:ap-south-1", "aws:eu-west-1"]
}
