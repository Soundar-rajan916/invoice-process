project             = "invoiceflow"
aws_region          = "ap-south-1"
api_image           = "123456789012.dkr.ecr.ap-south-1.amazonaws.com/invoiceflow-api:staging"
acm_certificate_arn = "arn:aws:acm:ap-south-1:123456789012:certificate/staging-cert-id"
db_password         = "StagingChangeMeInSecretsManager123!"
redis_auth_token    = "StagingRedisToken32CharsMinLen12!"
alert_email         = "devops-staging@invoiceflow.local"

