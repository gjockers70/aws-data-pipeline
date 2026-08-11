output "job_name" {
  value = aws_glue_job.world_bank.name
}

output "execution_role_arn" {
  value = aws_iam_role.job.arn
}
