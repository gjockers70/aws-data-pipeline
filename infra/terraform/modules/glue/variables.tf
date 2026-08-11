variable "job_name" {
  description = "Name of the AWS Glue ETL job."
  type        = string
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
}

variable "bucket_name" {
  description = "S3 bucket containing source, artifacts, and job output."
  type        = string
}

variable "bucket_arn" {
  description = "ARN of the S3 bucket containing source, artifacts, and job output."
  type        = string
}

variable "script_artifact_path" {
  description = "Local path to the packaged Glue entry script."
  type        = string
}

variable "library_artifact_path" {
  description = "Local path to the packaged transformation library ZIP."
  type        = string
}

variable "log_retention_days" {
  description = "Retention period for Glue CloudWatch logs."
  type        = number
  default     = 14
}

variable "tags" {
  description = "Tags applied to Glue resources."
  type        = map(string)
  default     = {}
}
