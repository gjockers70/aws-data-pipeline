data "aws_caller_identity" "current" {}

module "landing_bucket" {
  source = "../../modules/s3_landing"

  bucket_name   = "aws-data-pipeline-dev-${data.aws_caller_identity.current.account_id}-${var.aws_region}-landing"
  force_destroy = true

  tags = {
    Component = "landing"
  }
}

module "ingestion_lambda" {
  source = "../../modules/lambda"

  function_name       = "aws-data-pipeline-dev-ingestion"
  artifact_path       = var.lambda_artifact_path
  environment         = "dev"
  landing_bucket_arn  = module.landing_bucket.bucket_arn
  landing_bucket_name = module.landing_bucket.bucket_name
  log_retention_days  = 14

  tags = {
    Component = "ingestion"
  }
}

module "world_bank_glue" {
  source = "../../modules/glue"

  job_name              = "aws-data-pipeline-dev-world-bank-transform"
  environment           = "dev"
  bucket_name           = module.landing_bucket.bucket_name
  bucket_arn            = module.landing_bucket.bucket_arn
  script_artifact_path  = var.glue_script_artifact_path
  library_artifact_path = var.glue_library_artifact_path
  log_retention_days    = 14

  tags = {
    Component   = "transformation"
    Environment = "dev"
  }
}
