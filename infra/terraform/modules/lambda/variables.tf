variable "function_name" {
  description = "Name of the ingestion Lambda function."
  type        = string
}

variable "artifact_path" {
  description = "Absolute or caller-relative path to the Lambda deployment ZIP."
  type        = string
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention period."
  type        = number
  default     = 14
}

variable "tags" {
  description = "Tags applied to supported resources."
  type        = map(string)
  default     = {}
}
