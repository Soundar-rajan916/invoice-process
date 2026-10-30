terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# S3 Bucket for Invoices (Originals & Rendered Pages)
resource "aws_s3_bucket" "invoices" {
  bucket        = "${var.project}-${var.environment}-invoices-data"
  force_destroy = var.environment != "prod"

  tags = {
    Name        = "${var.project}-${var.environment}-invoices"
    Project     = var.project
    Environment = var.environment
  }
}

# Block all public access (R2 / 6.1 File Safety)
resource "aws_s3_bucket_public_access_block" "invoices" {
  bucket = aws_s3_bucket.invoices.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Versioning
resource "aws_s3_bucket_versioning" "invoices" {
  bucket = aws_s3_bucket.invoices.id

  versioning_configuration {
    status = "Enabled"
  }
}

# KMS Server-Side Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "invoices" {
  bucket = aws_s3_bucket.invoices.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = var.kms_key_arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

# Lifecycle Management: Glacier Transition after 90 days, Noncurrent cleanup
resource "aws_s3_bucket_lifecycle_configuration" "invoices" {
  bucket = aws_s3_bucket.invoices.id

  rule {
    id     = "archive-old-originals"
    status = "Enabled"

    filter {
      prefix = "originals/"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }

  rule {
    id     = "expire-page-images"
    status = "Enabled"

    filter {
      prefix = "pages/"
    }

    expiration {
      days = 180
    }
  }
}

