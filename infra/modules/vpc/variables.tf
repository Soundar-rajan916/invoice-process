variable "project" {
  type        = string
  description = "Project name"
  default     = "invoiceflow"
}

variable "environment" {
  type        = string
  description = "Deployment environment (staging, prod)"
}

variable "aws_region" {
  type        = string
  description = "AWS deployment region"
  default     = "ap-south-1"
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for VPC"
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  type        = list(string)
  description = "Two availability zones for high availability"
  default     = ["ap-south-1a", "ap-south-1b"]
}

