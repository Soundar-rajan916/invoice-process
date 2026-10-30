variable "project" {
  type    = string
  default = "invoiceflow"
}

variable "aws_region" {
  type    = string
  default = "ap-south-1"
}

variable "api_image" {
  type        = string
  description = "ECR image URI for API and workers"
}

variable "acm_certificate_arn" {
  type = string
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "redis_auth_token" {
  type      = string
  sensitive = true
}

variable "alert_email" {
  type    = string
  default = "prod-alerts@invoiceflow.local"
}

