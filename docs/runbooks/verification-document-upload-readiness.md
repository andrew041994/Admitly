# Verification-document upload infrastructure gate

Creator verification is account-level. The repository now contains the disabled
backend foundation, additive tracking migration, private-storage policy templates,
and operator checks. Website ID upload is **not ready to enable** until the separate
AWS bucket/IAM controls, migration, coordinated legal text, admin/web UI, and
synthetic security evidence are complete. This document authorizes no infrastructure,
environment, migration, deployment, retention, or production change.

## Current blocker

The configured application object storage is designed for normalized, public event-cover images. Its documented application role has `s3:PutObject` only on `S3_EVENT_PREFIX`; the application deliberately has no read or delete permission, constructs a permanent public URL, and records cover object keys in ordinary audit metadata. That design cannot provide private administrator review or reliable post-review deletion for government ID images.

Do not place verification documents in `S3_EVENT_BUCKET`, beneath `S3_EVENT_PREFIX`, behind `S3_PUBLIC_BASE_URL`, or in any bucket/prefix with anonymous/CDN reads. Current legal text remains email-only until the private infrastructure and coordinated product flow are reviewed and approved for release.

## Required private-storage evidence

Prefer a distinct private bucket, workload role, and configuration namespace so public-cover policy cannot accidentally apply. Before development resumes, an authorized infrastructure/security review must prove:

- account-level and bucket-level Block Public Access are enabled;
- no public bucket policy, object ACL, website hosting, public CDN origin, or public access point can read the document prefix;
- the backend workload principal has only narrowly scoped `PutObject`, `GetObject`, and `DeleteObject` on the verification-document prefix, with no bucket administration or unrelated-prefix access;
- encryption at rest is enforced and any KMS permissions are scoped to that bucket/prefix and workload;
- admin viewing occurs only through a backend endpoint that revalidates current database-backed admin authority; object keys never authorize access and are never returned to creators or public APIs;
- CloudTrail S3 data events (or equivalent object access evidence), alerts, and a non-production access-denial test cover upload, admin read, deletion, anonymous read, normal-user read, staff/scanner read, and cross-account read;
- lifecycle deletion is configured as a defense in depth and versioning/noncurrent versions, replicas, multipart uploads, and backups cannot retain documents beyond approved policy unnoticed;
- the application can distinguish successful deletion, retryable deletion failure, and terminal/manual cleanup without logging object keys, filenames, document contents, or user PII.

## Retention decision requiring approval

Recommended starting policy: delete immediately after completed verification or rejection, with a private-bucket lifecycle backstop of no more than **7 calendar days** for abandoned/unreviewed uploads. Seven days is a recommendation only; business, privacy, and Guyanese legal review must explicitly approve or replace it before implementation. The approved value must be represented in configuration and the bucket lifecycle, not silently hard-coded.

## Repository technical guarantees

Migration `20260828_0045` adds an account-owned temporary tracking row containing an
opaque internal ID, user ID, sensitive internal object key, safe workflow/outcome
status, upload/review/delete/cleanup timestamps, reviewing admin ID, and bounded
cleanup-attempt evidence. Public and normal-user schemas contain no object key,
bucket, URL, filename, bytes/base64, DOB, ID/document number, OCR, facial data, or
extracted contents.

The disabled upload endpoint authenticates the account owner, accepts only pending
or revoked accounts, permits at most one active submission, rate limits requests,
checks MIME/content agreement and byte/pixel/dimension bounds, rejects malformed or
decompression-bomb images, applies EXIF orientation, strips metadata, and re-encodes
to JPEG. It commits an `uploading` tracker before S3 Put so an uncertain result is
recoverable. The private storage service uses only the separate verification config,
random keys, server-side encryption, and no-store behavior; it has no public-URL API.

Normal users see safe status only and have no raw-content endpoint. Current
database-backed admin authority is required to list or stream pending content.
Verify/reject commits account/history/review evidence before immediate deletion;
failure becomes `cleanup_required` and supports idempotent admin or bounded command
retry. The cleanup command selects only tracked, bounded rows and the storage layer
rejects keys outside the configured prefix. S3 lifecycle handles an object already
missing as a successful idempotent delete. No real ID may be used in automated tests.

## Remaining release gates

- Provision and verify the separate bucket and workload policy using
  `verification-document-s3-setup.md`.
- Apply migration `0045` and deploy the backend with upload disabled.
- Finish the admin/web upload and review UI and coordinated legal/privacy wording.
- Run synthetic access-denial, review, immediate-delete, cleanup-failure, and log
  inspection evidence before enabling the feature.
