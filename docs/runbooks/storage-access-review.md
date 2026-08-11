# Storage and S3 access review

Run quarterly and after any personnel, vendor, bucket-policy, or credential change.

1. Inventory the production bucket, region, public base URL, prefixes, lifecycle rules, encryption, versioning, access logging, CORS, and ownership controls.
2. Confirm the API role has only the required object actions on the configured event-cover prefix. It must not have account-wide administration or access to unrelated buckets.
3. Prefer workload/instance credentials. If static keys remain necessary, confirm ownership, last use, storage location, rotation date, and alerting; rotate immediately if provenance is unclear.
4. Review bucket policy, IAM policies, access points, ACLs, and pre-signed URL lifetimes. Block public access unless a deliberately public asset path is documented. Never store tickets, payment records, exports, or personal documents in a public prefix.
5. Sample CloudTrail/data access records for denied access, bulk downloads, unexpected regions, anonymous access, and dormant principals.
6. Test upload, read, replacement, and deletion in a non-production prefix. Confirm content-type and size restrictions are enforced by the application.
7. Save the reviewer, date, findings, evidence location, remediation owner, and due date in the private security register.
