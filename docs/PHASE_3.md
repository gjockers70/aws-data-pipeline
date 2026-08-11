# Phase 3: S3 landing architecture

## Purpose

Phase 3 replaces the Lambda's validation-only checkpoint with durable S3 landing storage. Each
validated World Bank API page is preserved as its original JSON response, and a separate manifest
records the run status, source configuration, counts, checksums, object locations, and replay
state.

This gives the later Glue job a stable raw-data boundary. Glue will read landing objects rather
than call the external API, so source acquisition and transformation can fail or replay
independently.

## AWS concepts

- An S3 bucket is a globally named object container; prefixes form the logical folder layout.
- Versioning retains older object versions when a key is overwritten.
- Default encryption protects objects at rest, while a TLS-only bucket policy protects data in
  transit.
- Public Access Block provides account-independent controls against accidental public exposure.
- IAM identity policies grant the Lambda execution role only the required object actions.
- A conditional `PutObject` makes a raw object key create-only for the ingestion application.

## Object layout

Raw source pages use ingestion-date partitions and a run identifier:

```text
s3://<dev-landing-bucket>/
  landing/
    world_bank/
      year=YYYY/
        month=MM/
          day=DD/
            run_id=RUN_ID/
              sp_pop_totl_page_00001.json
  manifests/
    world_bank/
      run_id=RUN_ID.json
```

Date partitions allow Glue and other readers to avoid scanning unrelated dates. The run ID keeps
separate executions isolated even when they retrieve the same indicator on the same day.

## Raw-page immutability and replay

`S3LandingWriter` calculates SHA-256 over the exact UTF-8 response bytes and sends `If-None-Match:
*` with `PutObject`.

- A new key is written with the checksum in object metadata.
- An existing key with the same checksum is treated as an idempotent replay.
- An existing key with a different checksum raises `LandingConflictError`.

The execution role has no `DeleteObject` permission. This is application-level immutability, not
S3 Object Lock compliance mode: an account administrator or Terraform cleanup can still delete
DEV objects. A regulated production system could add Object Lock, retention governance, and a
separate security account.

## Manifest behavior

The manifest is deliberately versioned under one stable key. The runner writes checkpoints for:

1. `RUNNING` before source retrieval;
2. each successfully landed page;
3. `FAILED` with a bounded error description when processing fails; or
4. `COMPLETED` with final counts.

When the same run ID is submitted again, the runner compares the source-configuration
fingerprint. A completed matching run returns immediately without calling the API or writing new
objects. A changed source configuration with the same run ID is rejected.

## Bucket controls

Terraform manages:

- S3 Standard storage;
- all four Public Access Block settings;
- `BucketOwnerEnforced` ownership;
- versioning;
- default `AES256` server-side encryption;
- a bucket policy denying requests that do not use TLS;
- DEV-only `force_destroy` so the documented Terraform cleanup can remove test objects.

The live bucket was verified with AWS APIs as non-public, encrypted, versioned, and owner
enforced.

### Why AES-256 instead of a customer-managed KMS key

S3-managed AES-256 encryption has no separate key-storage charge. A customer-managed AWS KMS key
currently has a recurring monthly key charge. The project therefore demonstrates encrypted S3
storage now and defers the customer-managed KMS boundary to the dedicated security-hardening
phase, where its cost and key policy can be reviewed explicitly.

An enterprise environment may require a customer-managed key, rotation, separation of key and
data administrators, cross-account access, and CloudTrail data events.

## Least-privilege Lambda access

The Lambda execution role can:

- `s3:GetObject` and `s3:PutObject` only under `landing/world_bank/*` and
  `manifests/world_bank/*`;
- `s3:ListBucket` only when the requested prefix matches `manifests/world_bank/*`.

It cannot delete objects, change encryption, change bucket policies, make the bucket public, or
list the raw landing prefix.

The prefix-limited list permission is required because S3 returns `AccessDenied` instead of
`NoSuchKey` for a missing manifest unless the caller is allowed to determine that the key does
not exist. The first live attempt exposed this behavior before any object was written. The
policy was corrected in place and the same run ID then completed successfully.

## Live validation

The controlled run `phase3-smoke-001` completed with:

```json
{
  "status": "COMPLETED",
  "pages": 3,
  "records": 66,
  "source_bytes": 13671,
  "landing_status": "S3_PERSISTED",
  "replayed": false
}
```

S3 contained three raw objects with sizes 5,166, 5,166, and 3,339 bytes, plus a 1,559-byte final
manifest. Version history contained three raw versions and five expected manifest checkpoint
versions. Total retained data across all versions was 19,275 bytes, about 18.8 KiB.

The second invocation used the identical run ID and returned `replayed: true`. It did not create
another raw version.

The final Terraform plan reported:

```text
No changes. Your infrastructure matches the configuration.
```

## Cost boundary

S3 has no minimum charge, but storage and API requests are metered. This validation used about
18.8 KiB of versioned storage and a small number of PUT, GET, HEAD, and LIST requests. Its
on-demand value is far below one cent and is expected to remain within the account's available
free allowances or credits. The Billing console remains the source of truth because usage data
can be delayed.

No customer-managed KMS key, replication, S3 Inventory, access logging, CloudTrail data events,
or Intelligent-Tiering monitoring was enabled.

## Cleanup

From `infra/terraform/environments/dev`, review the destroy plan before applying it:

```powershell
terraform plan -destroy
terraform destroy
```

`force_destroy=true` is limited to DEV and allows Terraform to remove the test object versions
before deleting the bucket. Production landing buckets should normally use retention controls
and deletion safeguards instead.

## Phase 4 boundary

Phase 4 will introduce Glue/PySpark transformations that read these raw JSON pages, normalize and
cast fields, handle malformed records, deduplicate rows, and write transformed output. It will
not change the raw objects produced in this phase.
