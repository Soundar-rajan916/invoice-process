output "api_alb_dns" {
  value = module.compute.alb_dns_name
}

output "frontend_cloudfront_domain" {
  value = module.frontend.cloudfront_domain_name
}

output "invoices_bucket" {
  value = module.storage.bucket_id
}

