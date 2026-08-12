# Phase 6: Redshift warehouse layers

## Purpose

Phase 6 introduces a relational analytics boundary after the validated S3 output. Glue produces
clean files, while Redshift provides stable schemas, SQL transformations, entity relationships,
repeatable upserts, and dashboard-oriented views.

The warehouse uses four schemas:

```text
staging -> core -> mart
             \
              audit
```

- `staging` mirrors one validated Glue output and retains source lineage.
- `core` stores durable country, indicator, and population entities.
- `mart` exposes calculations and aggregations for reporting.
- `audit` records warehouse load attempts and their row counts.

## Physical S3-to-Redshift boundary

The Phase 4 processed dataset is partitioned by `observation_year`. Spark stores that value in the
folder name and removes it from each physical Parquet file. Local inspection confirmed that the
logical dataset has 14 columns but each file has 13 columns. Redshift `COPY` loads Parquet values
by physical column order and does not reconstruct Hive partition values from S3 paths.

The Glue job therefore keeps both representations:

```text
processed/world_bank/run_id=<run-id>/observation_year=YYYY/*.parquet
warehouse/world_bank/run_id=<run-id>/*.parquet
```

The partitioned output remains useful for lake queries. The warehouse output is unpartitioned so
all 14 staging columns, including `observation_year`, are embedded in every Parquet record. Both
paths are immutable and isolated by Glue run ID.

## Staging layer

`staging.world_bank_population` follows the warehouse Parquet column order exactly. It retains:

- normalized indicator and country fields;
- observation year and value;
- source file and source record index;
- schema-drift evidence in a `SUPER` column;
- warehouse load run ID and timestamp.

The load uses `IAM_ROLE default`; no access keys or database passwords appear in SQL. The
`SERIALIZETOJSON` option maps the Parquet array of drift-field names into Redshift `SUPER`.

## Core layer

The core model is a small star schema:

```text
core.dim_country   --< core.fact_population >-- core.dim_indicator
```

`dim_country` has one row per ISO3 country code. `dim_indicator` has one row per World Bank
indicator. `fact_population` has one row per country, indicator, and observation year.

The SQL uses `MERGE` so replaying a validated source run updates existing business keys and inserts
new ones. The fact transformation rounds the source double and casts it to `BIGINT`, which matches
the whole-number population measure.

Redshift primary, unique, and foreign-key constraints are informational and are not enforced like
constraints in a transactional database. They document the model and can help query planning, but
explicit duplicate, null, and row-count checks remain mandatory.

## Mart layer

The first mart contains three views:

- `mart.population_yearly` joins both dimensions to the fact and calculates annual absolute and
  percentage change with `LAG`;
- `mart.population_decade_summary` groups population into decades and calculates minimum,
  maximum, average, and range;
- `mart.population_latest_kpi` returns the most recent population and annual change for each
  country.

These views support trend charts, decade summaries, latest-value KPI cards, and annual-growth
visuals without exposing warehouse keys to a dashboard.

## Distribution, sort keys, and optimization

All tables begin with `DISTSTYLE AUTO` and `SORTKEY AUTO`. This is appropriate for the small DEV
dataset because Redshift can observe real joins and filters before selecting physical keys.
Dimensions may initially be distributed to every compute node because they are small. A larger
fact table may later move to even or key distribution.

A manual production design would consider collocating frequently joined fact and dimension rows
with a shared distribution key. A date or year sort key can improve range scans by allowing
Redshift to skip blocks. Those choices should be driven by table size, query plans, and workload
history rather than assumed for a 66-row dataset.

## SQL execution order

The local SQL is organized in dependency order:

```text
001_create_schemas.sql
010_create_staging.sql
020_create_core.sql
030_create_mart.sql
040_load_staging.sql
050_merge_core.sql
060_validate_load.sql
```

The load script contains two runtime placeholders:

- `{{warehouse_load_uri}}` for the exact validated Glue run prefix;
- `{{load_run_id}}` for warehouse audit and replay identity.

A later execution component will render only validated values and submit statements through the
Redshift Data API. String replacement by untrusted input is not permitted.

## Validation SQL

The current validation queries measure:

- nulls in required staging fields;
- duplicate staging business keys;
- staging-to-core row-count reconciliation;
- schema-drift rows.

The expected first live load is 66 staging rows, 66 fact rows, one country row, one indicator row,
and zero failures. Those values are expectations until a Redshift live load is approved and run.

## Replay and failure recovery

A Glue run creates a new immutable warehouse prefix. A warehouse replay identifies that exact
prefix and load run ID. Staging is replaced, while core tables use business-key `MERGE` operations,
so replay does not append duplicate facts.

If `COPY` fails, Redshift leaves an error for investigation and the core merge must not run. If
validation fails after merge, the load is marked failed and downstream mart refresh or dashboard
refresh must not proceed. Transaction boundaries and audit-status orchestration are added with the
Data API executor before live deployment.

## Cost decision

Redshift Serverless is recommended for this project:

- the minimum base capacity in `us-east-1` is 4 RPU;
- pricing begins around USD 1.50 per active hour;
- usage is billed per second with a 60-second minimum;
- the minimum compute activation is therefore approximately USD 0.025;
- managed storage is billed separately and is negligible for this dataset;
- idle workgroups do not incur compute charges.

Provisioned Redshift starts around USD 0.543 per hour and continues charging while the cluster is
running, which is roughly USD 396 for a 730-hour month. It is a poor default for an intermittent
small project unless it is manually paused and carefully monitored.

The Terraform design includes a 4-RPU base and maximum, a one RPU-hour daily deactivation limit,
private networking, no public endpoint, a free S3 gateway endpoint, an S3 read role scoped to
`warehouse/world_bank/*`, AWS-managed encryption, and a cleanup procedure. Redshift remains
disabled by default and has not been provisioned.

The disabled DEV plan was applied on 2026-08-12. It updated four existing Glue resources in place:
the job argument, its prefix-scoped S3 write policy, and two versioned job artifacts. It added and
destroyed no resources, started no compute, and prepared the job to write the warehouse load
dataset. The independently verified enabled plan contains 17 additions, four in-place updates,
and zero deletions; it must not be applied without a separate cost approval.

Official references:

- https://aws.amazon.com/redshift/pricing/
- https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-billing.html
- https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-capacity.html
- https://docs.aws.amazon.com/redshift/latest/dg/copy-usage_notes-copy-from-columnar.html

## Enterprise differences

A larger platform would separate deployment and runtime roles, use database role-based access,
manage schema migrations with an approved migration tool, retain multiple staging batches, create
formal load-control tables, enforce workload management policies, monitor query queues and storage,
and test distribution changes with representative data. It might use slowly changing dimensions,
late-arriving fact handling, materialized marts, and cross-account data sharing.
