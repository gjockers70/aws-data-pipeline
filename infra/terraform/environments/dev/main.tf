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
