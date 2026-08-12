data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

locals {
  artifact_prefix = "artifacts/glue/world_bank"
  log_group_names = toset([
    "/aws-glue/jobs/error",
    "/aws-glue/jobs/output",
    "/aws-glue/jobs/logs-v2",
  ])
}

resource "aws_s3_object" "job_script" {
  bucket                 = var.bucket_name
  key                    = "${local.artifact_prefix}/world_bank_job.py"
  source                 = var.script_artifact_path
  etag                   = filemd5(var.script_artifact_path)
  server_side_encryption = "AES256"
}

resource "aws_s3_object" "transformation_library" {
  bucket                 = var.bucket_name
  key                    = "${local.artifact_prefix}/transformations.zip"
  source                 = var.library_artifact_path
  etag                   = filemd5(var.library_artifact_path)
  server_side_encryption = "AES256"
}

resource "aws_cloudwatch_log_group" "glue" {
  for_each          = local.log_group_names
  name              = each.value
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "job" {
  name               = "${var.job_name}-execution"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  tags               = var.tags
}

data "aws_iam_policy_document" "s3_access" {
  statement {
    sid       = "ReadBucketLocation"
    effect    = "Allow"
    actions   = ["s3:GetBucketLocation"]
    resources = [var.bucket_arn]
  }

  statement {
    sid       = "ListPipelineBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.bucket_arn]
  }

  statement {
    sid     = "ReadSourceAndArtifacts"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${var.bucket_arn}/landing/world_bank/*",
      "${var.bucket_arn}/artifacts/glue/world_bank/*",
    ]
  }

  statement {
    sid    = "WriteTransformationResults"
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:PutObject",
    ]
    resources = [
      "${var.bucket_arn}/processed/world_bank/*",
      "${var.bucket_arn}/quality/world_bank/*",
      "${var.bucket_arn}/rejected/world_bank/*",
      "${var.bucket_arn}/warehouse/world_bank/*",
    ]
  }
}

resource "aws_iam_role_policy" "s3_access" {
  name   = "world-bank-object-access"
  role   = aws_iam_role.job.id
  policy = data.aws_iam_policy_document.s3_access.json
}

data "aws_iam_policy_document" "logging" {
  statement {
    sid    = "WriteGlueLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      for group in aws_cloudwatch_log_group.glue : "${group.arn}:*"
    ]
  }
}

resource "aws_iam_role_policy" "logging" {
  name   = "write-glue-logs"
  role   = aws_iam_role.job.id
  policy = data.aws_iam_policy_document.logging.json
}

resource "aws_glue_job" "world_bank" {
  name              = var.job_name
  description       = "Validates and normalizes World Bank JSON into partitioned Parquet."
  role_arn          = aws_iam_role.job.arn
  glue_version      = "5.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  execution_class   = "STANDARD"
  max_retries       = 0
  timeout           = 10

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.bucket_name}/${aws_s3_object.job_script.key}"
  }

  default_arguments = {
    "--ENVIRONMENT"                      = var.environment
    "--SOURCE_PATH"                      = "s3://${var.bucket_name}/landing/world_bank/"
    "--PROCESSED_BASE_PATH"              = "s3://${var.bucket_name}/processed/world_bank/"
    "--QUALITY_BASE_PATH"                = "s3://${var.bucket_name}/quality/world_bank/"
    "--REJECTED_BASE_PATH"               = "s3://${var.bucket_name}/rejected/world_bank/"
    "--WAREHOUSE_BASE_PATH"              = "s3://${var.bucket_name}/warehouse/world_bank/"
    "--extra-py-files"                   = "s3://${var.bucket_name}/${aws_s3_object.transformation_library.key}"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--enable-observability-metrics"     = "true"
    "--enable-spark-ui"                  = "false"
    "--job-language"                     = "python"
  }

  depends_on = [
    aws_iam_role_policy.logging,
    aws_iam_role_policy.s3_access,
  ]

  tags = var.tags
}
