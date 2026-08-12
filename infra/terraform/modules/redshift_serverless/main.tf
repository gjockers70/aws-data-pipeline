data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_region" "current" {}

data "aws_iam_policy_document" "assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["redshift.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "warehouse_read" {
  statement {
    sid       = "ListWarehouseObjects"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [var.bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["warehouse/world_bank/*"]
    }
  }

  statement {
    sid       = "ReadWarehouseObjects"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.bucket_arn}/warehouse/world_bank/*"]
  }
}

data "aws_iam_policy_document" "s3_endpoint" {
  statement {
    effect = "Allow"
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      var.bucket_arn,
      "${var.bucket_arn}/warehouse/world_bank/*",
    ]
  }
}

resource "aws_vpc" "warehouse" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-vpc" })
}

resource "aws_subnet" "warehouse" {
  count = 3

  vpc_id                  = aws_vpc.warehouse.id
  cidr_block              = cidrsubnet(aws_vpc.warehouse.cidr_block, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = false

  tags = merge(var.tags, { Name = "${var.name_prefix}-private-${count.index + 1}" })
}

resource "aws_route_table" "warehouse" {
  count = 3

  vpc_id = aws_vpc.warehouse.id
  tags   = merge(var.tags, { Name = "${var.name_prefix}-private-${count.index + 1}" })
}

resource "aws_route_table_association" "warehouse" {
  count = 3

  subnet_id      = aws_subnet.warehouse[count.index].id
  route_table_id = aws_route_table.warehouse[count.index].id
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.warehouse.id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = aws_route_table.warehouse[*].id
  policy            = data.aws_iam_policy_document.s3_endpoint.json

  tags = merge(var.tags, { Name = "${var.name_prefix}-s3" })
}

resource "aws_security_group" "warehouse" {
  name_prefix = "${var.name_prefix}-"
  description = "Redshift Serverless egress to the S3 gateway endpoint"
  vpc_id      = aws_vpc.warehouse.id

  egress {
    description     = "HTTPS to Amazon S3"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    prefix_list_ids = [aws_vpc_endpoint.s3.prefix_list_id]
  }

  tags = var.tags
}

resource "aws_iam_role" "warehouse" {
  name               = "${var.name_prefix}-s3-read"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "warehouse_read" {
  name   = "read-world-bank-warehouse"
  role   = aws_iam_role.warehouse.id
  policy = data.aws_iam_policy_document.warehouse_read.json
}

resource "aws_redshiftserverless_namespace" "warehouse" {
  namespace_name       = "${var.name_prefix}-namespace"
  db_name              = "analytics"
  default_iam_role_arn = aws_iam_role.warehouse.arn
  iam_roles            = [aws_iam_role.warehouse.arn]

  tags = var.tags
}

resource "aws_redshiftserverless_workgroup" "warehouse" {
  workgroup_name       = "${var.name_prefix}-workgroup"
  namespace_name       = aws_redshiftserverless_namespace.warehouse.namespace_name
  base_capacity        = var.base_capacity
  max_capacity         = var.max_capacity
  publicly_accessible  = false
  enhanced_vpc_routing = true
  subnet_ids           = aws_subnet.warehouse[*].id
  security_group_ids   = [aws_security_group.warehouse.id]

  config_parameter {
    parameter_key   = "require_ssl"
    parameter_value = "true"
  }

  tags = var.tags
}

resource "aws_redshiftserverless_usage_limit" "daily_compute" {
  resource_arn  = aws_redshiftserverless_workgroup.warehouse.arn
  usage_type    = "serverless-compute"
  period        = "daily"
  amount        = var.daily_rpu_hour_limit
  breach_action = "deactivate"
}
