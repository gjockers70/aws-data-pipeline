output "lambda_function_name" {
  value = module.ingestion_lambda.function_name
}

output "lambda_function_arn" {
  value = module.ingestion_lambda.function_arn
}

output "lambda_execution_role_arn" {
  value = module.ingestion_lambda.execution_role_arn
}

output "lambda_log_group_name" {
  value = module.ingestion_lambda.log_group_name
}

output "landing_bucket_name" {
  value = module.landing_bucket.bucket_name
}
