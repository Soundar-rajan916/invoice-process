variable "project" {
  type    = string
  default = "invoiceflow"
}

variable "environment" {
  type = string
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "monthly_budget_usd" {
  type    = string
  default = "500"
}

variable "alert_email" {
  type    = string
  default = "alerts@invoiceflow.local"
}

