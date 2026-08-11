output "function_name" {
  description = "Deployed Lambda function name."
  value       = aws_lambda_function.ingestion.function_name
}

output "function_arn" {
  description = "Deployed Lambda function ARN."
  value       = aws_lambda_function.ingestion.arn
}

output "execution_role_arn" {
  description = "Least-privilege execution role ARN."
  value       = aws_iam_role.ingestion.arn
}

output "log_group_name" {
  description = "CloudWatch log group receiving structured Lambda logs."
  value       = aws_cloudwatch_log_group.ingestion.name
}
