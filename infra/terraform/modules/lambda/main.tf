data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ingestion" {
  name               = "${var.function_name}-execution"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = var.tags
}

resource "aws_cloudwatch_log_group" "ingestion" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

data "aws_iam_policy_document" "lambda_logs" {
  statement {
    sid    = "WriteFunctionLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["${aws_cloudwatch_log_group.ingestion.arn}:*"]
  }
}

resource "aws_iam_role_policy" "lambda_logs" {
  name   = "write-function-logs"
  role   = aws_iam_role.ingestion.id
  policy = data.aws_iam_policy_document.lambda_logs.json
}

resource "aws_lambda_function" "ingestion" {
  function_name = var.function_name
  description   = "Validates paginated World Bank indicator data before S3 landing is added."
  role          = aws_iam_role.ingestion.arn
  runtime       = "python3.12"
  handler       = "ingestion.lambda_handler.lambda_handler"
  architectures = ["x86_64"]

  filename         = var.artifact_path
  source_code_hash = filebase64sha256(var.artifact_path)

  memory_size                    = 256
  timeout                        = 60

  environment {
    variables = {
      APP_ENV                         = var.environment
      WORLD_BANK_API_BASE_URL         = "https://api.worldbank.org/v2"
      WORLD_BANK_COUNTRY              = "USA"
      WORLD_BANK_INDICATOR            = "SP.POP.TOTL"
      WORLD_BANK_PAGE                 = "1"
      WORLD_BANK_PER_PAGE             = "25"
      WORLD_BANK_TIMEOUT_SECONDS      = "30"
      WORLD_BANK_MAX_ATTEMPTS         = "3"
      WORLD_BANK_BACKOFF_BASE_SECONDS = "1"
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.ingestion,
    aws_iam_role_policy.lambda_logs,
  ]

  tags = var.tags
}
