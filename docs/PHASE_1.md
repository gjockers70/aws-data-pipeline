# Phase 1: Local REST API ingestion

## Purpose

Phase 1 proves the ingestion behavior locally before packaging it for AWS Lambda. It retrieves
paginated World Bank indicator data, preserves the source JSON, and produces enough operational
metadata to diagnose or replay a run without using AWS services.

## Runtime flow

```text
Environment configuration
  -> World Bank API client
  -> pagination and bounded retries
  -> response and record validation
  -> immutable page files
  -> run manifest
  -> structured JSON logs
```

Each source page is stored independently so a failed multi-page run does not lose pages that were
already retrieved. The manifest is updated after every successful page.

## Run locally

With the virtual environment activated:

```powershell
ingest-world-bank
```

The program creates a UUID run ID when `INGESTION_RUN_ID` is not supplied. To create a repeatable
run ID for replay testing:

```powershell
$env:INGESTION_RUN_ID = "manual-population-001"
ingest-world-bank
```

Submitting that ID again with the same source configuration returns the completed manifest without
calling the API. Remove the override when finished:

```powershell
Remove-Item Env:INGESTION_RUN_ID
```

## Configuration

| Environment variable | Default | Purpose |
|---|---:|---|
| `WORLD_BANK_API_BASE_URL` | `https://api.worldbank.org/v2` | Source API base URL |
| `WORLD_BANK_COUNTRY` | `USA` | Country or aggregate requested |
| `WORLD_BANK_INDICATOR` | `SP.POP.TOTL` | Indicator code |
| `WORLD_BANK_PAGE` | `1` | First page requested |
| `WORLD_BANK_PER_PAGE` | `25` | Requested page size |
| `WORLD_BANK_TIMEOUT_SECONDS` | `30` | Per-request timeout |
| `WORLD_BANK_MAX_ATTEMPTS` | `3` | Maximum attempts per page |
| `WORLD_BANK_BACKOFF_BASE_SECONDS` | `1` | First exponential-backoff delay |
| `INGESTION_RUN_ID` | generated UUID | Optional idempotency and replay key |
| `LANDING_ROOT` | `local_data/landing` | Local raw-data root |
| `MANIFEST_ROOT` | `local_data/manifests` | Local run-manifest root |

No variable contains credentials. Later AWS phases will move non-secret settings to SSM Parameter
Store and use Secrets Manager only if a selected source or database connection requires a secret.

## Retry policy

Timeouts, connection failures, HTTP 429, and HTTP 500/502/503/504 are retried. With the defaults,
the client makes at most three attempts with delays of one and two seconds after the first two
failures. Permanent HTTP errors are returned immediately.

## Validation performed

The client rejects a page when:

- the response is not the expected two-item metadata-and-records array;
- pagination metadata is missing, non-numeric, or outside its allowed range;
- records are not JSON objects;
- a record lacks `country`, `countryiso3code`, `date`, `indicator`, or `value`;
- nested country or indicator identifiers/names have unexpected types;
- an observation value is neither numeric nor null.

This is source-contract validation, not the complete data-quality framework. Null rules,
duplicates, enumerations, row-count reconciliation, and persisted schema-drift results belong to
Phases 4 and 5 after the data has a normalized schema.

## Manifest and checksums

Manifests are written to:

```text
local_data/manifests/world_bank/run_id=RUN_ID.json
```

A manifest records the source configuration fingerprint, timestamps, status, expected and landed
page counts, record counts, error details, object paths, SHA-256 checksums, and whether each object
was newly written or already present.

Landing objects use this layout:

```text
local_data/landing/world_bank/
  year=YYYY/month=MM/day=DD/run_id=RUN_ID/
    sp_pop_totl_page_00001.json
```

If a failed run is resubmitted, matching page content is marked `EXISTING`. Different content for
the same run ID and page is rejected instead of overwriting the original file. A run ID cannot be
reused with a different source configuration.

## Structured logs

Runtime logs are one JSON object per line. Events include `run_started`, `page_landed`,
`run_completed`, `run_failed`, and `run_skipped`. Only explicitly selected operational fields are
logged; response bodies and credentials are not logged.

## Test coverage

The local suite covers:

- successful response parsing;
- pagination;
- malformed response and record schemas;
- retryable timeouts and HTTP failures;
- non-retryable HTTP failures;
- raw-payload preservation and checksums;
- matching-content idempotency and conflicting-content rejection;
- completed-run skipping;
- failed-run manifest creation and replay;
- run ID/configuration conflicts.

## Local limitations and Phase 2 boundary

Phase 1 deliberately does not include Lambda, S3, IAM, KMS, CloudWatch, Terraform, CSV ingestion,
or PySpark. The local manifest store does not provide distributed locking for concurrent workers.
The current retry policy does not yet add jitter or honor `Retry-After`.

Phase 2 will adapt the tested orchestration to Lambda, replace the local landing and manifest
stores with AWS-backed implementations, obtain configuration from the deployed environment, and
emit logs suitable for CloudWatch. The core API behavior and tests remain reusable.
