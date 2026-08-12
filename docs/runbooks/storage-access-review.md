# Storage and S3 access review

Run quarterly and after any personnel, vendor, bucket-policy, or credential change.

1. Inventory the production bucket, region, public base URL, prefixes, lifecycle rules, encryption, versioning, access logging, CORS, and ownership controls.
2. Confirm the API role has only the required object actions on the configured event-cover prefix. It must not have account-wide administration or access to unrelated buckets.
3. Prefer workload/instance credentials. If static keys remain necessary, confirm ownership, last use, storage location, rotation date, and alerting; rotate immediately if provenance is unclear.
4. Review bucket policy, IAM policies, access points, ACLs, and pre-signed URL lifetimes. Block public access unless a deliberately public asset path is documented. Never store tickets, payment records, exports, or personal documents in a public prefix.
5. Sample CloudTrail/data access records for denied access, bulk downloads, unexpected regions, anonymous access, and dormant principals.
6. Test upload, read, replacement, and deletion in a non-production prefix. Confirm content-type and size restrictions are enforced by the application.
7. Save the reviewer, date, findings, evidence location, remediation owner, and due date in the private security register.

## Event-cover access baseline

The API writes normalized public event-cover images beneath `S3_EVENT_PREFIX`. It does not read, list, or delete S3 objects, and clients never receive AWS credentials. Prefer a workload role. If static credentials are unavoidable, provide both `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` only in the backend environment.

The backend principal needs only this application operation:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "WriteEventCoversOnly",
      "Effect": "Allow",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::REPLACE_BUCKET/REPLACE_PREFIX/*"
    }
  ]
}
```

Replace the bucket and prefix exactly; do not use a wildcard bucket. Do not grant the backend `s3:DeleteObject`, `s3:ListBucket`, bucket-policy administration, ACL administration, or access to other prefixes. If the bucket uses a customer-managed KMS key, separately scope only the KMS permissions that AWS documents as necessary for `PutObject` to that key.

Public reads should be limited to the event-cover prefix through the configured `S3_PUBLIC_BASE_URL` (preferably a CDN with origin access control). Keep account-level block-public-access protections for every non-public bucket/prefix. The application does not set object ACLs.

## Replacement and cleanup evidence

Every upload first writes an `event_cover_upload_reserved` audit with the proposed object key. Successful changes add `event_cover_uploaded` or `event_cover_replaced`; concurrent changes add `event_cover_upload_orphaned` with `cleanup_required`; removal adds `event_cover_removed`. Replacement and removal audits retain the prior managed object key.

The API deliberately does not delete objects. Review unresolved reservations and cleanup-required/prior keys with a separate operator role that has narrowly scoped deletion permission. Confirm that a key is not referenced by any current `events.cover_image_url` before deleting it. Test that process against a non-production prefix first, retain evidence, and never grant deletion permission to the normal backend role merely to simplify cleanup.
