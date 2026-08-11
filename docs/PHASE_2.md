# Phase 2: AWS Lambda ingestion adapter

## Purpose

Phase 2 adapts the tested REST client for AWS Lambda. The function proves that a managed Lambda
runtime can reach the World Bank API, paginate, validate the source contract, and emit useful
structured logs.

S3 is intentionally not simulated with Lambda `/tmp` storage. Raw landing remains
`DEFERRED_TO_PHASE_3` until an encrypted S3 bucket and S3-backed writer exist.

## Lambda event contract

Every field is optional:

```json
{
  "run_id": "manual-lambda-001",
  "country": "USA",
  "indicator": "SP.POP.TOTL",
  "start_page": 1,
  "per_page": 25
}
```

When `run_id` is omitted, the Lambda request ID becomes the run ID. Unknown event fields are
rejected, and country/indicator values are restricted to the characters used by the source API.
Event values are never copied wholesale into logs.

A successful direct invocation returns a small summary:

```json
{
  "status": "COMPLETED",
  "run_id": "manual-lambda-001",
  "country": "USA",
  "indicator": "SP.POP.TOTL",
  "pages": 3,
  "records": 66,
  "source_bytes": 12345,
  "landing_status": "DEFERRED_TO_PHASE_3"
}
```

Raw responses are not returned because Lambda responses have size limits and raw data belongs in
the landing layer. Source failures are raised so AWS marks the invocation as failed.

## Package locally

```powershell
.\.venv\Scripts\python.exe scripts\build_lambda.py
```

The reproducible artifact is written to `build/lambda/function.zip`. The build directory is
excluded from Git. The ZIP includes the ingestion package and its `requests` dependency; it does
not include credentials, local landing data, or Terraform state.

The deployed handler is:

```text
ingestion.lambda_handler.lambda_handler
```

## Terraform design

The DEV root is `infra/terraform/environments/dev`, with the reusable function resources in
`infra/terraform/modules/lambda`.

The configuration creates only:

- one Python 3.12 Lambda function;
- one Lambda execution role;
- one inline log-writing policy;
- one CloudWatch log group with 14-day retention.

The role can write only log streams/events beneath its own log group. It has no S3, Secrets
Manager, SSM, database, network-management, or account-administration permissions.

The Lambda is outside a VPC because it currently calls a public HTTPS API and has no private
resource dependency. Putting it in private subnets now would add networking complexity and could
require paid NAT egress without improving the current security boundary.

Memory is set to 256 MB and timeout to 60 seconds. The function has no schedule, event source,
or public function URL, so it can run only through an explicitly authorized manual invocation.
Reserved concurrency is intentionally unset because new AWS accounts can have an initial account
concurrency quota of 10, and AWS does not permit a reservation that would reduce unreserved
concurrency below 10.

## Validate without deploying

From the DEV Terraform directory:

```powershell
..\..\..\..\.tools\terraform\terraform.exe init -backend=false
..\..\..\..\.tools\terraform\terraform.exe validate
```

`terraform init` creates `.terraform.lock.hcl`, which is committed so future runs select the same
provider version. `.terraform/` and state files remain excluded.

## Deployment gate

No `terraform plan` or `terraform apply` should run until all of these are true:

- AWS CLI authentication identifies the intended AWS account;
- the DEV region is explicitly confirmed;
- billing alerts or budgets have been reviewed;
- the plan contains only the four resources listed above;
- the Lambda ZIP has passed tests and content inspection.

The current default region is `us-east-1`, but it remains an input rather than an architectural
requirement. All five gates were completed before the DEV deployment.

## DEV deployment result

Phase 2 was deployed to `us-east-1` on 2026-08-11. Terraform created exactly four managed
resources:

- `aws-data-pipeline-dev-ingestion` Lambda function;
- its Lambda service execution role;
- an inline policy limited to creating log streams and writing events in the function's log
  group;
- `/aws/lambda/aws-data-pipeline-dev-ingestion` with 14-day retention.

The first apply exposed a new-account Lambda quota constraint: reserving one concurrent execution
would have reduced the account's unreserved concurrency below AWS's required minimum of 10. The
unsupported reservation was removed. The function remains protected from accidental automated
usage because it has no schedule, event source mapping, or public function URL.

After reconciling the partial apply, a Terraform refresh and plan reported:

```text
No changes. Your infrastructure matches the configuration.
```

One controlled live invocation used `run_id=phase2-smoke-001` and returned:

```json
{
  "status": "COMPLETED",
  "run_id": "phase2-smoke-001",
  "country": "USA",
  "indicator": "SP.POP.TOTL",
  "pages": 3,
  "records": 66,
  "source_bytes": 13671,
  "landing_status": "DEFERRED_TO_PHASE_3"
}
```

CloudWatch recorded start, per-page validation counts of 25, 25, and 16, completion, duration,
and memory usage. No credentials or raw response payloads were logged.

## Cost boundary

This checkpoint uses manual invocations, one small function, short log retention, and no NAT
Gateway. IAM has no additional charge, and idle Lambda functions do not incur compute charges.
The smoke test used about 10.2 GB-seconds of Lambda compute and a few kilobytes of logs, far below
the published monthly free allowances of 400,000 Lambda GB-seconds, one million requests, and
5 GB of CloudWatch Logs. The Billing console remains the source of truth for account-wide usage.

## Cleanup after a future deployment

From the same DEV directory:

```powershell
terraform plan -destroy
terraform destroy
```

The destroy plan must be reviewed before approval. Destroying the stack removes the function,
execution role/policy, and its Terraform-managed log group.

## Phase 3 boundary

Phase 3 will add an encrypted, immutable S3 landing bucket and an S3 implementation of the landing
and manifest stores. The execution role will then gain narrowly scoped permissions for the exact
bucket prefixes and KMS key required by ingestion.
