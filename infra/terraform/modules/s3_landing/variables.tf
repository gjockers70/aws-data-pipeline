variable "bucket_name" {
  description = "Globally unique S3 landing bucket name."
  type        = string
}

variable "force_destroy" {
  description = "Allow Terraform to remove DEV objects when the bucket is destroyed."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to supported landing resources."
  type        = map(string)
  default     = {}
}
