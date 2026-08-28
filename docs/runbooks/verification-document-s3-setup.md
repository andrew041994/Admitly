# Private creator-verification S3 setup

This is an operator procedure for a new private bucket. It is not an authorization
to change AWS, Render, production data, or feature flags. Use only synthetic test
images; never use a real government ID during provisioning validation.

## Separation and ownership

The verification bucket must be different from `S3_EVENT_BUCKET`. Admitly's event
cover bucket and `S3_PUBLIC_BASE_URL` are public-delivery infrastructure and must
not appear in verification configuration or policy. Provisioning permissions
belong to an infrastructure operator. The backend runtime receives only
prefix-scoped object Put/Get/Delete permissions.

There is no existing repository-managed AWS IaC. The JSON files under
`infrastructure/verification-s3/` are reviewed operator inputs. Record the AWS
change/ticket reference, operator, UTC time, region, bucket name, lifecycle rule,
runtime role ARN, and verification output in the restricted infrastructure record;
do not put credentials or object keys in that record.

## AWS Console provisioning

1. In the AWS account that runs Admitly, open **S3 → Create bucket**. Choose a new,
   non-identifying globally unique name. Do not reuse the event-cover bucket.
2. Choose the same AWS region as the backend unless the approved architecture says
   otherwise. Record the region, not credentials.
3. Leave all four **Block Public Access** controls enabled:
   `BlockPublicAcls`, `IgnorePublicAcls`, `BlockPublicPolicy`, and
   `RestrictPublicBuckets`.
4. Select **ACLs disabled / Bucket owner enforced**. Do not create a public access
   point, static website, or CloudFront/public CDN distribution.
5. Under default encryption, select **SSE-S3**. The repository defaults deliberately
   avoid KMS operational complexity. A future SSE-KMS change must coordinate the
   bucket policy, application setting, and scoped KMS role permissions.
6. Create the bucket. Under **Properties → Lifecycle configuration**, add an enabled
   rule limited to prefix `creator-verification/`, expire current objects after
   **7 days**, and abort incomplete multipart uploads after 1 day. Seven days is a
   configurable maximum privacy backstop, not normal retention; application review
   deletes immediately.
7. Under **Permissions → Bucket policy**, replace
   `REPLACE_WITH_VERIFICATION_BUCKET` in
   `infrastructure/verification-s3/bucket-policy.json` and apply it. It denies
   non-TLS and unencrypted/unexpected-encryption writes. It grants no public access.
8. In **IAM**, create or update the backend workload policy from
   `runtime-iam-policy.json`, replacing the bucket placeholder. Attach it only to
   the designated backend runtime identity. It must allow only `s3:PutObject`,
   `s3:GetObject`, and `s3:DeleteObject` on
   `arn:aws:s3:::<bucket>/creator-verification/*`.
9. Do not attach `s3:*`, `ListAllMyBuckets`, bucket-policy, lifecycle, IAM,
   event-cover, unrelated-prefix, or bucket-administration permissions to the app.
10. Confirm CloudTrail S3 data events or equivalent restricted access evidence is
    enabled for object reads/writes/deletes according to the approved AWS logging
    policy. Ensure monitoring does not copy request bodies or object contents.

## Render configuration and disabled rollout

11. In the backend service's protected Render environment configuration, add
    `S3_VERIFICATION_BUCKET`, `S3_VERIFICATION_REGION`,
    `S3_VERIFICATION_PREFIX=creator-verification/`,
    `S3_VERIFICATION_MAX_BYTES=8388608`,
    `S3_VERIFICATION_RETENTION_DAYS=7`, and the cleanup batch size/rate-limit
    settings. Use the workload role where supported; if existing static AWS
    credentials are unavoidable, never copy them into tickets or logs.
12. Keep `VERIFICATION_DOCUMENT_UPLOAD_ENABLED=false`. Do not set
    `S3_VERIFICATION_KMS_KEY_ID` for the provided SSE-S3 policy.
13. Apply migration `20260828_0045` only through the separately authorized
    production migration process, then deploy the matching backend while the
    feature remains disabled. Neither action is part of this runbook's repository
    preparation.

## Read-only security verification

14. From a restricted operator workstation with read-only S3 inspection and, if
    used, IAM simulation permission, run without a canary first:

    ```bash
    python scripts/verify_verification_s3.py \
      --bucket '<verification-bucket>' \
      --region '<region>' \
      --event-bucket '<event-cover-bucket>' \
      --runtime-role-arn '<backend-role-arn>'
    ```

    This only calls read/inspection APIs. Require zero failures. Resolve warnings
    about IAM simulation or canary checks before enabling upload.

## Explicitly separated synthetic canary test

15. Only after an approved change window, upload a generated non-ID image through
    the disabled-feature validation mechanism or an explicitly authorized scoped
    operator action. Do not use `aws s3` or a public ACL. Record the canary key only
    in the restricted temporary operator session, never in application logs.
16. Re-run the verifier with `--canary-key '<temporary-synthetic-key>'`. Require
    anonymous HEAD to fail and authorized metadata access to succeed.
17. With designated test accounts, confirm a normal user cannot retrieve either
    their own or another account's raw image, event staff/scanners receive no
    access, and only a currently authorized admin can stream it through the API.
18. Complete synthetic verify and reject exercises. Confirm `DeleteObject`, the
    database `deleted` evidence, no object afterward, and no key/URL/body in API,
    Render, Sentry, audit, or browser logs. Test a simulated delete failure and the
    bounded cleanup retry path.
19. Delete any remaining synthetic canary through the authorized private cleanup
    path. Confirm the lifecycle rule remains a backstop rather than the normal path.
20. Only after security, privacy/legal, migration, backend, and coordinated web UI
    evidence is approved may an operator set
    `VERIFICATION_DOCUMENT_UPLOAD_ENABLED=true` and deploy that configuration.

## Coordinated rollout order

1. Provision the separate bucket and controls.
2. Verify bucket security read-only.
3. Attach the scoped backend runtime policy.
4. Add protected Render configuration with upload disabled.
5. Apply migration `0045` through the authorized migration job.
6. Deploy matching backend code with upload disabled.
7. Validate with a synthetic image and designated tester accounts.
8. Confirm immediate deletion and anonymous/public denial.
9. Approve and deploy coordinated privacy/legal wording and web UI.
10. Enable upload only after all evidence passes.

Rollback the feature by disabling upload, not by making the bucket public or
downgrading the database. Continue immediate cleanup of any tracked objects.
