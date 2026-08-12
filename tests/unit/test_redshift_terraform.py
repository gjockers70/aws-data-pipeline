from pathlib import Path

MODULE = (
    Path(__file__).resolve().parents[2] / "infra" / "terraform" / "modules" / "redshift_serverless"
)
DEV = Path(__file__).resolve().parents[2] / "infra" / "terraform" / "environments" / "dev"


def test_redshift_is_disabled_by_default_and_capped_at_four_rpu():
    variables = (DEV / "variables.tf").read_text(encoding="utf-8")
    main = (DEV / "main.tf").read_text(encoding="utf-8")

    assert 'variable "enable_redshift"' in variables
    assert "default     = false" in variables
    assert 'variable "redshift_base_capacity"' in variables
    assert "max_capacity         = var.redshift_base_capacity" in main


def test_private_network_has_no_internet_gateway_or_nat_gateway():
    main = (MODULE / "main.tf").read_text(encoding="utf-8")

    assert "publicly_accessible  = false" in main
    assert "enhanced_vpc_routing = true" in main
    assert 'resource "aws_vpc_endpoint" "s3"' in main
    assert 'resource "aws_internet_gateway"' not in main
    assert 'resource "aws_nat_gateway"' not in main
    assert main.count('resource "aws_subnet"') == 1
    assert "count = 3" in main


def test_s3_permissions_are_read_only_and_prefix_scoped():
    main = (MODULE / "main.tf").read_text(encoding="utf-8")

    assert 'values   = ["warehouse/world_bank/*"]' in main
    assert '"${var.bucket_arn}/warehouse/world_bank/*"' in main
    assert 'actions   = ["s3:GetObject"]' in main
    assert "s3:PutObject" not in main
    assert "s3:DeleteObject" not in main


def test_daily_usage_limit_deactivates_compute():
    main = (MODULE / "main.tf").read_text(encoding="utf-8")

    assert 'usage_type    = "serverless-compute"' in main
    assert 'period        = "daily"' in main
    assert 'breach_action = "deactivate"' in main
