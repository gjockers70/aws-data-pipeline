variable "name_prefix" {
  description = "Prefix used for Redshift Serverless and network resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
}

variable "bucket_name" {
  description = "Pipeline S3 bucket name."
  type        = string
}

variable "bucket_arn" {
  description = "Pipeline S3 bucket ARN."
  type        = string
}

variable "base_capacity" {
  description = "Base Redshift Processing Units."
  type        = number
  default     = 4
}

variable "max_capacity" {
  description = "Maximum Redshift Processing Units."
  type        = number
  default     = 4
}

variable "daily_rpu_hour_limit" {
  description = "Daily RPU-hour ceiling before the workgroup is deactivated."
  type        = number
  default     = 1
}

variable "tags" {
  description = "Tags applied to resources."
  type        = map(string)
  default     = {}
}
