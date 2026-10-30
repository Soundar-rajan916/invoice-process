output "sns_alerts_arn" {
  value = aws_sns_topic.alerts.arn
}

output "api_log_group_name" {
  value = aws_cloudwatch_log_group.api.name
}

