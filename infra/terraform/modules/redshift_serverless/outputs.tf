output "namespace_name" {
  value = aws_redshiftserverless_namespace.warehouse.namespace_name
}

output "workgroup_name" {
  value = aws_redshiftserverless_workgroup.warehouse.workgroup_name
}

output "workgroup_arn" {
  value = aws_redshiftserverless_workgroup.warehouse.arn
}

output "database_name" {
  value = aws_redshiftserverless_namespace.warehouse.db_name
}

output "s3_read_role_arn" {
  value = aws_iam_role.warehouse.arn
}

output "vpc_id" {
  value = aws_vpc.warehouse.id
}
