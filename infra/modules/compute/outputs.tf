output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "alb_zone_id" {
  value = aws_lb.main.zone_id
}

output "app_security_group_id" {
  value = aws_security_group.app.id
}

output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

