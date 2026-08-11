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

variable "glue_script_artifact_path" {
  description = "Path to the packaged Glue entry script."
  type        = string
  default     = "../../../../build/glue/world_bank_job.py"
}

variable "glue_library_artifact_path" {
  description = "Path to the packaged Glue transformation library ZIP."
  type        = string
  default     = "../../../../build/glue/transformations.zip"
}
