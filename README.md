# AWS Data Pipeline

This project builds a cloud-native data pipeline incrementally:

```text
External REST API -> Lambda -> S3 -> Glue/PySpark -> Redshift -> QuickSight
```

## Current checkpoint

Phase 1 currently provides a local ingestion flow that:

- follows the World Bank page metadata until all pages are retrieved;
- retries timeouts, connection failures, throttling, and transient server errors;
- uses bounded exponential backoff between retry attempts;
- validates the top-level response structure;
- validates required fields and basic source data types;
- preserves the original JSON response;
- writes it to a date-partitioned local landing directory;
- records page counts, row counts, file checksums, and status in a run manifest;
- safely skips a completed run when the same run ID is submitted again;
- emits structured JSON logs without credentials;
- runs without AWS credentials or AWS charges.

AWS services and infrastructure remain intentionally deferred to later review checkpoints.

## Local setup

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ingest-world-bank
pytest
```

The default request retrieves all available pages of United States population observations.
Configuration can be overridden with the environment variables documented in `.env.example`.

Raw responses are written beneath:

```text
local_data/landing/world_bank/year=YYYY/month=MM/day=DD/run_id=RUN_ID/
```

`local_data/` is excluded from Git because landing data is generated runtime output.

See [`docs/PHASE_1.md`](docs/PHASE_1.md) for the run manifest, replay procedure,
configuration, validation boundary, and known local limitations.
