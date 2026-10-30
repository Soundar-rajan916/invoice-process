terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "invoiceflow-terraform-state-prod"
    key            = "prod/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "invoiceflow-terraform-locks-prod"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "invoiceflow"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}

module "vpc" {
  source      = "../../modules/vpc"
  project     = var.project
  environment = "prod"
  aws_region  = var.aws_region
  vpc_cidr    = "10.20.0.0/16"
}

module "security" {
  source      = "../../modules/security"
  project     = var.project
  environment = "prod"
}

module "storage" {
  source      = "../../modules/storage"
  project     = var.project
  environment = "prod"
  kms_key_arn = module.security.kms_key_arn
}

module "database" {
  source                = "../../modules/database"
  project               = var.project
  environment           = "prod"
  vpc_id                = module.vpc.vpc_id
  subnet_ids            = module.vpc.private_db_subnet_ids
  app_security_group_id = module.compute.app_security_group_id
  kms_key_arn           = module.security.kms_key_arn
  instance_class        = "db.r6g.large"
  multi_az              = true # Multi-AZ High Availability for production
  backup_retention_days = 30
  db_password           = var.db_password
}

module "cache" {
  source                = "../../modules/cache"
  project               = var.project
  environment           = "prod"
  vpc_id                = module.vpc.vpc_id
  subnet_ids            = module.vpc.private_db_subnet_ids
  app_security_group_id = module.compute.app_security_group_id
  kms_key_arn           = module.security.kms_key_arn
  node_type             = "cache.m6g.large"
  num_cache_clusters    = 2 # Multi-node Redis replication with automatic failover
  auth_token            = var.redis_auth_token
}

module "compute" {
  source                 = "../../modules/compute"
  project                = var.project
  environment            = "prod"
  aws_region             = var.aws_region
  vpc_id                 = module.vpc.vpc_id
  public_subnet_ids      = module.vpc.public_subnet_ids
  private_app_subnet_ids = module.vpc.private_app_subnet_ids
  acm_certificate_arn    = var.acm_certificate_arn
  waf_acl_arn            = module.security.waf_acl_arn
  ecs_execution_role_arn = module.security.ecs_execution_role_arn
  ecs_task_role_arn      = module.security.ecs_task_role_arn
  api_image              = var.api_image
  database_url           = "postgresql+asyncpg://invoiceflow_admin:${var.db_password}@${module.database.endpoint}/invoiceflow"
  redis_url              = "rediss://:${var.redis_auth_token}@${module.cache.primary_endpoint_address}:${module.cache.port}/0"
  s3_bucket              = module.storage.bucket_id
  api_desired_count      = 4
  api_min_count          = 4
  api_max_count          = 16
  worker_desired_count   = 4
}

module "frontend" {
  source      = "../../modules/frontend"
  project     = var.project
  environment = "prod"
}

module "observability" {
  source             = "../../modules/observability"
  project            = var.project
  environment        = "prod"
  log_retention_days = 90
  monthly_budget_usd = "1000"
  alert_email        = var.alert_email
}

