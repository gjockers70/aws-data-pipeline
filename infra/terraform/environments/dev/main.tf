module "ingestion_lambda" {
  source = "../../modules/lambda"

  function_name      = "aws-data-pipeline-dev-ingestion"
  artifact_path      = var.lambda_artifact_path
  environment        = "dev"
  log_retention_days = 14

  tags = {
    Component = "ingestion"
  }
}
