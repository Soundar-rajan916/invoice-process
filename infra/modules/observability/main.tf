terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# SNS Topic for Alarms (Email / Slack Integration)
resource "aws_sns_topic" "alerts" {
  name = "${var.project}-${var.environment}-alerts"

  tags = {
    Name = "${var.project}-${var.environment}-alerts"
  }
}

# CloudWatch Log Groups with Retention
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project}-${var.environment}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "worker_extract" {
  name              = "/ecs/${var.project}-${var.environment}-worker-extract"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "worker_general" {
  name              = "/ecs/${var.project}-${var.environment}-worker-general"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "beat" {
  name              = "/ecs/${var.project}-${var.environment}-beat"
  retention_in_days = var.log_retention_days
}

# Alarm: Oldest Unreviewed Invoice Age > 4 Hours
resource "aws_cloudwatch_metric_alarm" "queue_age" {
  alarm_name          = "${var.project}-${var.environment}-oldest-invoice-age"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "OldestUnreviewedAgeSeconds"
  namespace           = "InvoiceFlow/Operations"
  period              = 300
  statistic           = "Maximum"
  threshold           = 14400 # 4 hours
  alarm_description   = "Invoice review queue backlog age exceeds 4 hours SLA"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Alarm: Circuit Breaker Open > 10 Minutes
resource "aws_cloudwatch_metric_alarm" "circuit_breaker_open" {
  alarm_name          = "${var.project}-${var.environment}-circuit-breaker-open"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 2
  metric_name         = "CircuitBreakerStateOpen"
  namespace           = "InvoiceFlow/Resilience"
  period              = 300
  statistic           = "Maximum"
  threshold           = 1
  alarm_description   = "Circuit breaker is OPEN for upstream LLM or downstream accounting"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# Alarm: Dead Letter Count Above Zero
resource "aws_cloudwatch_metric_alarm" "dead_letters" {
  alarm_name          = "${var.project}-${var.environment}-dead-letters-present"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "DeadLetterCount"
  namespace           = "InvoiceFlow/Reliability"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "Invoices present in PUSH_FAILED or FAILED dead letter states"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# AWS Budget Alarm ($500/mo cap)
resource "aws_budgets_budget" "monthly" {
  name              = "${var.project}-${var.environment}-monthly-budget"
  budget_type       = "COST"
  limit_amount      = var.monthly_budget_usd
  limit_unit        = "USD"
  time_unit         = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}

