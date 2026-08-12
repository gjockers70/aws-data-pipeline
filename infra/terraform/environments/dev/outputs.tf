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

output "glue_job_name" {
  value = module.world_bank_glue.job_name
}

output "glue_execution_role_arn" {
  value = module.world_bank_glue.execution_role_arn
}

output "redshift_namespace_name" {
  value = try(module.redshift_serverless[0].namespace_name, null)
}

output "redshift_workgroup_name" {
  value = try(module.redshift_serverless[0].workgroup_name, null)
}

output "redshift_database_name" {
  value = try(module.redshift_serverless[0].database_name, null)
}

output "redshift_s3_read_role_arn" {
  value = try(module.redshift_serverless[0].s3_read_role_arn, null)
}
