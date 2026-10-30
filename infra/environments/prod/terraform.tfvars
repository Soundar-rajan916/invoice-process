project             = "invoiceflow"
aws_region          = "ap-south-1"
api_image           = "123456789012.dkr.ecr.ap-south-1.amazonaws.com/invoiceflow-api:v1.0.0"
acm_certificate_arn = "arn:aws:acm:ap-south-1:123456789012:certificate/prod-cert-id"
db_password         = "ProdSecretInjectedFromSecretsManagerDoNotCommit"
redis_auth_token    = "ProdRedisToken32CharsMinLenInjectedFromSecrets"
alert_email         = "devops-prod@invoiceflow.local"

