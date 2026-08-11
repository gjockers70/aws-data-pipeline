variable "aws_region" {
  description = "AWS region for the DEV deployment."
  type        = string
  default     = "us-east-1"
}

variable "lambda_artifact_path" {
  description = "Path to the packaged Lambda ZIP."
  type        = string
  default     = "../../../../build/lambda/function.zip"
}
