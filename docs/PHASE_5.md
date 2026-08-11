# Phase 5: Reusable data-quality framework

## Purpose

Phase 5 adds an explicit quality gate between transformation and publication. The Glue job still
parses and normalizes the immutable landing files, but processed Parquet is written only after
the transformed dataset passes the configured rules. Every run writes one immutable JSON result
that explains what passed or failed.

This component exists because successful Spark execution does not prove that the data is usable.
A job can finish without an exception while producing missing columns, null business keys,
duplicate observations, unexpected categories, or the wrong number of rows.

## Architecture

```text
S3 landing JSON
    -> PySpark normalization
    -> processed candidate + rejected rows
    -> reusable quality evaluator
       -> PASS: quality result + processed Parquet + empty rejected output
       -> FAIL: quality result + rejected evidence + Glue job failure
```

The result path is isolated by the AWS Glue run ID:

```text
s3://<dev-landing-bucket>/quality/world_bank/run_id=<glue-job-run-id>/result.json
```

The writer sends `If-None-Match: *`, so the application cannot replace a result at the same key.
S3 bucket versioning and AES-256 server-side encryption remain enabled as additional controls.

## AWS and Spark concepts

- A data-quality rule turns an expectation into a measured PASS or FAIL result.
- Spark actions execute a lazy DataFrame plan. Related row metrics are aggregated together to
  avoid a separate full scan for every rule.
- Persisting a DataFrame lets quality evaluation and output writing reuse calculated data.
- A business key identifies one logical record independently of Spark's physical row identity.
- S3 conditional writes provide application-level immutability for the result object.
- A Glue run ID separates attempts and supports investigation without overwriting older evidence.

## Quality policy

The reusable `DataQualityConfig` defines:

- required columns;
- expected Spark data types;
- required non-null and non-blank values;
- the business key used for duplicate detection;
- allowed categorical values;
- minimum and expected row counts;
- the maximum permitted number of schema-drift rows;
- whether any rejected row should fail the dataset.

The World Bank policy requires the population indicator `SP.POP.TOTL`, country `USA`, and the
stable processed schema established in Phase 4. Its business key is:

```text
(country_iso3_code, indicator_id, observation_year)
```

## Row-count reconciliation

Each World Bank page repeats the source's total record count in its metadata. The job accepts that
total only when every readable page reports the same value. Quality passes row reconciliation
when:

```text
processed row count + rejected row count = expected source row count
```

Counting rejected rows matters because a pipeline that silently drops an invalid row should not
claim that all source data was accounted for. If metadata totals are missing or inconsistent,
the expected count is unavailable and the required row-count rule fails.

## Rejection classification

The evaluator includes prior transformation failures in the quality totals:

- `NULL_*` contributes to `null_failures`;
- `DUPLICATE_BUSINESS_KEY` contributes to `duplicate_failures`;
- `INVALID_*` contributes to `invalid_type_failures`;
- every rejected row contributes to the rejected-row rule.

It also detects nulls, duplicates, invalid enums, type mismatches, missing columns, and schema
drift that remain in the processed candidate DataFrame.

## Result contract

An abbreviated passing result is:

```json
{
  "dataset": "world_bank_population",
  "run_id": "jr_example",
  "row_count": 66,
  "rejected_row_count": 0,
  "expected_row_count": 66,
  "row_count_match": true,
  "null_failures": 0,
  "duplicate_failures": 0,
  "invalid_type_failures": 0,
  "missing_column_failures": 0,
  "invalid_enum_failures": 0,
  "schema_drift": false,
  "schema_drift_rows": 0,
  "status": "PASS",
  "rules": []
}
```

The actual `rules` array contains one result for each rule with its status, failure count, and
diagnostic details. `evaluated_at` records the UTC evaluation time.

## Failure and replay behavior

The quality result is written before processed output. If status is `FAIL`, the job writes the
rejected dataset and raises `DataQualityFailure`; it does not publish processed Parquet for that
run. A PASS quality result means the candidate data passed its rules, not that later S3 writes or
downstream systems completed. Pipeline-completion monitoring is added in Phase 7.

Recovery uses a new Glue run ID and reads the original immutable landing objects. Previous
quality results and rejected evidence remain available for comparison.

## Local validation

The test suite uses synthetic `.test` data and mocked S3 clients. It covers:

- passing data;
- required nulls and invalid enum values;
- duplicate keys and rejected rows;
- exact row-count reconciliation and mismatches;
- missing columns and incorrect Spark types;
- schema drift;
- consistent and inconsistent source metadata totals;
- the complete World Bank transformation followed by its dataset quality policy;
- encrypted, conditional S3 result writes;
- deterministic Glue library packaging.

## Cost boundary

Local tests, packaging, linting, and Terraform validation do not use AWS services. Deploying the
updated script and library creates tiny versioned S3 artifact writes but does not start Glue
compute. A live Phase 5 Glue validation requires another explicitly approved job run and uses the
same two-worker pricing boundary described in Phase 4.

## DEV deployment checkpoint

On August 11, 2026, Terraform updated the existing DEV resources in place:

- uploaded versioned copies of the Glue entry script and Python library;
- granted the Glue role write access to only `quality/world_bank/*` in the pipeline bucket;
- configured the existing Glue job with its quality-result S3 path.

The apply added no resources, destroyed no resources, and did not start a Glue run. Live quality
validation remains a separate cost-controlled checkpoint.

## Enterprise differences

A larger platform would typically store rule definitions in governed configuration, version data
contracts, emit quality metrics and alerts, distinguish blocking from warning rules, maintain
historical quality tables, assign ownership and severity, and provide controlled overrides. It
might use AWS Glue Data Quality or another managed framework where its rule language, runtime
cost, and operational model fit the organization. This phase keeps the evaluation code explicit
and locally testable before introducing those operational layers.
