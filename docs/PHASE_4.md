# Phase 4: Glue and PySpark transformation

## Purpose

Phase 4 converts immutable World Bank JSON responses into a stable, columnar dataset. The Glue
job reads only from the S3 landing prefix; it does not call the external API or alter raw source
objects. Valid records become partitioned Parquet, while malformed or invalid records are
written separately as JSON with a rejection reason and source location.

This separates acquisition from transformation. A failed transformation can be corrected and
replayed from the original landing objects without calling the source again.

## Concepts to understand

- A Glue job is a managed Spark application. The job definition itself is idle; DPU billing
  begins only when a job run starts.
- A Spark DataFrame has a schema and represents transformations as a lazy execution plan.
- An explicit schema prevents Spark from silently selecting different types across input files.
- Parquet is a compressed columnar format that supports projection and partition pruning.
- A business key identifies the same logical observation even when it appears in multiple files.
- A rejected-record path preserves failure evidence without contaminating processed data.

## Source shape and normalization

Each World Bank response is one JSON document shaped as:

```text
[
  {page metadata},
  [
    {
      indicator: {id, value},
      country: {id, value},
      countryiso3code,
      date,
      value,
      unit,
      obs_status,
      decimal
    }
  ]
]
```

Because this is not newline-delimited JSON, the job reads each S3 object as a binary file and
decodes the whole content as UTF-8. The parser then emits an explicit intermediate schema before
Spark applies casts and validation.

The processed fields are:

| Field | Type | Source |
| --- | --- | --- |
| `indicator_id` | string | `indicator.id` |
| `indicator_name` | string | `indicator.value` |
| `country_id` | string | `country.id` |
| `country_name` | string | `country.value` |
| `country_iso3_code` | string | `countryiso3code` |
| `observation_year` | integer | cast from `date` |
| `observation_value` | double | cast from `value` |
| `unit` | string | `unit` |
| `observation_status` | string | `obs_status` |
| `decimal_places` | integer | cast from `decimal` |

Source file, source record index, schema-drift flag, and unexpected field names are retained for
lineage and troubleshooting.

## Validation and rejection rules

The transformation rejects:

- malformed JSON documents;
- documents that do not contain metadata plus a record array;
- records that are not objects;
- invalid `indicator` or `country` nested objects;
- missing required indicator, country ISO3, year, or value fields;
- year, value, or decimal values that cannot be cast to the expected type;
- duplicate business keys.

The business key is `(country_iso3_code, indicator_id, observation_year)`. When duplicates are
found, the record with the lexically first source path and lowest record index is retained. The
others are written to rejected output as `DUPLICATE_BUSINESS_KEY`, making the rule deterministic
and auditable.

Unexpected source fields do not immediately reject an otherwise usable record. They set
`schema_drift=true` and populate `schema_drift_fields`. Phase 5 will build the reusable quality
result and policy layer that decides when drift should fail a pipeline.

## Output layout and replay

The Glue entry point uses the AWS-generated job run ID:

```text
s3://<dev-landing-bucket>/
  processed/world_bank/run_id=<glue-job-run-id>/observation_year=YYYY/*.parquet
  rejected/world_bank/run_id=<glue-job-run-id>/*.json
```

Every run writes to a new prefix, so a retry cannot silently overwrite a prior result. A later
recovery process can compare runs and promote only a validated output.

## Local development

The project pins PySpark 3.5.4 because Glue 5.0 uses Spark 3.5.4, Java 17, and Python 3.11. Build
the artifacts and run tests with:

```powershell
python scripts/build_glue.py
ruff check src tests
pytest tests/spark
```

Windows can execute the in-memory parsing, casting, validation, drift, and deduplication tests.
The local Parquet filesystem round-trip is skipped on Windows because Apache Hadoop's optional
`winutils` native helper is not bundled. That test runs in a Linux environment, matching the
Glue execution environment more closely.

## Glue Visual ETL equivalent

The same logical flow could be represented in Glue Studio Visual ETL as:

```text
S3 source -> Custom transform -> Change Schema -> Data Quality checks
          -> Remove Duplicates -> Conditional Router -> S3 Parquet / S3 rejected JSON
```

