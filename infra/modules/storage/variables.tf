variable "project" {
  type    = string
  default = "invoiceflow"
}

variable "environment" {
  type = string
}

variable "kms_key_arn" {
  type        = string
  description = "KMS Key ARN for S3 server-side encryption"
}