The custom transform is still needed because each source object contains the World Bank's
two-element document wrapper rather than ordinary newline-delimited JSON. `Change Schema` maps
and casts normalized columns. A conditional router separates accepted and rejected rows, and
the accepted S3 target partitions by observation year.

The code-first job is used here because it is versionable, locally testable, reviewable in Git,
and easier to reproduce across environments. Visual ETL remains useful for communicating the
node graph and for teams that prefer console-assisted job authoring.

## IAM and operational boundary

The Glue execution role can:

- list key names in the dedicated pipeline bucket, as required by Spark's S3 output committer;
- read only landing objects and its two deployment artifacts;
- write only processed and rejected objects;
- write only to the managed Glue CloudWatch log groups.

It has no S3 delete permission, cannot read manifest objects or unrelated prefixes,
and no permission to start itself. The job has no schedule or trigger.

Spark performs a bucket-level destination check without an `s3:prefix` condition before writing
Parquet. The initial prefix-conditioned list policy therefore failed at runtime. `ListBucket` is
scoped to this one pipeline bucket, while object content remains protected by prefix-restricted
`GetObject` and `PutObject` permissions.

## Cost gate

AWS currently lists Glue ETL at **$0.44 per DPU-hour**, billed per second with a one-minute
minimum. This smallest job uses two `G.1X` workers, so its minimum compute charge is approximately
`2 x $0.44 / 60 = $0.0147` before storage and request charges. A run lasting ten minutes would be
about $0.147 in Glue compute.

Creating the idle job definition does not start a job run. The code and infrastructure can be
built, tested, planned, and deployed without starting Glue compute. A live run requires a
separate explicit cost approval.

References: [AWS Glue pricing](https://aws.amazon.com/glue/pricing/) and
[AWS Glue 5.0 migration guide](https://docs.aws.amazon.com/glue/latest/dg/migrating-version-50.html).

## Deployment checkpoint

The reviewed DEV plan contained nine additions, zero changes, and zero destructions. Terraform
created the idle job, execution role and two inline policies, three log groups, and two encrypted
S3 deployment artifacts. The final drift check reported no changes.

The initial deployment verification found:

- Glue version 5.0 with two `G.1X` workers, no automatic retries, and a ten-minute timeout;
- a 1,238-byte entry script and a 3,199-byte transformation library archive;
- 14-day retention on each Glue log group.

The first live run exposed a duplicate `JOB_RUN_ID` registration in the Glue argument parser and
failed before reading source data. The entrypoint now requests only custom options while using
the Glue-provided run ID for output isolation. A regression test protects that contract.

The second run completed parsing and transformation but failed when Spark's Parquet writer made
a bucket-level `ListBucket` request without a prefix. After explicit approval, the role received
bucket-wide key-listing permission on this dedicated pipeline bucket. `GetObject` remains limited
to landing and artifact objects, while `PutObject` remains limited to processed and rejected
objects.

The final run succeeded in 84 seconds. S3 and local Parquet inspection verified:

- 66 processed rows and 14 columns;
- 66 observation-year partitions covering 1960 through 2025;
- zero nulls across indicator ID, country ISO3 code, observation year, and observation value;
- zero duplicate business keys;
- zero rows with schema drift;
- no rejected records; the rejected prefix contains only an empty success marker;
- AES-256 server-side encryption on the sampled Parquet object.

The three attempts used 52, 193, and 84 execution seconds. Applying the one-minute minimum to the
first attempt gives an estimated total Glue compute cost of approximately $0.082, plus negligible
S3 request, versioned-storage, and CloudWatch usage. The result is intentionally split into one
small Parquet object per year; production-scale data would need a measured partition and file
compaction strategy to avoid a small-files problem.

## Enterprise differences

A larger production pipeline would commonly add a Glue Data Catalog, Lake Formation controls,
KMS customer-managed keys, job bookmarks or a dedicated orchestration state store, compact-file
management, autoscaling decisions based on measured workloads, cross-account deployment, and a
formal schema registry or data contract. Those additions are deliberately deferred until their
cost and operational value can be reviewed in the appropriate phase.
